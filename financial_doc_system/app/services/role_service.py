"""
services/role_service.py
Role and permission management: create roles, assign to users, seed defaults.
"""

import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Permission, Role, DEFAULT_PERMISSIONS, DEFAULT_ROLES, user_roles
from app.models.user import User
from app.schemas import AssignRoleRequest, RoleCreateRequest
from loguru import logger


async def seed_roles_and_permissions(db: AsyncSession) -> None:
    """
    Idempotently seed default permissions and roles into the database.
    Called once on application startup.
    """
    # Seed permissions
    for perm_data in DEFAULT_PERMISSIONS:
        result = await db.execute(
            select(Permission).where(Permission.name == perm_data["name"])
        )
        if not result.scalar_one_or_none():
            db.add(Permission(**perm_data))

    await db.flush()

    # Seed roles and attach permissions
    for role_name, perm_names in DEFAULT_ROLES.items():
        result = await db.execute(select(Role).where(Role.name == role_name))
        role = result.scalar_one_or_none()

        if not role:
            role = Role(name=role_name, description=f"Default {role_name} role")
            db.add(role)
            await db.flush()

        # Attach permissions
        for pname in perm_names:
            result = await db.execute(select(Permission).where(Permission.name == pname))
            perm = result.scalar_one_or_none()
            if perm and perm not in role.permissions:
                role.permissions.append(perm)

    await db.commit()
    logger.info("Default roles and permissions seeded")


async def create_role(db: AsyncSession, data: RoleCreateRequest) -> Role:
    """Create a custom role with specified permissions."""
    result = await db.execute(select(Role).where(Role.name == data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{data.name}' already exists",
        )

    role = Role(name=data.name, description=data.description)
    db.add(role)
    await db.flush()

    for pname in data.permission_names:
        result = await db.execute(select(Permission).where(Permission.name == pname))
        perm = result.scalar_one_or_none()
        if not perm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Permission '{pname}' does not exist",
            )
        role.permissions.append(perm)

    await db.commit()
    await db.refresh(role)
    logger.info(f"Role created: {role.name}")
    return role


async def assign_role_to_user(db: AsyncSession, data: AssignRoleRequest) -> User:
    """Assign a named role to a user by ID."""
    result = await db.execute(
        select(User)
        .where(User.id == data.user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await db.execute(select(Role).where(Role.name == data.role_name))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Role '{data.role_name}' not found")

    if role not in user.roles:
        user.roles.append(role)
        await db.commit()
        logger.info(f"Assigned role '{role.name}' to user {user.email}")
    else:
        logger.info(f"User {user.email} already has role '{role.name}'")

    await db.refresh(user)
    return user


async def get_user_roles(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Fetch user with their roles eagerly loaded."""
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


async def get_all_permissions(db: AsyncSession) -> List[Permission]:
    """List all available permissions."""
    result = await db.execute(select(Permission).order_by(Permission.name))
    return list(result.scalars().all())
