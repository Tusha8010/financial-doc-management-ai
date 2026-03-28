"""
api/roles.py
Role and permission management endpoints.
All routes require Admin-level access (role:manage permission).
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas import (
    AssignRoleRequest,
    MessageResponse,
    PermissionResponse,
    RoleCreateRequest,
    RoleResponse,
    UserPermissionsResponse,
    UserResponse,
)
from app.services.auth_service import get_current_user, require_permission
from app.services.role_service import (
    assign_role_to_user,
    create_role,
    get_all_permissions,
    get_user_roles,
)

router = APIRouter(tags=["Roles & Permissions"])


# ─── Role Management ──────────────────────────────────────────────────────────

@router.post(
    "/roles/create",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new role (Admin only)",
    dependencies=[Depends(require_permission("role:manage"))],
)
async def create_new_role(
    data: RoleCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a custom role and assign permissions to it.
    `permission_names` should be values like `document:upload`, `rag:search`.
    """
    return await create_role(db, data)


@router.get(
    "/permissions",
    response_model=List[PermissionResponse],
    summary="List all available permissions (Admin only)",
    dependencies=[Depends(require_permission("role:manage"))],
)
async def list_permissions(db: AsyncSession = Depends(get_db)):
    """Return every permission that can be assigned to roles."""
    return await get_all_permissions(db)


# ─── User Role Assignment ─────────────────────────────────────────────────────

@router.post(
    "/users/assign-role",
    response_model=UserResponse,
    summary="Assign a role to a user (Admin only)",
    dependencies=[Depends(require_permission("role:manage"))],
)
async def assign_role(
    data: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Assign an existing role to a user by user_id and role_name.
    If the user already has the role, this is a no-op.
    """
    return await assign_role_to_user(db, data)


@router.get(
    "/users/{user_id}/roles",
    response_model=UserResponse,
    summary="Get all roles assigned to a user",
)
async def get_roles_for_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return all roles assigned to a user.
    Admins can query any user; others can only query themselves.
    """
    if not current_user.has_permission("role:manage") and current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to view other users' roles")
    return await get_user_roles(db, user_id)


@router.get(
    "/users/{user_id}/permissions",
    response_model=UserPermissionsResponse,
    summary="View all effective permissions for a user",
)
async def get_permissions_for_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the flat list of all permissions a user holds (union of all role permissions).
    Admins can query any user; others can only query themselves.
    """
    if not current_user.has_permission("role:manage") and current_user.id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to view other users' permissions")

    user = await get_user_roles(db, user_id)
    return UserPermissionsResponse(
        user_id=user.id,
        username=user.username,
        permissions=sorted(user.permission_names),
    )
