"""User schemas for request/response validation."""
from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    """User registration request."""
    username: str
    email: Optional[EmailStr] = None
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "player1",
                "email": "player1@example.com",
                "password": "securepassword123"
            }
        }


class UserUpdate(BaseModel):
    """User profile update request."""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "username": "newusername",
                "email": "newemail@example.com"
            }
        }


class UserResponse(BaseModel):
    """User profile response."""
    id: UUID
    username: str
    email: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
