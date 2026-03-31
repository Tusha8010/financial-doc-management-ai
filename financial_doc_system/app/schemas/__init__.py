"""
schemas/__init__.py
Pydantic v2 request/response schemas for all API endpoints.
Grouped by domain: Auth, User, Role, Document, RAG.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ═══════════════════════════════════════════════════════════
# AUTH SCHEMAS
# ═══════════════════════════════════════════════════════════

class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    """Decoded JWT payload."""
    sub: Optional[str] = None  # user id as string
    email: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# PERMISSION SCHEMAS
# ═══════════════════════════════════════════════════════════

class PermissionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════
# ROLE SCHEMAS
# ═══════════════════════════════════════════════════════════

class RoleCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    permission_names: List[str] = Field(default_factory=list)


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    permissions: List[PermissionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignRoleRequest(BaseModel):
    user_id: uuid.UUID
    role_name: str


# ═══════════════════════════════════════════════════════════
# USER SCHEMAS
# ═══════════════════════════════════════════════════════════

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    roles: List[RoleResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPermissionsResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    permissions: List[str]


# ═══════════════════════════════════════════════════════════
# DOCUMENT SCHEMAS
# ═══════════════════════════════════════════════════════════

class DocumentMetadataRequest(BaseModel):
    """Extra metadata submitted alongside the file upload form."""
    title: str = Field(..., min_length=1, max_length=500)
    company_name: str = Field(..., min_length=1, max_length=255)
    document_type: str = Field(..., description="invoice|report|contract|agreement|financial_statement|audit_report|other")
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, v: str) -> str:
        allowed = {"invoice", "report", "contract", "agreement",
                   "financial_statement", "audit_report", "other"}
        if v not in allowed:
            raise ValueError(f"document_type must be one of {allowed}")
        return v


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    company_name: str
    document_type: str
    description: Optional[str]
    original_filename: str
    file_size_bytes: int
    status: str
    chunk_count: int
    uploaded_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentResponse]


class DocumentSearchParams(BaseModel):
    """Query params for metadata-based search."""
    title: Optional[str] = None
    company_name: Optional[str] = None
    document_type: Optional[str] = None
    skip: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


# ═══════════════════════════════════════════════════════════
# RAG / SEMANTIC SEARCH SCHEMAS
# ═══════════════════════════════════════════════════════════

class IndexDocumentRequest(BaseModel):
    document_id: uuid.UUID


class IndexDocumentResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    chunks_indexed: int
    message: str


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="Natural language search query")
    top_k: int = Field(5, ge=1, le=20, description="Number of results to return after reranking")
    company_name: Optional[str] = Field(None, description="Filter results by company")
    document_type: Optional[str] = Field(None, description="Filter by document type")


class ChunkResult(BaseModel):
    document_id: uuid.UUID
    document_title: str
    company_name: str
    document_type: str
    chunk_text: str
    chunk_index: int
    similarity_score: float
    relevance_score: float  # After reranking


class SemanticSearchResponse(BaseModel):
    query: str
    total_retrieved: int
    results: List[ChunkResult]


class DocumentContextResponse(BaseModel):
    document_id: uuid.UUID
    title: str
    company_name: str
    chunks: List[dict]
    total_chunks: int


# ═══════════════════════════════════════════════════════════
# GENERIC RESPONSE
# ═══════════════════════════════════════════════════════════

class MessageResponse(BaseModel):
    message: str
    success: bool = True
