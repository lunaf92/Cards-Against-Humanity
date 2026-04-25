"""Authentication service with server-side token revocation."""
from uuid import uuid4, UUID
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models import User, TokenRevocation
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token


class AuthService:
    """Service for user authentication and token management."""

    @staticmethod
    async def register_user(db: AsyncSession, username: str, email: str, password: str) -> User:
        """Register a new user with hashed password."""
        user = User(
            username=username,
            email=email if email else None,
            password_hash=hash_password(password),
        )
        db.add(user)
        await db.flush()
        return user

    @staticmethod
    async def get_user_by_username_or_email(
        db: AsyncSession, username_or_email: str
    ) -> User | None:
        """Retrieve user by username or email."""
        result = await db.execute(
            select(User).where(
                (User.username == username_or_email) | (User.email == username_or_email)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def verify_user_password(db: AsyncSession, username_or_email: str, password: str) -> User | None:
        """Verify user credentials."""
        user = await AuthService.get_user_by_username_or_email(db, username_or_email)
        if user and verify_password(password, user.password_hash):
            return user
        return None

    @staticmethod
    async def create_tokens(user_id: UUID) -> dict:
        """Generate access and refresh token pair."""
        token_jti = str(uuid4())
        access_token = create_access_token({"sub": str(user_id), "jti": token_jti})
        refresh_token = create_refresh_token({"sub": str(user_id), "jti": token_jti})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_jti": token_jti,
        }

    @staticmethod
    async def revoke_token(db: AsyncSession, user_id: UUID, token: str) -> None:
        """Revoke a token server-side by storing its JTI."""
        payload = decode_token(token)
        if not payload:
            return

        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return

        revocation = TokenRevocation(
            user_id=user_id,
            token_jti=jti,
            expires_at=datetime.fromtimestamp(exp, UTC),
        )
        db.add(revocation)
        await db.flush()

    @staticmethod
    async def is_token_revoked(db: AsyncSession, token: str) -> bool:
        """Check if token has been revoked server-side."""
        payload = decode_token(token)
        if not payload:
            return True

        jti = payload.get("jti")
        if not jti:
            return True

        result = await db.execute(select(TokenRevocation).where(TokenRevocation.token_jti == jti))
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def cleanup_expired_revocations(db: AsyncSession) -> None:
        """Clean up expired token revocation records."""
        await db.execute(
            delete(TokenRevocation).where(TokenRevocation.expires_at < datetime.now(UTC))
        )
        await db.flush()
