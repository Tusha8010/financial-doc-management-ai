"""
services/document_service.py
Document management: upload, retrieve, delete, search by metadata.
File is saved to disk; metadata is persisted in PostgreSQL.
"""

import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User
from app.schemas import DocumentMetadataRequest, DocumentResponse
from loguru import logger

ALLOWED_MIME_TYPES = {"application/pdf", "text/plain", "text/csv"}
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv"}


def _validate_file(file: UploadFile) -> None:
    """Raise 400 if file type or size is not allowed."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )


async def save_upload_file(file: UploadFile, document_id: uuid.UUID) -> tuple[str, int]:
    """
    Stream file to disk under the uploads directory.

    Returns:
        (file_path_str, file_size_bytes)
    """
    suffix = Path(file.filename or "file.pdf").suffix.lower()
    filename = f"{document_id}{suffix}"
    dest_path = settings.upload_path / filename

    total_bytes = 0
    with open(dest_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):  # 1 MB chunks
            if total_bytes + len(chunk) > settings.max_file_size_bytes:
                out_file.close()
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
                )
            out_file.write(chunk)
            total_bytes += len(chunk)

    return str(dest_path), total_bytes


async def upload_document(
    db: AsyncSession,
    file: UploadFile,
    metadata: DocumentMetadataRequest,
    current_user: User,
) -> Document:
    """
    Save uploaded file and create a Document record in the database.
    Document is created with PENDING status (not yet indexed).
    """
    _validate_file(file)

    doc_id = uuid.uuid4()
    file_path, file_size = await save_upload_file(file, doc_id)

    document = Document(
        id=doc_id,
        title=metadata.title,
        company_name=metadata.company_name,
        document_type=DocumentType(metadata.document_type),
        description=metadata.description,
        original_filename=file.filename or "unknown",
        file_path=file_path,
        file_size_bytes=file_size,
        mime_type=file.content_type,
        status=DocumentStatus.PENDING,
        uploaded_by=current_user.id,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(f"Document uploaded: {document.id} - '{document.title}' by {current_user.email}")
    return document


async def get_document_by_id(db: AsyncSession, document_id: uuid.UUID) -> Document:
    """Fetch a single document or raise 404."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.is_active == True)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return doc


async def list_documents(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    current_user: Optional[User] = None,
) -> dict:
    """
    Return paginated list of all active documents.
    Clients only see documents from their own uploads.
    """
    query = select(Document).where(Document.is_active == True)

    # Clients only see their own documents
    if current_user and not current_user.has_permission("role:manage"):
        role_names = [r.name for r in current_user.roles]
        if "Client" in role_names and "Analyst" not in role_names and "Auditor" not in role_names:
            query = query.where(Document.uploaded_by == current_user.id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()

    return {"total": total, "documents": list(documents)}


async def search_documents(
    db: AsyncSession,
    title: Optional[str] = None,
    company_name: Optional[str] = None,
    document_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> dict:
    """Metadata-based document search using ILIKE (case-insensitive partial match)."""
    filters = [Document.is_active == True]

    if title:
        filters.append(Document.title.ilike(f"%{title}%"))
    if company_name:
        filters.append(Document.company_name.ilike(f"%{company_name}%"))
    if document_type:
        filters.append(Document.document_type == document_type)

    count_q = select(func.count()).where(*filters)
    total = (await db.execute(count_q)).scalar()

    result = await db.execute(
        select(Document)
        .where(*filters)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return {"total": total, "documents": list(docs)}


async def delete_document(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> None:
    """
    Soft-delete a document (sets is_active=False).
    The file on disk is NOT deleted to allow potential recovery.
    """
    doc = await get_document_by_id(db, document_id)
    doc.is_active = False
    await db.commit()
    logger.info(f"Document soft-deleted: {document_id}")


async def update_document_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status: DocumentStatus,
    chunk_count: int = 0,
) -> None:
    """Update indexing status and chunk count after RAG processing."""
    doc = await get_document_by_id(db, document_id)
    doc.status = status
    if chunk_count:
        doc.chunk_count = chunk_count
    await db.commit()
