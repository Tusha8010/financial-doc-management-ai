"""
services/auth_service.py
Authentication business logic: register, login, get current user.
All DB operations use async SQLAlchemy.
"""

import uuid
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.models.role import Role
from app.schemas import TokenData, UserRegisterRequest
from loguru import logger

# HTTP Bearer scheme for extracting JWT from Authorization header
bearer_scheme = HTTPBearer()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User)
        .where(User.email == email)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def register_user(db: AsyncSession, data: UserRegisterRequest) -> User:
    """
    Create a new user after checking for duplicate email/username.
    Auto-assigns the 'Client' role to every new user.
    """
    # Check duplicate email
    if await get_user_by_email(db, data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check duplicate username
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    await db.flush()  # Get the ID without committing

    # Auto-assign 'Client' role
    result = await db.execute(select(Role).where(Role.name == "Client"))
    client_role = result.scalar_one_or_none()
    if client_role:
        user.roles.append(client_role)

    await db.commit()
    await db.refresh(user)

    logger.info(f"New user registered: {user.email}")
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Verify credentials and return user, or None on failure."""
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    return user


def create_token_for_user(user: User) -> dict:
    """Issue a JWT token containing user ID and email."""
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ─── FastAPI Dependencies ─────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: decode JWT and return the authenticated User.
    Raises 401 if token is missing, invalid, or expired.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        )

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def require_permission(permission: str):
    """
    Dependency factory: returns a dependency that checks a specific permission.

    Usage:
        @router.post("/...", dependencies=[Depends(require_permission("document:upload"))])
    """
    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return current_user

    return _checker


def require_admin():
    """Shorthand dependency: user must have 'role:manage' permission (Admin)."""
    return require_permission("role:manage")
