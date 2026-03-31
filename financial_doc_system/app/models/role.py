"""
models/role.py
Role and Permission ORM models with many-to-many relationship.
Roles: Admin, Analyst, Auditor, Client
"""

import uuid
from typing import List, TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User

# ─── Association Tables ───────────────────────────────────────────────────────

# Many-to-many: Role ↔ Permission
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE")),
)

# Many-to-many: User ↔ Role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")),
)


# ─── Permission Model ─────────────────────────────────────────────────────────

class Permission(Base, TimestampMixin):
    """
    Granular permission (e.g. 'document:upload', 'document:delete').
    Assigned to roles, not users directly.
    """
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


# ─── Role Model ───────────────────────────────────────────────────────────────

class Role(Base, TimestampMixin):
    """
    User role (Admin, Analyst, Auditor, Client).
    Each role has a set of permissions.
    """
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    permissions: Mapped[List[Permission]] = relationship(
        Permission, secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


# ─── Default Role/Permission Definitions ─────────────────────────────────────

DEFAULT_PERMISSIONS = [
    {"name": "document:upload",   "description": "Upload new documents"},
    {"name": "document:view",     "description": "View documents"},
    {"name": "document:edit",     "description": "Edit document metadata"},
    {"name": "document:delete",   "description": "Delete documents"},
    {"name": "document:search",   "description": "Search documents semantically"},
    {"name": "rag:index",         "description": "Index documents into vector DB"},
    {"name": "rag:search",        "description": "Perform RAG semantic search"},
    {"name": "user:manage",       "description": "Create and manage users"},
    {"name": "role:manage",       "description": "Create and assign roles"},
    {"name": "report:audit",      "description": "Review and audit documents"},
]

DEFAULT_ROLES = {
    "Admin": [
        "document:upload", "document:view", "document:edit", "document:delete",
        "document:search", "rag:index", "rag:search", "user:manage", "role:manage",
        "report:audit",
    ],
    "Analyst": [
        "document:upload", "document:view", "document:edit",
        "document:search", "rag:index", "rag:search",
    ],
    "Auditor": [
        "document:view", "document:search", "rag:search", "report:audit",
    ],
    "Client": [
        "document:view", "document:search",
    ],
}
