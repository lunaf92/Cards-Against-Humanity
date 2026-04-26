"""In-memory WebSocket connection manager for room channels."""

from __future__ import annotations

from uuid import UUID

from fastapi import WebSocket


class RoomConnectionManager:
    """Track and broadcast room-bound WebSocket connections."""

    def __init__(self) -> None:
        self._rooms: dict[UUID, dict[UUID, list[WebSocket]]] = {}

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
        room_connections = self._rooms.get(room_id, {})
        for user_connections in room_connections.values():
            for websocket in user_connections:
                await websocket.send_json(payload)


connection_manager = RoomConnectionManager()
