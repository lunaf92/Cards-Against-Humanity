"""Deck endpoints: build, share, copy."""
import asyncio
from uuid import UUID

from fastapi import status

from app.models import Room, RoomDeck
from tests.endpoints.test_rooms import _auth_headers, _register_and_get_access_token


def _user(client, name):
    return _auth_headers(_register_and_get_access_token(client, name))


def test_build_share_and_copy_a_deck(client):
    owner, friend, stranger = _user(client, "deck_owner"), _user(client, "deck_friend"), _user(client, "deck_stranger")

    deck = client.post("/decks", headers=owner, json={"name": "Office jokes"}).json()
    assert deck["is_public"] is False and deck["is_owner"] and deck["share_code"] is None
    deck_id = deck["id"]

    black = client.post(f"/decks/{deck_id}/cards", headers=owner, json={"type": "black", "text": "___ and ___ walk into a bar."})
    assert black.status_code == status.HTTP_201_CREATED and black.json()["pick"] == 2
    white = client.post(f"/decks/{deck_id}/cards", headers=owner, json={"type": "white", "text": "  The  printer "}).json()
    assert white["text"] == "The printer"

    # Private decks are invisible to outsiders.
    assert client.get(f"/decks/{deck_id}", headers=stranger).status_code == status.HTTP_404_NOT_FOUND
    assert client.post(f"/decks/{deck_id}/copy", headers=stranger).status_code == status.HTTP_404_NOT_FOUND

    # The share link makes a co-editor, who can add cards and rename but not change visibility.
    code = client.post(f"/decks/{deck_id}/share", headers=owner).json()["share_code"]
    joined = client.post(f"/decks/join/{code.lower()}", headers=friend).json()
    assert joined["can_edit"] and not joined["is_owner"]
    assert client.post(f"/decks/{deck_id}/cards", headers=friend, json={"type": "white", "text": "Casual Friday"}).status_code == 201
    assert client.patch(f"/decks/{deck_id}", headers=friend, json={"name": "Office"}).json()["name"] == "Office"
    assert client.patch(f"/decks/{deck_id}", headers=friend, json={"is_public": True}).status_code == 403
    assert client.delete(f"/decks/{deck_id}", headers=friend).status_code == 403
    assert "Office" in {d["name"] for d in client.get("/decks", headers=friend).json()}

    detail = client.get(f"/decks/{deck_id}", headers=owner).json()
    assert [m["username"] for m in detail["members"]] == ["deck_friend"]
    assert (detail["black_count"], detail["white_count"]) == (1, 2)

    # Turning the link off stops new joins; the owner can still remove the friend.
    client.delete(f"/decks/{deck_id}/share", headers=owner)
    assert client.post(f"/decks/join/{code}", headers=stranger).status_code == 404
    friend_id = detail["members"][0]["user_id"]
    assert client.delete(f"/decks/{deck_id}/members/{friend_id}", headers=owner).status_code == 204
    assert client.get(f"/decks/{deck_id}", headers=friend).status_code == 404

    # Public decks can be viewed and copied by anyone; the copy is private and independent.
    client.patch(f"/decks/{deck_id}", headers=owner, json={"is_public": True})
    copy = client.post(f"/decks/{deck_id}/copy", headers=stranger).json()
    assert copy["is_owner"] and not copy["is_public"] and copy["copied_from_name"] == "Office"
    assert (copy["black_count"], copy["white_count"]) == (1, 2)
    card = next(c for c in copy["cards"] if c["text"] == "The printer")
    client.patch(f"/decks/{copy['id']}/cards/{card['id']}", headers=stranger, json={"text": "The fax machine"})
    original = {c["text"] for c in client.get(f"/decks/{deck_id}", headers=owner).json()["cards"]}
    assert "The printer" in original and "The fax machine" not in original

    assert client.delete(f"/decks/{deck_id}", headers=owner).status_code == 204
    assert client.get(f"/decks/{deck_id}", headers=owner).status_code == 404


def test_cards_cannot_be_deleted_while_their_deck_is_in_a_game(client, test_db):
    owner = _user(client, "busy_owner")
    deck = client.post("/decks", headers=owner, json={"name": "Busy"}).json()
    card = client.post(f"/decks/{deck['id']}/cards", headers=owner, json={"type": "white", "text": "x"}).json()

    async def _start_game():
        async with test_db() as session:
            room = Room(code="BUSY01", room_kind="private", status="in_progress")
            session.add(room)
            await session.flush()
            session.add(RoomDeck(room_id=room.id, deck_id=UUID(deck["id"])))
            await session.commit()

    asyncio.run(_start_game())
    assert client.delete(f"/decks/{deck['id']}/cards/{card['id']}", headers=owner).status_code == 409
    assert client.delete(f"/decks/{deck['id']}", headers=owner).status_code == 409
