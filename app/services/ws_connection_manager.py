"""In-memory WebSocket connection manager for room channels."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID
from uuid import uuid4

from fastapi import WebSocket
import redis.asyncio as redis


logger = logging.getLogger(__name__)
ROOM_CHANNEL_PREFIX = "ws:room:"
BRIDGE_RESTART_DELAY_SECONDS = 1.0


class RoomConnectionManager:
    """Track and broadcast room-bound WebSocket connections."""

    def __init__(self) -> None:
        self._rooms: dict[UUID, dict[UUID, list[WebSocket]]] = {}
        self._instance_id = str(uuid4())
        self._redis_client: redis.Redis | None = None
        self._bridge_task: asyncio.Task | None = None

    async def start_pubsub_bridge(self, redis_url: str) -> None:
        """Start Redis pub/sub bridge for cross-instance room broadcasts."""
        if self._bridge_task is not None and not self._bridge_task.done():
            return

        self._redis_client = redis.from_url(redis_url)
        self._bridge_task = asyncio.create_task(self._run_pubsub_bridge())

    async def stop_pubsub_bridge(self) -> None:
        """Stop Redis pub/sub bridge and close shared Redis client."""
        if self._bridge_task is not None:
            self._bridge_task.cancel()
            try:
                await self._bridge_task
            except asyncio.CancelledError:
                pass
            self._bridge_task = None

        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None

    async def _run_pubsub_bridge(self) -> None:
        """Subscribe to room channels and fan-out remote events locally.

        The bridge is the only path for worker-published matchmaking events, so
        it resubscribes after unexpected failures instead of dying silently.
        """
        while self._redis_client is not None:
            pubsub = self._redis_client.pubsub()
            try:
                await pubsub.psubscribe(f"{ROOM_CHANNEL_PREFIX}*")
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message is None:
                        await asyncio.sleep(0.05)
                        continue
                    await self._handle_bridge_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive bridge guard
                logger.exception("websocket pubsub bridge failed, restarting: %s", exc)
                await asyncio.sleep(BRIDGE_RESTART_DELAY_SECONDS)
            finally:
                try:
                    await pubsub.aclose()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass

    async def _handle_bridge_message(self, message: dict) -> None:
        """Fan out one pub/sub message locally; malformed messages are dropped."""
        raw_data = message.get("data")
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode()
        if not isinstance(raw_data, str):
            return

        try:
            envelope = json.loads(raw_data)
            if not isinstance(envelope, dict) or envelope.get("source") == self._instance_id:
                return

            room_id_raw = envelope.get("room_id")
            payload = envelope.get("payload")
            if room_id_raw is None or not isinstance(payload, dict):
                return
            room_id = UUID(str(room_id_raw))
        except ValueError:
            logger.warning("dropping malformed pubsub message")
            return

        await self._broadcast_local(room_id, payload)

    @staticmethod
    async def _safe_send(websocket: WebSocket, payload: dict) -> bool:
        """Send to one socket; a dead socket must never break delivery to the others."""
        try:
            await websocket.send_json(payload)
            return True
        except Exception as exc:
            # The socket's own receive loop notices the disconnect and cleans up.
            logger.debug("dropping event for closed websocket: %s", exc)
            return False

    async def _broadcast_local(self, room_id: UUID, payload: dict) -> None:
        """Broadcast payload only to sockets connected in this process."""
        # Snapshot first: sockets may connect/disconnect while sends are awaited.
        sockets = [
            websocket
            for user_connections in list(self._rooms.get(room_id, {}).values())
            for websocket in list(user_connections)
        ]
        for websocket in sockets:
            await self._safe_send(websocket, payload)

    async def _publish_room_event(self, room_id: UUID, payload: dict) -> None:
        """Publish payload for other app instances via Redis pub/sub."""
        if self._redis_client is None:
            return

        channel = f"{ROOM_CHANNEL_PREFIX}{room_id}"
        envelope = {
            "source": self._instance_id,
            "room_id": str(room_id),
            "payload": payload,
        }
        try:
            await self._redis_client.publish(channel, json.dumps(envelope, default=str))
        except Exception as exc:
            # Local delivery already happened; a Redis hiccup must not fail the command.
            logger.warning("failed to publish room event to redis: %s", exc)

    async def connect(self, room_id: UUID, user_id: UUID, websocket: WebSocket) -> None:
        """Accept socket and register user connection for room."""
        await websocket.accept()
        room_connections = self._rooms.setdefault(room_id, {})
        room_connections.setdefault(user_id, []).append(websocket)

    def has_user_connections(self, room_id: UUID, user_id: UUID) -> bool:
        """Return whether user already has one or more sockets in room."""
        return bool(self._rooms.get(room_id, {}).get(user_id))

    def has_other_connected_users(self, room_id: UUID, user_id: UUID) -> bool:
        """Return whether room has connected users excluding the provided user."""
        room_connections = self._rooms.get(room_id, {})
        return any(other_user_id != user_id for other_user_id in room_connections)

    def disconnect(self, room_id: UUID, user_id: UUID, websocket: WebSocket) -> bool:
        """Remove connection for user and prune empty room channels."""
        room_connections = self._rooms.get(room_id)
        if room_connections is None:
            return False

        user_connections = room_connections.get(user_id)
        if user_connections is None:
            return False

        room_connections[user_id] = [conn for conn in user_connections if conn is not websocket]
        disconnected_user = False
        if not room_connections[user_id]:
            room_connections.pop(user_id, None)
            disconnected_user = True

        if not room_connections:
            self._rooms.pop(room_id, None)

        return disconnected_user

    async def send_personal_event(self, room_id: UUID, user_id: UUID, payload: dict) -> None:
        """Send event payload to one connected user in room."""
        for websocket in list(self._rooms.get(room_id, {}).get(user_id, [])):
            await self._safe_send(websocket, payload)

    def connected_user_ids(self, room_id: UUID) -> list[UUID]:
        """Return ids of users with at least one live socket in the room."""
        return list(self._rooms.get(room_id, {}).keys())

    async def broadcast_event(self, room_id: UUID, payload: dict) -> None:
        """Broadcast event payload to all connected users in room."""
        await self._broadcast_local(room_id, payload)
        await self._publish_room_event(room_id, payload)


connection_manager = RoomConnectionManager()
