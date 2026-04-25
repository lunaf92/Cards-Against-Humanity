"""User profile endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return profile for the authenticated user."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse, summary="Update current user profile")
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update username, email, or password for the authenticated user."""
    if payload.username and payload.username != current_user.username:
        username_taken = await db.execute(
            select(User).where(User.username == payload.username, User.id != current_user.id)
        )
        if username_taken.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )
        current_user.username = payload.username

    if payload.email is not None and payload.email != current_user.email:
        email_taken = await db.execute(
            select(User).where(User.email == payload.email, User.id != current_user.id)
        )
        if email_taken.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        current_user.email = payload.email

    if payload.password:
        current_user.password_hash = hash_password(payload.password)

    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
