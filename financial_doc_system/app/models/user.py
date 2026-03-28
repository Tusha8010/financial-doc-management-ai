"""
models/user.py
User ORM model with bcrypt-hashed password and role relationships.
"""

import uuid
from typing import List, TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.role import user_roles

if TYPE_CHECKING:
    from app.models.role import Role
    from app.models.document import Document


class User(Base, TimestampMixin):
    """
    Application user.
    Authentication via JWT; authorization via assigned roles.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="selectin"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="owner", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"

    @property
    def permission_names(self) -> set[str]:
        """Return flat set of all permission names across all assigned roles."""
        perms = set()
        for role in self.roles:
            for perm in role.permissions:
                perms.add(perm.name)
        return perms

    def has_permission(self, permission: str) -> bool:
        """Check if this user holds a specific permission."""
        if self.is_superuser:
            return True
        return permission in self.permission_names
