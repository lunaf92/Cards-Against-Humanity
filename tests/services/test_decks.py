"""Rooms deal only from their chosen decks."""
import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Card, Deck, DeckMember
from app.services.decks import DeckService
from app.services.rooms import RoomGameError, RoomService
from tests.services.test_rooms_gameplay import _FakeRedisClient, _create_room_with_players, _create_users


async def _deck(session, name, *, black=1, white=30, owner=None, slug=None, public=False) -> Deck:
    deck = Deck(name=name, slug=slug, owner_id=owner, is_public=public or owner is None)
    session.add(deck)
    await session.flush()
    session.add_all(Card(type="black", text=f"{name} prompt {i} _", pick=1, is_default=owner is None, deck_id=deck.id) for i in range(black))
    session.add_all(Card(type="white", text=f"{name} answer {i}", is_default=owner is None, deck_id=deck.id) for i in range(white))
    await session.flush()
    return deck


def test_room_deals_only_from_chosen_decks(test_db):
    async def _run():
        async with test_db() as session:
            redis = _FakeRedisClient()
            users = await _create_users(session, 3, "pick")
            room = await _create_room_with_players(session, users)
            await _deck(session, "Base", slug="base-game")
            mine = await _deck(session, "Mine", owner=users[0].id)

            await DeckService.set_room_decks(session, room, [mine.id], users[0].id)
            outcome = await RoomService.start_game(session, room, users[0].id, redis)

            mine_ids = set((await session.execute(select(Card.id).where(Card.deck_id == mine.id))).scalars())
            assert outcome["black_card"].deck_id == mine.id
            for user in users:
                assert set(await RoomService.get_player_hand(redis, room.id, user.id)) <= mine_ids

    asyncio.run(_run())


def test_default_selection_is_builtin_without_family_edition(test_db):
    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 3, "dflt")
            room = await _create_room_with_players(session, users)
            base = await _deck(session, "Base", slug="base-game")
            await _deck(session, "Family", slug="family-edition")
            await _deck(session, "Mine", owner=users[0].id)
            assert await DeckService.room_deck_ids(session, room.id) == [base.id]

    asyncio.run(_run())


def test_start_refuses_when_decks_are_too_small(test_db):
    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 3, "tiny")
            room = await _create_room_with_players(session, users)
            await _deck(session, "Base", slug="base-game")
            tiny = await _deck(session, "Tiny", owner=users[0].id, white=12)
            await DeckService.set_room_decks(session, room, [tiny.id], users[0].id)
            with pytest.raises(RoomGameError) as err:
                await RoomService.start_game(session, room, users[0].id, _FakeRedisClient())
            assert err.value.details["white_required"] == 30
            assert room.status == "lobby"

    asyncio.run(_run())


def test_host_can_use_builtin_own_and_coedited_decks_only(test_db):
    async def _run():
        async with test_db() as session:
            users = await _create_users(session, 3, "acc")
            room = await _create_room_with_players(session, users)
            base = await _deck(session, "Base", slug="base-game")
            own = await _deck(session, "Own", owner=users[0].id)
            shared = await _deck(session, "Shared", owner=users[1].id)
            session.add(DeckMember(deck_id=shared.id, user_id=users[0].id))
            other = await _deck(session, "Other", owner=users[2].id, public=True)
            await session.flush()

            await DeckService.set_room_decks(session, room, [base.id, own.id, shared.id], users[0].id)
            assert set(await DeckService.room_deck_ids(session, room.id)) == {base.id, own.id, shared.id}
            with pytest.raises(HTTPException) as err:
                await DeckService.set_room_decks(session, room, [other.id], users[0].id)
            assert err.value.status_code == 404

            usable = {d["name"]: d for d in await DeckService.usable_decks(session, users[0].id)}
            assert set(usable) == {"Base", "Own", "Shared"}
            assert usable["Base"]["is_default"] and not usable["Own"]["is_default"]
            assert usable["Own"]["is_owner"] and not usable["Shared"]["is_owner"]
            assert usable["Own"]["white_count"] == 30

    asyncio.run(_run())
