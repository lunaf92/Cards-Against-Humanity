"""Room service for private room and matchmaking operations."""
from __future__ import annotations

import random
import string
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import Room, RoomPlayer, User
from app.schemas.room import RoomConfigUpdateRequest, RoomCreateRequest, RoomJoinRequest

MATCHMAKING_QUEUE_KEY = "matchmaking:queue"


class RoomService:
    """Business logic for room lifecycle and matchmaking queue."""

    @staticmethod
    async def _generate_unique_room_code(db: AsyncSession) -> str:
        """Generate a unique 6-char room code."""
        charset = string.ascii_uppercase + string.digits
        for _ in range(20):
            code = "".join(random.choices(charset, k=6))
            exists = await db.execute(select(Room.id).where(Room.code == code).limit(1))
            if exists.scalar_one_or_none() is None:
                return code

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to allocate room code",
        )

    @staticmethod
    async def _room_player_count(db: AsyncSession, room_id: UUID) -> int:
        """Return current number of players in a room."""
        result = await db.execute(
            select(func.count()).select_from(RoomPlayer).where(RoomPlayer.room_id == room_id)
        )
        return int(result.scalar_one())

    @staticmethod
    async def _next_join_order(db: AsyncSession, room_id: UUID) -> int:
        """Compute the next join order for room players."""
        result = await db.execute(
            select(func.max(RoomPlayer.join_order)).where(RoomPlayer.room_id == room_id)
        )
        current = result.scalar_one()
        return 1 if current is None else int(current) + 1

    @staticmethod
    async def create_private_room(
        db: AsyncSession,
        host_user: User,
        payload: RoomCreateRequest,
    ) -> Room:
        """Create private room and insert host as first RoomPlayer."""
        room = Room(
            code=await RoomService._generate_unique_room_code(db),
            password_hash=hash_password(payload.password),
            host_id=host_user.id,
            room_kind="private",
            status="lobby",
            max_players=payload.max_players,
            winning_score=payload.winning_score,
            round_timer_seconds=payload.round_timer_seconds,
            card_pool_mode=payload.card_pool_mode,
        )
        db.add(room)
        await db.flush()

        db.add(
            RoomPlayer(
                room_id=room.id,
                player_id=host_user.id,
                join_order=1,
                score=0,
                is_connected=True,
            )
        )
        await db.flush()
        return room

    @staticmethod
    async def join_private_room(
        db: AsyncSession,
        user: User,
        payload: RoomJoinRequest,
    ) -> Room:
        """Join private room by code and password with capacity checks."""
        room_code = payload.code.upper()
        result = await db.execute(select(Room).where(Room.code == room_code))
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

        if room.room_kind != "private":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only private rooms can be joined by code",
            )

        if not room.password_hash or not verify_password(payload.password, room.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid room password",
            )

        existing = await db.execute(
            select(RoomPlayer).where(
                RoomPlayer.room_id == room.id,
                RoomPlayer.player_id == user.id,
            )
        )
        existing_member = existing.scalar_one_or_none()
        if existing_member is not None:
            if not existing_member.is_connected:
                existing_member.is_connected = True
                await db.flush()
            return room

        player_count = await RoomService._room_player_count(db, room.id)
        if player_count >= room.max_players:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room is full")

        db.add(
            RoomPlayer(
                room_id=room.id,
                player_id=user.id,
                join_order=await RoomService._next_join_order(db, room.id),
                score=0,
                is_connected=True,
            )
        )
        await db.flush()
        return room

    @staticmethod
    async def get_room_for_member(db: AsyncSession, room_id: UUID, user_id: UUID) -> Room:
        """Return room only if the requesting user is a member."""
        result = await db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

        membership = await db.execute(
            select(RoomPlayer.id).where(RoomPlayer.room_id == room.id, RoomPlayer.player_id == user_id)
        )
        if membership.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a room member")

        return room

    @staticmethod
    async def list_room_players(db: AsyncSession, room_id: UUID) -> list[dict]:
        """Return room players with user profile fields required by API response."""
        result = await db.execute(
            select(RoomPlayer, User)
            .join(User, RoomPlayer.player_id == User.id)
            .where(RoomPlayer.room_id == room_id)
            .order_by(RoomPlayer.join_order.asc())
        )

        rows = result.all()
        return [
            {
                "player_id": user.id,
                "username": user.username,
                "join_order": room_player.join_order,
                "score": room_player.score,
                "is_connected": room_player.is_connected,
            }
            for room_player, user in rows
        ]

    @staticmethod
    async def update_room_config(
        db: AsyncSession,
        room_id: UUID,
        host_user_id: UUID,
        payload: RoomConfigUpdateRequest,
    ) -> Room:
        """Apply host-only room config updates while room is still in lobby state."""
        result = await db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

        if room.host_id != host_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only host can update room")

        if room.status != "lobby":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Room config can only be updated in lobby",
            )

        if payload.max_players is not None:
            current_players = await RoomService._room_player_count(db, room.id)
            if payload.max_players < current_players:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="max_players cannot be lower than current player count",
                )
            room.max_players = payload.max_players

        if payload.winning_score is not None:
            room.winning_score = payload.winning_score

        if payload.round_timer_seconds is not None:
            room.round_timer_seconds = payload.round_timer_seconds

        if payload.card_pool_mode is not None:
            room.card_pool_mode = payload.card_pool_mode

        await db.flush()
        return room

    @staticmethod
    async def enqueue_for_matchmaking(db: AsyncSession, redis_client, user: User) -> tuple[int, UUID | None]:
        """Enqueue user and promote first 3 queued users into a random room when ready."""
        # Intent: Keep queue ordering deterministic and server-authoritative.
        now = datetime.now(UTC).timestamp()
        await redis_client.zadd(MATCHMAKING_QUEUE_KEY, {str(user.id): now})

        existing_room = await RoomService._find_open_matchmaking_room(db)
        if existing_room is not None:
            await redis_client.zrem(MATCHMAKING_QUEUE_KEY, str(user.id))
            await RoomService._add_player_to_room(db, existing_room, user.id)
            existing_room.matchmaking_fill_expires_at = (
                datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=10)
            )
            await db.flush()
            return int(await redis_client.zcard(MATCHMAKING_QUEUE_KEY)), existing_room.id

        queue_size = int(await redis_client.zcard(MATCHMAKING_QUEUE_KEY))

        queued_users = await redis_client.zrange(MATCHMAKING_QUEUE_KEY, 0, 2)
        queued_user_ids = [UUID(value.decode() if isinstance(value, bytes) else value) for value in queued_users]
        if len(queued_user_ids) < 3:
            return queue_size, None

        for member in queued_user_ids:
            await redis_client.zrem(MATCHMAKING_QUEUE_KEY, str(member))

        room = Room(
            code=await RoomService._generate_unique_room_code(db),
            host_id=queued_user_ids[0],
            room_kind="random",
            status="matchmaking_lobby",
            max_players=10,
            winning_score=8,
            round_timer_seconds=90,
            card_pool_mode="default_only",
            matchmaking_fill_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=10),
        )
        db.add(room)
        await db.flush()

        for player_id in queued_user_ids:
            await RoomService._add_player_to_room(db, room, player_id)

        await db.flush()
        return int(await redis_client.zcard(MATCHMAKING_QUEUE_KEY)), room.id

    @staticmethod
    async def leave_matchmaking_queue(redis_client, user_id: UUID) -> bool:
        """Remove player from matchmaking queue."""
        removed = await redis_client.zrem(MATCHMAKING_QUEUE_KEY, str(user_id))
        return bool(removed)

    @staticmethod
    async def _find_open_matchmaking_room(db: AsyncSession) -> Room | None:
        """Find an existing matchmaking lobby that can accept more players."""
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await db.execute(
            select(Room)
            .where(
                Room.room_kind == "random",
                Room.status == "matchmaking_lobby",
                Room.matchmaking_fill_expires_at.is_not(None),
                Room.matchmaking_fill_expires_at > now,
            )
            .order_by(Room.matchmaking_fill_expires_at.asc())
            .limit(1)
        )
        room = result.scalar_one_or_none()
        if room is None:
            return None

        players = await RoomService._room_player_count(db, room.id)
        if players >= room.max_players:
            return None

        return room

    @staticmethod
    async def _add_player_to_room(db: AsyncSession, room: Room, user_id: UUID) -> None:
        """Insert player membership in room if not already present."""
        existing = await db.execute(
            select(RoomPlayer).where(
                RoomPlayer.room_id == room.id,
                RoomPlayer.player_id == user_id,
            )
        )
        existing_member = existing.scalar_one_or_none()
        if existing_member is not None:
            if not existing_member.is_connected:
                existing_member.is_connected = True
            await db.flush()
            return

        db.add(
            RoomPlayer(
                room_id=room.id,
                player_id=user_id,
                join_order=await RoomService._next_join_order(db, room.id),
                score=0,
                is_connected=True,
            )
        )
        await db.flush()

    @staticmethod
    async def process_matchmaking_tick(db: AsyncSession) -> int:
        """Update matchmaking countdown state for all random lobbies."""
        now = datetime.now(UTC).replace(tzinfo=None)
        updated = 0

        result = await db.execute(
            select(Room).where(
                Room.room_kind == "random",
                Room.status == "matchmaking_lobby",
            )
        )
        rooms = result.scalars().all()

        for room in rooms:
            player_count = await RoomService._room_player_count(db, room.id)

            # Cancel countdown if lobby drops below matchmaking threshold.
            if player_count < 3 and room.matchmaking_fill_expires_at is not None:
                room.matchmaking_fill_expires_at = None
                updated += 1
                continue

            # Start countdown once lobby has enough players.
            if player_count >= 3 and room.matchmaking_fill_expires_at is None:
                room.matchmaking_fill_expires_at = now + timedelta(seconds=10)
                updated += 1
                continue

            # Keep countdown rolling by resetting expired lobbies that still have 3-9 players.
            if (
                3 <= player_count < room.max_players
                and room.matchmaking_fill_expires_at is not None
                and room.matchmaking_fill_expires_at <= now
            ):
                room.matchmaking_fill_expires_at = now + timedelta(seconds=10)
                updated += 1

        if updated:
            await db.flush()

        return updated
