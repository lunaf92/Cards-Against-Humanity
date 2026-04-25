"""Authentication schemas for request/response validation."""
from pydantic import BaseModel
from typing import Optional


class TokenPair(BaseModel):
    """JWT token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer"
            }
        }


class LoginRequest(BaseModel):
    """User login request."""
    username_or_email: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username_or_email": "player1",
                "password": "securepassword123"
            }
        }


class RefreshTokenRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
            }
        }


class TokenResponse(BaseModel):
    """Token response with new access token."""
    access_token: str
    token_type: str = "bearer"

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "token_type": "bearer"
            }
        }
