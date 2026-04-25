"""Authentication endpoint tests."""
import pytest
from fastapi import status


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"


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
