"""Authentication endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_token
from app.services.auth import AuthService
from app.schemas.auth import LoginRequest, TokenPair, RefreshTokenRequest, TokenResponse
from app.schemas.user import UserCreate, UserResponse
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        409: {"description": "Username or email already taken"},
        422: {"description": "Invalid input"},
    },
)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user and return JWT token pair."""
    # Check if user already exists
    existing = await AuthService.get_user_by_username_or_email(db, user_data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    if user_data.email:
        existing_email = await AuthService.get_user_by_username_or_email(db, user_data.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

    # Register user
    user = await AuthService.register_user(
        db, user_data.username, user_data.email or "", user_data.password
    )
    await db.commit()

    # Create tokens
    tokens = await AuthService.create_tokens(user.id)
    return TokenPair(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Login user",
    responses={
        401: {"description": "Invalid credentials"},
    },
)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token pair."""
    user = await AuthService.verify_user_password(
        db, credentials.username_or_email, credentials.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = await AuthService.create_tokens(user.id)
    return TokenPair(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh_token(
    request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)
):
    """Exchange refresh token for new access token."""
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Check if token is revoked
    is_revoked = await AuthService.is_token_revoked(db, request.refresh_token)
    if is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Create new access token
    new_access_token = (await AuthService.create_tokens(user_id))["access_token"]
    return TokenResponse(access_token=new_access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout user",
)
async def logout(
    authorization: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Revoke user tokens server-side."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    # Extract token from Bearer scheme
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )

    token = parts[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    await AuthService.revoke_token(db, user_id, token)
    await db.commit()
    return None
