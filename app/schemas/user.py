"""User schemas for request/response validation."""
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

# Username must fit the DB column (String(50)); password capped at 72 to stay
# within bcrypt's effective input limit.
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72


class UserCreate(BaseModel):
    """User registration request."""
    username: str = Field(min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

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
    username: Optional[str] = Field(
        default=None, min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH
    )
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(
        default=None, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

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
