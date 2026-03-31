"""
api/documents.py
Financial document management endpoints.
Upload, retrieve, search (by metadata), and delete documents.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas import (
    DocumentListResponse,
    DocumentMetadataRequest,
    DocumentResponse,
    MessageResponse,
)
from app.services.auth_service import get_current_user, require_permission
from app.services.document_service import (
    delete_document,
    get_document_by_id,
    list_documents,
    search_documents,
    upload_document,
)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a financial document",
)
async def upload(
    # File upload (multipart/form-data)
    file: UploadFile = File(..., description="PDF or text file to upload"),
    # Metadata fields as form fields alongside the file
    title: str = Form(..., min_length=1, max_length=500),
    company_name: str = Form(..., min_length=1, max_length=255),
    document_type: str = Form(..., description="invoice|report|contract|agreement|financial_statement|audit_report|other"),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document:upload")),
):
    """
    Upload a financial document (PDF or plain text).

    The file is stored on disk; metadata is persisted in PostgreSQL.
    Document status starts as **PENDING** — call `POST /rag/index-document`
    to generate embeddings and enable semantic search.

    Requires: `document:upload` permission (Analyst, Admin).
    """
    metadata = DocumentMetadataRequest(
        title=title,
        company_name=company_name,
        document_type=document_type,
        description=description,
    )
    return await upload_document(db, file, metadata, current_user)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents",
)
async def list_all_documents(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document:view")),
):
    """
    Return a paginated list of documents.
    - Admins/Analysts/Auditors see all documents.
    - Clients only see their own uploads.

    Requires: `document:view` permission.
    """
    return await list_documents(db, skip=skip, limit=limit, current_user=current_user)


@router.get(
    "/search",
    response_model=DocumentListResponse,
    summary="Search documents by metadata",
)
async def search_by_metadata(
    title: Optional[str] = Query(None, description="Partial title match"),
    company_name: Optional[str] = Query(None, description="Partial company name match"),
    document_type: Optional[str] = Query(None, description="Exact document type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document:search")),
):
    """
    Search documents using metadata filters (title, company, type).
    This is a **metadata search** — for AI-powered semantic search use `POST /rag/search`.

    Requires: `document:search` permission.
    """
    return await search_documents(
        db,
        title=title,
        company_name=company_name,
        document_type=document_type,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Retrieve document details",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document:view")),
):
    """
    Fetch metadata for a single document by its UUID.

    Requires: `document:view` permission.
    """
    return await get_document_by_id(db, document_id)


@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    summary="Delete a document",
)
async def remove_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document:delete")),
):
    """
    Soft-delete a document (marks `is_active=False`).
    The file on disk is retained. Embeddings remain in FAISS but are filtered
    from search results via metadata checks.

    To fully remove embeddings, call `DELETE /rag/remove-document/{id}` first.

    Requires: `document:delete` permission (Admin only).
    """
    await delete_document(db, document_id)
    return MessageResponse(message=f"Document {document_id} deleted successfully")
