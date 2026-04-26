"""Room service for private room and matchmaking operations."""
from __future__ import annotations

import json
import random
import string
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import Card, GameRound, Room, RoomPlayer, Submission, User
from app.schemas.room import RoomConfigUpdateRequest, RoomCreateRequest, RoomJoinRequest

MATCHMAKING_QUEUE_KEY = "matchmaking:queue"
GAME_WHITE_DECK_KEY = "game:{room_id}:white_deck"
GAME_PLAYER_HAND_KEY = "game:{room_id}:hand:{user_id}"


class RoomGameError(Exception):
    """Domain error for room gameplay actions and websocket protocol guards."""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


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
    async def _ordered_room_player_rows(db: AsyncSession, room_id: UUID) -> list[RoomPlayer]:
        """Return ordered RoomPlayer rows for rotation and scoreboard logic."""
        result = await db.execute(
            select(RoomPlayer).where(RoomPlayer.room_id == room_id).order_by(RoomPlayer.join_order.asc())
        )
        return result.scalars().all()

    @staticmethod
    def _white_deck_key(room_id: UUID) -> str:
        """Build Redis key for room white deck state."""
        return GAME_WHITE_DECK_KEY.format(room_id=room_id)

    @staticmethod
    def _player_hand_key(room_id: UUID, user_id: UUID) -> str:
        """Build Redis key for a player's private hand state."""
        return GAME_PLAYER_HAND_KEY.format(room_id=room_id, user_id=user_id)

    @staticmethod
    async def _redis_json_get(redis_client, key: str) -> list[UUID]:
        """Load JSON array payload from Redis and normalize entries to UUIDs."""
        raw = await redis_client.get(key)
        if raw is None:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode()
        values = json.loads(raw)
        return [item if isinstance(item, UUID) else UUID(str(item)) for item in values]

    @staticmethod
    async def _redis_json_set(redis_client, key: str, values: list[UUID]) -> None:
        """Persist UUID list into Redis as JSON array of strings."""
        await redis_client.set(key, json.dumps([str(item) for item in values]))

    @staticmethod
    async def get_white_deck(redis_client, room_id: UUID) -> list[UUID]:
        """Return remaining white deck for the room from Redis state."""
        return await RoomService._redis_json_get(redis_client, RoomService._white_deck_key(room_id))

    @staticmethod
    async def _set_white_deck(redis_client, room_id: UUID, deck: list[UUID]) -> None:
        """Persist remaining white deck for the room."""
        await RoomService._redis_json_set(redis_client, RoomService._white_deck_key(room_id), deck)

    @staticmethod
    async def get_player_hand(redis_client, room_id: UUID, user_id: UUID) -> list[UUID]:
        """Return private hand for a room player from Redis state."""
        return await RoomService._redis_json_get(
            redis_client,
            RoomService._player_hand_key(room_id, user_id),
        )

    @staticmethod
    async def _set_player_hand(redis_client, room_id: UUID, user_id: UUID, hand: list[UUID]) -> None:
        """Persist private hand for a room player."""
        await RoomService._redis_json_set(
            redis_client,
            RoomService._player_hand_key(room_id, user_id),
            hand,
        )

    @staticmethod
    async def _select_white_cards_for_room(db: AsyncSession, room: Room) -> list[UUID]:
        """Select white-card pool for room dealing; currently default-only."""
        result = await db.execute(
            select(Card.id)
            .where(Card.type == "white", Card.is_default.is_(True))
            .order_by(Card.created_at.asc(), Card.id.asc())
        )
        return [card_id for (card_id,) in result.all()]

    @staticmethod
    async def _deal_initial_hands(db: AsyncSession, redis_client, room: Room) -> dict[UUID, list[UUID]]:
        """Shuffle white deck, deal 10 cards to each player, and persist Redis game state."""
        players = await RoomService._ordered_room_player_rows(db, room.id)
        white_deck = await RoomService._select_white_cards_for_room(db, room)
        required_cards = len(players) * 10
        if len(white_deck) < required_cards:
            raise RoomGameError(
                "STATE_CONFLICT",
                "Not enough white cards to deal starting hands",
                {"required": required_cards, "available": len(white_deck)},
            )

        random.shuffle(white_deck)
        dealt: dict[UUID, list[UUID]] = {}
        for player in players:
            hand = white_deck[:10]
            white_deck = white_deck[10:]
            dealt[player.player_id] = hand
            await RoomService._set_player_hand(redis_client, room.id, player.player_id, hand)

        await RoomService._set_white_deck(redis_client, room.id, white_deck)
        return dealt

    @staticmethod
    async def _remove_cards_from_hand(
        redis_client,
        room_id: UUID,
        user_id: UUID,
        submitted_card_ids: list[UUID],
    ) -> list[UUID]:
        """Validate submitted cards belong to player's hand and remove them."""
        hand = await RoomService.get_player_hand(redis_client, room_id, user_id)
        remaining_hand = list(hand)
        for card_id in submitted_card_ids:
            if card_id not in remaining_hand:
                raise RoomGameError(
                    "INVALID_CARD_SELECTION",
                    "One or more white cards are not in player's hand",
                    {"reason": "card_not_in_hand"},
                )
            remaining_hand.remove(card_id)

        await RoomService._set_player_hand(redis_client, room_id, user_id, remaining_hand)
        return remaining_hand

    @staticmethod
    async def _refill_player_hands(redis_client, room_id: UUID, player_ids: list[UUID]) -> dict[UUID, list[UUID]]:
        """Draw from deck until each listed player is back to 10 white cards."""
        hands_by_player = {
            player_id: await RoomService.get_player_hand(redis_client, room_id, player_id)
            for player_id in player_ids
        }
        deck = await RoomService.get_white_deck(redis_client, room_id)

        total_needed = sum(max(0, 10 - len(hand)) for hand in hands_by_player.values())
        if len(deck) < total_needed:
            raise RoomGameError(
                "STATE_CONFLICT",
                "Not enough white cards to refill hands",
                {"required": total_needed, "available": len(deck)},
            )

        for player_id, hand in hands_by_player.items():
            missing = 10 - len(hand)
            if missing <= 0:
                continue

            drawn_cards = deck[:missing]
            deck = deck[missing:]
            new_hand = hand + drawn_cards
            hands_by_player[player_id] = new_hand
            await RoomService._set_player_hand(redis_client, room_id, player_id, new_hand)

        await RoomService._set_white_deck(redis_client, room_id, deck)
        return hands_by_player

    @staticmethod
    async def _pick_black_card_for_round(db: AsyncSession, round_number: int) -> Card:
        """Pick a deterministic black card for a round from the current card pool."""
        result = await db.execute(
            select(Card).where(Card.type == "black").order_by(Card.created_at.asc(), Card.id.asc())
        )
        black_cards = result.scalars().all()
        if not black_cards:
            raise RoomGameError("STATE_CONFLICT", "No black cards available", {"event": "round.start"})
        return black_cards[(round_number - 1) % len(black_cards)]

    @staticmethod
    async def _next_czar_id(db: AsyncSession, room_id: UUID, current_czar_id: UUID | None = None) -> UUID:
        """Rotate the czar in room join order."""
        players = await RoomService._ordered_room_player_rows(db, room_id)
        if len(players) < 3:
            raise RoomGameError("STATE_CONFLICT", "Need at least 3 players to run game rounds")

        if current_czar_id is None:
            return players[0].player_id

        for index, player in enumerate(players):
            if player.player_id == current_czar_id:
                return players[(index + 1) % len(players)].player_id

        return players[0].player_id

    @staticmethod
    async def _create_round(
        db: AsyncSession,
        room: Room,
        round_number: int,
        czar_id: UUID,
    ) -> tuple[GameRound, Card]:
        """Create a new waiting round with rotated czar and chosen black card."""
        black_card = await RoomService._pick_black_card_for_round(db, round_number)
        round_obj = GameRound(
            room_id=room.id,
            round_number=round_number,
            czar_id=czar_id,
            black_card_id=black_card.id,
            status="waiting",
        )
        db.add(round_obj)
        await db.flush()
        return round_obj, black_card

    @staticmethod
    async def _round_submission_payload(db: AsyncSession, round_id: UUID) -> list[dict]:
        """Build anonymized judging payload with card texts for all submissions."""
        submissions_result = await db.execute(
            select(Submission).where(Submission.round_id == round_id)
        )
        submissions = submissions_result.scalars().all()

        all_white_card_ids = {
            card_id
            for submission_item in submissions
            for card_id in submission_item.white_card_ids
        }
        cards_result = await db.execute(
            select(Card.id, Card.text).where(Card.id.in_(all_white_card_ids), Card.type == "white")
        )
        card_text_by_id = {card_id: text for card_id, text in cards_result.all()}

        payload = [
            {
                "submission_id": str(item.id),
                "white_card_texts": [card_text_by_id.get(card_id, "") for card_id in item.white_card_ids],
            }
            for item in submissions
        ]
        random.shuffle(payload)
        return payload

    @staticmethod
    async def build_game_state(
        db: AsyncSession,
        room_id: UUID,
        redis_client=None,
        current_user_id: UUID | None = None,
    ) -> dict | None:
        """Build active game snapshot for websocket state-sync requests."""
        round_result = await db.execute(
            select(GameRound)
            .where(
                GameRound.room_id == room_id,
                GameRound.status.in_(("waiting", "judging")),
            )
            .order_by(GameRound.round_number.desc())
            .limit(1)
        )
        active_round = round_result.scalar_one_or_none()
        if active_round is None:
            return None

        black_card = await db.get(Card, active_round.black_card_id)
        submitted_count_result = await db.execute(
            select(func.count()).select_from(Submission).where(Submission.round_id == active_round.id)
        )
        submitted_count = int(submitted_count_result.scalar_one())
        required_count_result = await db.execute(
            select(func.count()).select_from(RoomPlayer).where(
                RoomPlayer.room_id == room_id,
                RoomPlayer.player_id != active_round.czar_id,
            )
        )
        required_count = int(required_count_result.scalar_one())

        payload = {
            "round_id": str(active_round.id),
            "round_number": active_round.round_number,
            "status": active_round.status,
            "czar_id": str(active_round.czar_id),
            "submitted_count": submitted_count,
            "required_count": required_count,
            "black_card": None,
        }
        if black_card is not None:
            payload["black_card"] = {
                "id": str(black_card.id),
                "text": black_card.text,
                "pick": black_card.pick,
            }

        if active_round.status == "judging":
            payload["submissions"] = await RoomService._round_submission_payload(db, active_round.id)

        if redis_client is not None and current_user_id is not None:
            payload["hand"] = [
                str(card_id)
                for card_id in await RoomService.get_player_hand(redis_client, room_id, current_user_id)
            ]

        return payload

    @staticmethod
    async def start_game(db: AsyncSession, room: Room, current_user_id: UUID, redis_client) -> dict:
        """Validate lobby start and create the first round for the room."""
        if room.host_id != current_user_id:
            raise RoomGameError("NOT_HOST", "Only host can start the game", {"event": "lobby.start_game"})

        if room.status not in ("lobby", "matchmaking_lobby"):
            raise RoomGameError(
                "STATE_CONFLICT",
                "Room is not in a startable state",
                {"room_status": room.status},
            )

        players_count = await RoomService._room_player_count(db, room.id)
        if players_count < 3:
            raise RoomGameError(
                "STATE_CONFLICT",
                "Need at least 3 players to start game",
                {"player_count": players_count},
            )

        max_round_result = await db.execute(
            select(func.max(GameRound.round_number)).where(GameRound.room_id == room.id)
        )
        current_round = max_round_result.scalar_one()
        next_round_number = 1 if current_round is None else int(current_round) + 1
        czar_id = await RoomService._next_czar_id(db, room.id)

        room.status = "in_progress"
        round_obj, black_card = await RoomService._create_round(db, room, next_round_number, czar_id)
        players = await RoomService.list_room_players(db, room.id)
        hands = await RoomService._deal_initial_hands(db, redis_client, room)

        return {
            "round": round_obj,
            "black_card": black_card,
            "round_number": next_round_number,
            "players": players,
            "hands": hands,
        }

    @staticmethod
    async def submit_cards(
        db: AsyncSession,
        room: Room,
        current_user_id: UUID,
        round_id: UUID,
        white_card_ids: list[UUID],
        redis_client,
    ) -> dict:
        """Validate and persist a player's round submission."""
        if room.status != "in_progress":
            raise RoomGameError("GAME_NOT_STARTED", "Game is not in progress")

        round_result = await db.execute(
            select(GameRound).where(GameRound.id == round_id, GameRound.room_id == room.id)
        )
        round_obj = round_result.scalar_one_or_none()
        if round_obj is None or round_obj.status != "waiting":
            raise RoomGameError(
                "ROUND_NOT_ACTIVE",
                "Round is not accepting submissions",
                {"round_id": str(round_id)},
            )

        if round_obj.czar_id == current_user_id:
            raise RoomGameError("NOT_CZAR", "Czar cannot submit cards")

        black_card = await db.get(Card, round_obj.black_card_id)
        pick_count = 1 if black_card is None else int(black_card.pick)
        if len(white_card_ids) != pick_count:
            raise RoomGameError(
                "INVALID_CARD_SELECTION",
                "Submitted card count does not match black card pick",
                {"required": pick_count},
            )

        duplicate_result = await db.execute(
            select(Submission.id).where(
                Submission.round_id == round_obj.id,
                Submission.player_id == current_user_id,
            )
        )
        if duplicate_result.scalar_one_or_none() is not None:
            raise RoomGameError("DUPLICATE_SUBMISSION", "Player already submitted for this round")

        cards_result = await db.execute(
            select(Card.id).where(Card.id.in_(white_card_ids), Card.type == "white")
        )
        cards_rows = cards_result.all()
        if len(cards_rows) != len(white_card_ids):
            raise RoomGameError(
                "INVALID_CARD_SELECTION",
                "One or more white cards are invalid",
            )

        await RoomService._remove_cards_from_hand(
            redis_client,
            room.id,
            current_user_id,
            white_card_ids,
        )

        submission = Submission(
            round_id=round_obj.id,
            player_id=current_user_id,
            white_card_ids=white_card_ids,
            is_winner=False,
        )
        db.add(submission)
        await db.flush()

        submitted_count_result = await db.execute(
            select(func.count()).select_from(Submission).where(Submission.round_id == round_obj.id)
        )
        submitted_count = int(submitted_count_result.scalar_one())
        required_count_result = await db.execute(
            select(func.count()).select_from(RoomPlayer).where(
                RoomPlayer.room_id == room.id,
                RoomPlayer.player_id != round_obj.czar_id,
            )
        )
        required_count = int(required_count_result.scalar_one())

        if submitted_count >= required_count and required_count > 0:
            round_obj.status = "judging"
            return {
                "transition": "judging",
                "round": round_obj,
                "submissions": await RoomService._round_submission_payload(db, round_obj.id),
            }

        return {
            "transition": "accepted",
            "round": round_obj,
            "submitted_count": submitted_count,
            "required_count": required_count,
        }

    @staticmethod
    async def pick_winner(
        db: AsyncSession,
        room: Room,
        current_user_id: UUID,
        round_id: UUID,
        submission_id: UUID | str,
        redis_client,
    ) -> dict:
        """Record the round winner, advance score, and either end or continue the game."""
        if room.status != "in_progress":
            raise RoomGameError("GAME_NOT_STARTED", "Game is not in progress")

        normalized_submission_id = submission_id if isinstance(submission_id, UUID) else UUID(str(submission_id))

        round_result = await db.execute(
            select(GameRound).where(GameRound.id == round_id, GameRound.room_id == room.id)
        )
        round_obj = round_result.scalar_one_or_none()
        if round_obj is None or round_obj.status != "judging":
            raise RoomGameError(
                "ROUND_NOT_ACTIVE",
                "Round is not in judging state",
                {"round_id": str(round_id)},
            )

        if round_obj.czar_id != current_user_id:
            raise RoomGameError("NOT_CZAR", "Only czar can pick winner")

        winner_result = await db.execute(
            select(Submission).where(
                Submission.id == normalized_submission_id,
                Submission.round_id == round_obj.id,
            )
        )
        winner_submission = winner_result.scalar_one_or_none()
        if winner_submission is None:
            raise RoomGameError(
                "INVALID_PAYLOAD",
                "submission_id does not belong to this round",
            )

        reset_result = await db.execute(select(Submission).where(Submission.round_id == round_obj.id))
        for submission in reset_result.scalars().all():
            submission.is_winner = submission.id == winner_submission.id

        player_result = await db.execute(
            select(RoomPlayer).where(
                RoomPlayer.room_id == room.id,
                RoomPlayer.player_id == winner_submission.player_id,
            )
        )
        winning_player = player_result.scalar_one_or_none()
        if winning_player is None:
            raise RoomGameError("STATE_CONFLICT", "Winning player not found in room")

        winning_player.score += 1
        round_obj.status = "complete"

        scoreboard = await RoomService._ordered_room_player_rows(db, room.id)
        game_winner = None
        for row in scoreboard:
            if row.score >= room.winning_score:
                game_winner = row
                break

        if game_winner is not None:
            room.status = "finished"
            return {
                "winner_submission": winner_submission,
                "scoreboard": scoreboard,
                "game_winner": game_winner,
                "next_round": None,
                "next_black_card": None,
            }

        next_round_number = round_obj.round_number + 1
        next_czar_id = await RoomService._next_czar_id(db, room.id, round_obj.czar_id)
        refilled_hands = await RoomService._refill_player_hands(
            redis_client,
            room.id,
            [player.player_id for player in scoreboard],
        )
        next_round, next_black_card = await RoomService._create_round(
            db,
            room,
            next_round_number,
            next_czar_id,
        )
        return {
            "winner_submission": winner_submission,
            "scoreboard": scoreboard,
            "game_winner": None,
            "next_round": next_round,
            "next_black_card": next_black_card,
            "hands": refilled_hands,
        }

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
        )
        rooms = result.scalars().all()

        for room in rooms:
            players = await RoomService._room_player_count(db, room.id)
            if players < room.max_players:
                return room

        return None

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
