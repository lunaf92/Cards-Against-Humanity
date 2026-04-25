"""User profile endpoint tests."""
from fastapi import status


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


def test_get_users_me(client):
    """Authenticated user can fetch own profile."""
    token = _register_and_get_access_token(client, "users_me_user")
    response = client.get("/users/me", headers=_auth_headers(token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == "users_me_user"


def test_patch_users_me_updates_username_and_password(client):
    """Authenticated user can update own profile fields."""
    token = _register_and_get_access_token(client, "users_update_user", "update@example.com")
    patch_response = client.patch(
        "/users/me",
        headers=_auth_headers(token),
        json={
            "username": "users_update_user_new",
            "password": "newsecurepass123",
        },
    )
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.json()["username"] == "users_update_user_new"

    login_response = client.post(
        "/auth/login",
        json={"username_or_email": "users_update_user_new", "password": "newsecurepass123"},
    )
    assert login_response.status_code == status.HTTP_200_OK