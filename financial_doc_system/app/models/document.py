"""
models/document.py
Document ORM model storing financial document metadata.
The actual file is stored on disk; embeddings in FAISS.
"""

import uuid
import enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class DocumentType(str, enum.Enum):
    """Allowed financial document types."""
    INVOICE = "invoice"
    REPORT = "report"
    CONTRACT = "contract"
    AGREEMENT = "agreement"
    FINANCIAL_STATEMENT = "financial_statement"
    AUDIT_REPORT = "audit_report"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    """Processing status of a document."""
    PENDING = "pending"       # Uploaded, not yet indexed
    INDEXING = "indexing"     # Being embedded
    INDEXED = "indexed"       # Ready for semantic search
    FAILED = "failed"         # Indexing failed


class Document(Base, TimestampMixin):
    """
    Financial document metadata.
    File content lives at `file_path`; embeddings are stored in FAISS
    with `faiss_index_id` as the reference key.
    """
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType), nullable=False, default=DocumentType.OTHER
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # File storage
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=True)

    # Processing
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Owner FK
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationship back to user
    owner: Mapped[Optional["User"]] = relationship("User", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document {self.title} ({self.document_type})>"
