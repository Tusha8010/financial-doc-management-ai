"""
api/rag.py
RAG (Retrieval-Augmented Generation) endpoints.
Index documents into FAISS, perform semantic search, retrieve context.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas import (
    DocumentContextResponse,
    IndexDocumentRequest,
    IndexDocumentResponse,
    MessageResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
    ChunkResult,
)
from app.services.auth_service import get_current_user, require_permission
from app.services.rag_service import (
    get_document_context,
    index_document,
    remove_document_embeddings,
    semantic_search,
)

router = APIRouter(prefix="/rag", tags=["RAG & Semantic Search"])


@router.post(
    "/index-document",
    response_model=IndexDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Index a document into the vector database",
)
async def index_doc(
    data: IndexDocumentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag:index")),
):
    """
    Trigger the full RAG indexing pipeline for a document:
    1. Extract text (PDF or plain text)
    2. Split into overlapping chunks (~500 words each)
    3. Generate embeddings using `all-MiniLM-L6-v2`
    4. Store vectors + metadata in FAISS

    The document status changes: PENDING → INDEXING → INDEXED

    Requires: `rag:index` permission (Analyst, Admin).
    """
    result = await index_document(db, data.document_id)
    return IndexDocumentResponse(**result)


@router.delete(
    "/remove-document/{document_id}",
    response_model=MessageResponse,
    summary="Remove document embeddings from the vector database",
)
async def remove_embeddings(
    document_id: uuid.UUID,
    current_user: User = Depends(require_permission("rag:index")),
):
    """
    Remove all vector embeddings for a document from FAISS.
    This does **not** delete the document record or file — use `DELETE /documents/{id}` for that.

    Requires: `rag:index` permission (Analyst, Admin).
    """
    removed = await remove_document_embeddings(document_id)
    return MessageResponse(message=f"Removed {removed} embeddings for document {document_id}")


@router.post(
    "/search",
    response_model=SemanticSearchResponse,
    summary="Perform AI-powered semantic search",
)
async def semantic_search_endpoint(
    data: SemanticSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag:search")),
):
    """
    Execute the full semantic search pipeline:

    ```
    Query → Embedding → FAISS (top 20) → Reranking → Top 5 Results
    ```

    **Example query:** `"financial risk related to high debt ratio"`

    Optional filters:
    - `company_name`: Restrict results to a specific company.
    - `document_type`: Filter by document category (e.g., `report`, `invoice`).

    Results include:
    - Matching chunk text with source document info
    - Cosine similarity score (from FAISS)
    - Final relevance score (after reranking)

    Requires: `rag:search` permission (Analyst, Auditor, Admin).
    """
    result = await semantic_search(
        query=data.query,
        top_k=data.top_k,
        company_name=data.company_name,
        document_type=data.document_type,
        db=db,
    )

    # Cast results to schema
    chunk_results = [ChunkResult(**r) for r in result["results"]]

    return SemanticSearchResponse(
        query=result["query"],
        total_retrieved=result["total_retrieved"],
        results=chunk_results,
    )


@router.get(
    "/context/{document_id}",
    response_model=DocumentContextResponse,
    summary="Retrieve all indexed chunks for a document",
)
async def get_context(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("rag:search")),
):
    """
    Return all stored text chunks for a specific document.
    Useful for inspecting what was indexed or for building full-document RAG context.

    Requires: `rag:search` permission.
    """
    from app.services.document_service import get_document_by_id
    doc = await get_document_by_id(db, document_id)
    context = await get_document_context(document_id)

    return DocumentContextResponse(
        document_id=document_id,
        title=doc.title,
        company_name=doc.company_name,
        chunks=context["chunks"],
        total_chunks=context["total_chunks"],
    )
