"""In-memory WebSocket connection manager for room channels."""

from __future__ import annotations

from uuid import UUID

from fastapi import WebSocket


class RoomConnectionManager:
    """Track and broadcast room-bound WebSocket connections."""

    def __init__(self) -> None:
        self._rooms: dict[UUID, dict[UUID, WebSocket]] = {}

    async def connect(self, room_id: UUID, user_id: UUID, websocket: WebSocket) -> None:
        """Accept socket and register user connection for room."""
        await websocket.accept()
        self._rooms.setdefault(room_id, {})[user_id] = websocket

    def disconnect(self, room_id: UUID, user_id: UUID) -> None:
        """Remove connection for user and prune empty room channels."""
        room_connections = self._rooms.get(room_id)
        if room_connections is None:
            return

        room_connections.pop(user_id, None)
        if not room_connections:
            self._rooms.pop(room_id, None)

    async def send_personal_event(self, room_id: UUID, user_id: UUID, payload: dict) -> None:
        """Send event payload to one connected user in room."""
        websocket = self._rooms.get(room_id, {}).get(user_id)
        if websocket is None:
            return
        await websocket.send_json(payload)

    async def broadcast_event(self, room_id: UUID, payload: dict) -> None:
        """Broadcast event payload to all connected users in room."""
        room_connections = self._rooms.get(room_id, {})
        for websocket in room_connections.values():
            await websocket.send_json(payload)


connection_manager = RoomConnectionManager()
