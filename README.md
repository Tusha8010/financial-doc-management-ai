# 📊 Financial Document Management System with Semantic Search (RAG)

A production-ready FastAPI application for storing, managing, and intelligently searching
financial documents using AI-powered semantic retrieval.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                   │
├──────────────┬──────────────┬───────────┬───────────────┤
│  /auth       │  /documents  │  /rag     │  /roles       │
│  (JWT Auth)  │  (CRUD)      │  (Search) │  (RBAC)       │
├──────────────┴──────────────┴───────────┴───────────────┤
│                    Service Layer                         │
│  auth_service │ document_service │ rag_service │ role_service │
├──────────────┬──────────────────────────────────────────┤
│  PostgreSQL  │              FAISS Vector DB              │
│  (Metadata)  │         (Embeddings + Chunks)             │
└──────────────┴──────────────────────────────────────────┘
```

### RAG Pipeline

```
PDF Upload
    │
    ▼
Text Extraction (pdfplumber → PyMuPDF fallback)
    │
    ▼
Chunking (500-word sliding window, 50-word overlap)
    │
    ▼
Embeddings (all-MiniLM-L6-v2, 384-dim, L2-normalized)
    │
    ▼
FAISS IndexFlatIP (cosine similarity via inner product)
    │
    ▼
Semantic Search Query
    │
    ├─► FAISS retrieves Top 20 candidates
    │
    └─► Reranker (0.7×semantic + 0.3×keyword overlap)
            │
            ▼
        Top 5 Results with scores
```

---

## 📁 Project Structure

```
financial_doc_system/
├── app/
│   ├── main.py                  # FastAPI app factory + lifespan
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (env vars)
│   │   ├── security.py          # JWT + bcrypt
│   │   └── logging.py           # Loguru setup
│   ├── db/
│   │   ├── base.py              # DeclarativeBase + TimestampMixin
│   │   └── session.py           # Async engine + get_db dependency
│   ├── models/
│   │   ├── user.py              # User ORM model
│   │   ├── role.py              # Role + Permission ORM models
│   │   └── document.py          # Document ORM model
│   ├── schemas/
│   │   └── __init__.py          # All Pydantic request/response schemas
│   ├── api/
│   │   ├── auth.py              # POST /auth/register, /auth/login
│   │   ├── documents.py         # CRUD /documents/*
│   │   ├── rag.py               # POST /rag/search, /rag/index-document
│   │   └── roles.py             # POST /roles/create, /users/assign-role
│   ├── services/
│   │   ├── auth_service.py      # Auth logic + FastAPI dependencies
│   │   ├── document_service.py  # Document CRUD business logic
│   │   ├── rag_service.py       # FAISS store + RAG pipeline
│   │   └── role_service.py      # Role/permission management
│   └── utils/
│       ├── text_extractor.py    # PDF/text extraction
│       ├── chunking.py          # Sliding window chunking
│       └── embeddings.py        # SentenceTransformer singleton
├── alembic/                     # DB migrations
├── .env                         # Environment variables
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🔐 Roles & Permissions

| Role     | Permissions                                                    |
|----------|----------------------------------------------------------------|
| Admin    | Full access to everything                                      |
| Analyst  | Upload, view, edit documents; index and search via RAG         |
| Auditor  | View and search documents; audit reports                       |
| Client   | View and search their own uploaded documents only              |

---

## ⚙️ Setup Instructions

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ running locally (or use Docker)
- Git

---

### Option A: Local Development Setup

#### 1. Clone and prepare
```bash
git clone <repo-url>
cd financial_doc_system
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configure environment
```bash
cp .env .env.local
# Edit .env with your database credentials:
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/financial_docs_db
# SECRET_KEY=your-very-long-random-secret-key-here
```

#### 3. Create the PostgreSQL database
```bash
psql -U postgres -c "CREATE DATABASE financial_docs_db;"
```

#### 4. Run the application
```bash
# Tables are auto-created on first startup (via init_db)
uvicorn app.main:app --reload --port 8000
```

The API will be live at: http://localhost:8000
Interactive docs: http://localhost:8000/docs

---

### Option B: Docker Compose (Recommended)

```bash
docker-compose up --build
```

This starts:
- PostgreSQL on port 5432
- FastAPI API on port 8000

---

### Option C: Production Migrations with Alembic

```bash
# Generate initial migration
alembic revision --autogenerate -m "initial schema"

# Apply migrations
alembic upgrade head

# Then start the server (without init_db auto-create)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🔑 Database Schema

```sql
-- Users
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    username    VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name   VARCHAR(255),
    is_active   BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Permissions
CREATE TABLE permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) UNIQUE NOT NULL,   -- e.g. 'document:upload'
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Roles
CREATE TABLE roles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(50) UNIQUE NOT NULL,    -- Admin, Analyst, Auditor, Client
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Role <-> Permission (many-to-many)
CREATE TABLE role_permissions (
    role_id       UUID REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID REFERENCES permissions(id) ON DELETE CASCADE
);

-- User <-> Role (many-to-many)
CREATE TABLE user_roles (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID REFERENCES roles(id) ON DELETE CASCADE
);

-- Documents
CREATE TABLE documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title             VARCHAR(500) NOT NULL,
    company_name      VARCHAR(255) NOT NULL,
    document_type     VARCHAR(50) NOT NULL,     -- invoice, report, contract, etc.
    description       TEXT,
    original_filename VARCHAR(500) NOT NULL,
    file_path         VARCHAR(1000) NOT NULL,
    file_size_bytes   INTEGER DEFAULT 0,
    mime_type         VARCHAR(100),
    status            VARCHAR(20) DEFAULT 'pending',  -- pending/indexing/indexed/failed
    chunk_count       INTEGER DEFAULT 0,
    is_active         BOOLEAN DEFAULT TRUE,
    uploaded_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 📡 API Reference

### Authentication

#### Register
```http
POST /auth/register
Content-Type: application/json

{
  "email": "analyst@acme.com",
  "username": "john_analyst",
  "password": "SecurePass123!",
  "full_name": "John Smith"
}
```

#### Login
```http
POST /auth/login
Content-Type: application/json

{
  "email": "analyst@acme.com",
  "password": "SecurePass123!"
}

Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

### Role Management (Admin only)

#### Create Role
```http
POST /roles/create
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "name": "SeniorAnalyst",
  "description": "Senior financial analyst with delete access",
  "permission_names": ["document:upload", "document:view", "document:edit", "document:delete", "rag:search"]
}
```

#### Assign Role to User
```http
POST /users/assign-role
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role_name": "Analyst"
}
```

#### Get User Roles
```http
GET /users/{user_id}/roles
Authorization: Bearer <token>
```

#### Get User Permissions
```http
GET /users/{user_id}/permissions
Authorization: Bearer <token>
```

---

### Document Management

#### Upload Document
```http
POST /documents/upload
Authorization: Bearer <analyst_token>
Content-Type: multipart/form-data

file=@Q3_financial_report.pdf
title=Q3 2024 Financial Report
company_name=Acme Corporation
document_type=report
description=Third quarter earnings and financial analysis
```

#### List Documents
```http
GET /documents?skip=0&limit=20
Authorization: Bearer <token>
```

#### Get Document by ID
```http
GET /documents/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <token>
```

#### Search by Metadata
```http
GET /documents/search?company_name=Acme&document_type=report&skip=0&limit=10
Authorization: Bearer <token>
```

#### Delete Document
```http
DELETE /documents/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <admin_token>
```

---

### RAG / Semantic Search

#### Index Document
```http
POST /rag/index-document
Authorization: Bearer <analyst_token>
Content-Type: application/json

{
  "document_id": "550e8400-e29b-41d4-a716-446655440000"
}

Response:
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "indexed",
  "chunks_indexed": 42,
  "message": "Successfully indexed 42 chunks"
}
```

#### Semantic Search
```http
POST /rag/search
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "financial risk related to high debt ratio",
  "top_k": 5,
  "company_name": "Acme Corporation",
  "document_type": "report"
}

Response:
{
  "query": "financial risk related to high debt ratio",
  "total_retrieved": 5,
  "results": [
    {
      "document_id": "550e8400-...",
      "document_title": "Q3 2024 Financial Report",
      "company_name": "Acme Corporation",
      "document_type": "report",
      "chunk_text": "The company's debt-to-equity ratio increased to 2.4x in Q3...",
      "chunk_index": 7,
      "similarity_score": 0.8923,
      "relevance_score": 0.9145
    }
  ]
}
```

#### Remove Document Embeddings
```http
DELETE /rag/remove-document/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <analyst_token>
```

#### Get Document Context
```http
GET /rag/context/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <token>
```

---

## 🧪 Running Tests

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## 📦 Environment Variables Reference

| Variable                    | Default                        | Description                        |
|-----------------------------|--------------------------------|------------------------------------|
| `DATABASE_URL`              | postgresql+asyncpg://...       | Async PostgreSQL connection string |
| `SECRET_KEY`                | (required)                     | JWT signing secret (min 32 chars)  |
| `ALGORITHM`                 | HS256                          | JWT algorithm                      |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60                           | Token expiry in minutes            |
| `UPLOAD_DIR`                | ./uploads                      | File storage directory             |
| `MAX_FILE_SIZE_MB`          | 50                             | Maximum upload file size           |
| `FAISS_INDEX_PATH`          | ./faiss_index                  | FAISS index directory              |
| `EMBEDDING_MODEL`           | all-MiniLM-L6-v2               | SentenceTransformer model name     |
| `CHUNK_SIZE`                | 500                            | Target words per chunk             |
| `CHUNK_OVERLAP`             | 50                             | Overlap words between chunks       |
| `LOG_LEVEL`                 | INFO                           | Logging level                      |
| `DEBUG`                     | False                          | Enable SQL echo and auto-reload    |

---

## 🚀 Production Checklist

- [ ] Change `SECRET_KEY` to a strong random value (`openssl rand -hex 32`)
- [ ] Set `DEBUG=false`
- [ ] Use Alembic for migrations instead of `init_db()`
- [ ] Configure proper CORS origins (not `*`)
- [ ] Use a reverse proxy (nginx) in front of uvicorn
- [ ] Set up SSL/TLS termination
- [ ] Replace FAISS with Qdrant for distributed vector storage
- [ ] Replace keyword reranker with a cross-encoder model
- [ ] Add rate limiting middleware
- [ ] Set up structured log aggregation (ELK / Loki)
