"""Background worker for matchmaking countdown maintenance."""
import asyncio
import json
import logging
from uuid import UUID

import redis.asyncio as redis

from app.core.config import settings
from app.core.database import async_session
from app.schemas.ws import WSEvent
from app.services.rooms import RoomService
from app.services.ws_connection_manager import ROOM_CHANNEL_PREFIX

logger = logging.getLogger(__name__)


async def _publish_matchmaking_change(redis_client, change: dict) -> None:
    """Publish one matchmaking state change into a room-scoped pub/sub channel."""
    room_id = change["room_id"]
    room_uuid = room_id if isinstance(room_id, UUID) else UUID(str(room_id))
    event_name = change["event"]
    payload = {key: value for key, value in change.items() if key not in {"room_id", "event"}}

    ws_event = WSEvent(
        event=event_name,
        room_id=room_uuid,
        payload=payload,
    ).model_dump(mode="json")

    envelope = {
        "source": "matchmaking-worker",
        "room_id": str(room_uuid),
        "payload": ws_event,
    }
    await redis_client.publish(
        f"{ROOM_CHANNEL_PREFIX}{room_uuid}",
        json.dumps(envelope, default=str),
    )


async def run_matchmaking_worker(poll_interval_seconds: float = 1.0) -> None:
    """Continuously process matchmaking countdown state transitions."""
    redis_client = redis.from_url(settings.REDIS_URL)
    try:
        while True:
            try:
                async with async_session() as db:
                    updated = await RoomService.process_matchmaking_tick(db)
                    if updated:
                        logger.info("matchmaking tick updated %s room(s)", updated)
                        for change in updated:
                            await _publish_matchmaking_change(redis_client, change)
                    await db.commit()
            except Exception as exc:  # pragma: no cover - defensive worker guard
                logger.exception("matchmaking worker tick failed: %s", exc)

            await asyncio.sleep(poll_interval_seconds)
    finally:
        await redis_client.aclose()


def main() -> None:
    """Worker process entrypoint."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_matchmaking_worker())


if __name__ == "__main__":
    main()
