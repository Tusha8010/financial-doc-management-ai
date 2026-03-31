"""
api/auth.py
Authentication endpoints: register and login.
Returns JWT tokens for use in Bearer Authorization headers.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas import TokenResponse, UserRegisterRequest, UserLoginRequest, UserResponse
from app.services.auth_service import register_user, authenticate_user, create_token_for_user
from fastapi import HTTPException

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account.
    - Email and username must be unique.
    - Password is bcrypt-hashed before storage.
    - New users are auto-assigned the 'Client' role.
    """
    user = await register_user(db, data)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT token",
)
async def login(
    data: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password.
    Returns a Bearer JWT token valid for the configured expiry window.
    """
    user = await authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return create_token_for_user(user)
