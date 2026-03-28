"""
main.py
FastAPI application entry point.

Startup sequence:
  1. Configure logging
  2. Create upload and FAISS directories
  3. Initialize database tables (dev) or run Alembic (prod)
  4. Seed default roles and permissions
  5. Mount all API routers
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler (replaces deprecated on_event hooks).
    Runs startup logic before yield and teardown after.
    """
    # ── Startup ──────────────────────────────────────────────
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Ensure storage directories exist
    Path("logs").mkdir(exist_ok=True)
    settings.upload_path          # Creates ./uploads
    settings.faiss_index_path     # Creates ./faiss_index

    # Initialize DB tables
    from app.db.session import init_db
    await init_db()
    logger.info("Database tables initialized")

    # Seed default roles and permissions
    from app.db.session import AsyncSessionLocal
    from app.services.role_service import seed_roles_and_permissions
    async with AsyncSessionLocal() as db:
        await seed_roles_and_permissions(db)

    logger.info("Application startup complete")

    yield  # ← Application runs here

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Application shutting down")


# ─── Application Factory ──────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="""
## Financial Document Management System with Semantic Search (RAG)

A production-ready API for storing, managing, and intelligently searching
financial documents using AI-powered semantic retrieval.

### Key Features
- **JWT Authentication** with bcrypt password hashing
- **Role-Based Access Control** (Admin / Analyst / Auditor / Client)
- **Document Management** — upload PDFs and text files with rich metadata
- **RAG Pipeline** — extract → chunk → embed → FAISS vector search
- **Semantic Search** — natural language queries over financial content
- **Reranking** — hybrid keyword + semantic scoring for better relevance

### Quick Start
1. `POST /auth/register` — Create an account
2. `POST /auth/login` — Get your JWT token
3. `POST /documents/upload` — Upload a PDF (requires Analyst/Admin role)
4. `POST /rag/index-document` — Index it for semantic search
5. `POST /rag/search` — Query: *"financial risk related to high debt ratio"*
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],      # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────
    from app.api.auth import router as auth_router
    from app.api.documents import router as documents_router
    from app.api.rag import router as rag_router
    from app.api.roles import router as roles_router

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(rag_router)
    app.include_router(roles_router)

    # ── Health Check ──────────────────────────────────────────
    @app.get("/health", tags=["System"], summary="Health check")
    async def health():
        return {"status": "healthy", "version": settings.APP_VERSION}

    # ── Global Exception Handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "success": False},
        )

    return app


app = create_app()


# ─── Dev Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
