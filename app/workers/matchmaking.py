"""Background worker for matchmaking countdown maintenance."""
import asyncio
import logging

from app.core.database import async_session
from app.services.rooms import RoomService

logger = logging.getLogger(__name__)


async def run_matchmaking_worker(poll_interval_seconds: float = 1.0) -> None:
    """Continuously process matchmaking countdown state transitions."""
    while True:
        try:
            async with async_session() as db:
                updated = await RoomService.process_matchmaking_tick(db)
                if updated:
                    logger.info("matchmaking tick updated %s room(s)", updated)
                await db.commit()
        except Exception as exc:  # pragma: no cover - defensive worker guard
            logger.exception("matchmaking worker tick failed: %s", exc)

        await asyncio.sleep(poll_interval_seconds)


def main() -> None:
    """Worker process entrypoint."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_matchmaking_worker())


if __name__ == "__main__":
    main()
