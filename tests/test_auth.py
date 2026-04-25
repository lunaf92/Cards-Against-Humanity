"""Authentication endpoint tests."""
import pytest
from fastapi import status
from app.routers import health as health_router


def test_health_check(client, monkeypatch):
    """Test health check endpoint."""
    class _FakeRedisClient:
        async def ping(self):
            return True

        async def close(self):
            return None

    monkeypatch.setattr(
        health_router.redis,
        "from_url",
        lambda *_args, **_kwargs: _FakeRedisClient(),
    )

    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"


def test_register_user(client):
    """Test user registration."""
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepass123"
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_user_without_email(client):
    """Test registration with username/password only (email optional)."""
    payload = {
        "username": "testuser_no_email",
        "password": "securepass123"
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_username(client):
    """Test registration fails with duplicate username."""
    payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepass123"
    }
    # First registration
    client.post("/auth/register", json=payload)

    # Duplicate registration
    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_409_CONFLICT


def test_login_user(client):
    """Test user login."""
    # Register first
    register_payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepass123"
    }
    client.post("/auth/register", json=register_payload)

    # Login
    login_payload = {
        "username_or_email": "testuser",
        "password": "securepass123"
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_user_with_email_identifier(client):
    """Test login using email via username_or_email field."""
    register_payload = {
        "username": "email_login_user",
        "email": "email_login_user@example.com",
        "password": "securepass123"
    }
    register_response = client.post("/auth/register", json=register_payload)
    assert register_response.status_code == status.HTTP_201_CREATED

    login_payload = {
        "username_or_email": "email_login_user@example.com",
        "password": "securepass123"
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_invalid_credentials(client):
    """Test login fails with invalid credentials."""
    login_payload = {
        "username_or_email": "nonexistent",
        "password": "wrongpassword"
    }
    response = client.post("/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token(client):
    """Test token refresh."""
    # Register and get tokens
    register_payload = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "securepass123"
    }
    register_response = client.post("/auth/register", json=register_payload)
    refresh_token = register_response.json()["refresh_token"]

    # Refresh
    refresh_payload = {"refresh_token": refresh_token}
    response = client.post("/auth/refresh", json=refresh_payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
