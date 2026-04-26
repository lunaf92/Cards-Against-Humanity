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
        """Subscribe to room channels and fan-out remote events locally."""
        if self._redis_client is None:
            return

        pubsub = self._redis_client.pubsub()
        await pubsub.psubscribe(f"{ROOM_CHANNEL_PREFIX}*")

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    await asyncio.sleep(0.05)
                    continue

                raw_data = message.get("data")
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode()
                if not isinstance(raw_data, str):
                    continue

                envelope = json.loads(raw_data)
                if envelope.get("source") == self._instance_id:
                    continue

                room_id_raw = envelope.get("room_id")
                payload = envelope.get("payload")
                if room_id_raw is None or not isinstance(payload, dict):
                    continue

                room_id = UUID(str(room_id_raw))
                await self._broadcast_local(room_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive bridge guard
            logger.exception("websocket pubsub bridge failed: %s", exc)
        finally:
            await pubsub.aclose()

    async def _broadcast_local(self, room_id: UUID, payload: dict) -> None:
        """Broadcast payload only to sockets connected in this process."""
        room_connections = self._rooms.get(room_id, {})
        for user_connections in room_connections.values():
            for websocket in user_connections:
                await websocket.send_json(payload)

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
        await self._redis_client.publish(channel, json.dumps(envelope, default=str))

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
        user_connections = self._rooms.get(room_id, {}).get(user_id, [])
        if not user_connections:
            return
        for websocket in user_connections:
            await websocket.send_json(payload)

    async def broadcast_event(self, room_id: UUID, payload: dict) -> None:
        """Broadcast event payload to all connected users in room."""
        await self._broadcast_local(room_id, payload)
        await self._publish_room_event(room_id, payload)


connection_manager = RoomConnectionManager()
