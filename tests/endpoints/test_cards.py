"""Cards endpoint tests."""
import asyncio
from uuid import UUID

from fastapi import status

from app.models import Card, Room, RoomPlayer


def _register_and_get_access_token(client, username: str, email: str | None = None) -> str:
    """Create a user through public API and return access token."""
    payload = {
        "username": username,
        "password": "securepass123",
    }
    if email:
        payload["email"] = email

    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    """Build bearer auth headers for protected endpoints."""
    return {"Authorization": f"Bearer {token}"}


def test_create_and_list_my_cards(client):
    """Player can create and list custom cards."""
    token = _register_and_get_access_token(client, "cards_user")
    create_response = client.post(
        "/cards",
        headers=_auth_headers(token),
        json={"type": "white", "text": "Test white card"},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    assert created["is_default"] is False
    assert created["owner_id"] is not None

    mine_response = client.get("/cards/mine", headers=_auth_headers(token))
    assert mine_response.status_code == status.HTTP_200_OK
    mine = mine_response.json()
    assert len(mine) == 1
    assert mine[0]["text"] == "Test white card"


def test_list_default_cards_pagination(client, test_db):
    """Default card listing returns paginated response fields."""
    async def _seed_default_cards():
        async with test_db() as session:
            session.add_all(
                [
                    Card(type="white", text="Default one", pick=1, is_default=True),
                    Card(type="black", text="Default two", pick=1, is_default=True),
                    Card(type="white", text="Custom hidden", pick=1, is_default=False),
                ]
            )
            await session.commit()

    asyncio.run(_seed_default_cards())

    response = client.get("/cards/default?page=1&page_size=2")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_card_mutation_blocked_while_in_active_game(client, test_db):
    """Card update/delete is blocked for players in active games."""
    token = _register_and_get_access_token(client, "cards_guard_user")
    create_card_response = client.post(
        "/cards",
        headers=_auth_headers(token),
        json={"type": "black", "text": "Prompt _", "pick": 1},
    )
    assert create_card_response.status_code == status.HTTP_201_CREATED
    card_id = create_card_response.json()["id"]

    user_response = client.get("/users/me", headers=_auth_headers(token))
    user_id = UUID(user_response.json()["id"])

    async def _seed_active_room():
        async with test_db() as session:
            room = Room(
                code="ABC123",
                host_id=user_id,
                room_kind="private",
                status="in_progress",
                max_players=10,
                winning_score=8,
                round_timer_seconds=90,
                card_pool_mode="default_only",
            )
            session.add(room)
            await session.flush()

            session.add(
                RoomPlayer(
                    room_id=room.id,
                    player_id=user_id,
                    join_order=1,
                    score=0,
                    is_connected=True,
                )
            )
            await session.commit()

    asyncio.run(_seed_active_room())

    patch_response = client.patch(
        f"/cards/{card_id}",
        headers=_auth_headers(token),
        json={"text": "Updated prompt _"},
    )
    assert patch_response.status_code == status.HTTP_409_CONFLICT

    delete_response = client.delete(f"/cards/{card_id}", headers=_auth_headers(token))
    assert delete_response.status_code == status.HTTP_409_CONFLICT