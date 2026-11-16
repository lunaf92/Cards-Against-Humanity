"""Delivery-robustness tests for the in-memory room connection manager."""

import asyncio
from uuid import uuid4

from app.services.ws_connection_manager import RoomConnectionManager


class _StubSocket:
    """WebSocket double that records sends or fails like a closed connection."""

    def __init__(self, *, broken: bool = False):
        self.broken = broken
        self.sent: list[dict] = []

    async def accept(self):
        return None

    async def send_json(self, payload: dict):
        if self.broken:
            raise RuntimeError('Cannot call "send" once a close message has been sent.')
        self.sent.append(payload)


def test_broadcast_survives_a_dead_socket():
    """One closed socket must not stop delivery to the remaining players."""

    async def _run():
        manager = RoomConnectionManager()
        room_id = uuid4()
        dead_user, live_user = uuid4(), uuid4()
        dead, live = _StubSocket(broken=True), _StubSocket()
        await manager.connect(room_id, dead_user, dead)
        await manager.connect(room_id, live_user, live)

        await manager.broadcast_event(room_id, {"event": "round.started"})
        await manager.send_personal_event(room_id, dead_user, {"event": "player.hand"})
        return live.sent

    assert asyncio.run(_run()) == [{"event": "round.started"}]
