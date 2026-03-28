"""
services/rag_service.py
RAG pipeline: text extraction → chunking → embedding → FAISS indexing → semantic search.

FAISS index stores all chunk embeddings.
A companion JSON metadata store maps FAISS internal IDs → chunk metadata.

Pipeline:
  Document → Text Extraction → Chunking → Embeddings → FAISS
  Query    → Embedding       → FAISS top-20 → Reranking → Top-5
"""

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.services.document_service import get_document_by_id, update_document_status
from app.utils.text_extractor import extract_text
from app.utils.chunking import chunk_text
from app.utils.embeddings import embed_texts, embed_query, get_embedding_dim


# ─── FAISS Store Manager ──────────────────────────────────────────────────────

class FAISSStore:
    """
    Manages a FAISS flat inner-product index (equivalent to cosine similarity
    when embeddings are L2-normalized).

    Persistence:
      - Index binary:  {FAISS_INDEX_PATH}/index.faiss
      - Metadata JSON: {FAISS_INDEX_PATH}/metadata.json
        Format: {"faiss_id": {document_id, chunk_index, text, ...}, ...}
    """

    def __init__(self) -> None:
        self._index = None
        self._metadata: Dict[int, Dict[str, Any]] = {}  # faiss_id -> chunk metadata
        self._next_id: int = 0
        self._index_path = settings.faiss_index_path / "index.faiss"
        self._meta_path = settings.faiss_index_path / "metadata.json"

    def _load_or_create_index(self) -> None:
        """Load existing FAISS index from disk, or create a new one."""
        import faiss

        if self._index is not None:
            return  # Already loaded

        dim = get_embedding_dim()

        if self._index_path.exists() and self._meta_path.exists():
            logger.info("Loading existing FAISS index from disk")
            self._index = faiss.read_index(str(self._index_path))
            with open(self._meta_path, "r") as f:
                raw = json.load(f)
            self._metadata = {int(k): v for k, v in raw.items()}
            self._next_id = max(self._metadata.keys(), default=-1) + 1
            logger.info(f"Loaded FAISS index with {self._index.ntotal} vectors")
        else:
            logger.info(f"Creating new FAISS index (dim={dim})")
            # IndexFlatIP: exact inner product search (cosine when normalized)
            self._index = faiss.IndexFlatIP(dim)
            self._metadata = {}
            self._next_id = 0

    def _save(self) -> None:
        """Persist index and metadata to disk."""
        import faiss
        faiss.write_index(self._index, str(self._index_path))
        with open(self._meta_path, "w") as f:
            json.dump(self._metadata, f, ensure_ascii=False)
        logger.debug("FAISS index saved to disk")

    def add_chunks(self, chunks: List[dict], embeddings: np.ndarray) -> List[int]:
        """
        Add chunk embeddings and their metadata to the index.

        Returns:
            List of assigned FAISS IDs.
        """
        self._load_or_create_index()

        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        vectors = embeddings.astype(np.float32)
        self._index.add(vectors)

        assigned_ids = []
        for i, chunk in enumerate(chunks):
            fid = self._next_id + i
            self._metadata[fid] = {
                "document_id": str(chunk["document_id"]),
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "word_count": chunk["word_count"],
            }
            assigned_ids.append(fid)

        self._next_id += len(chunks)
        self._save()

        logger.info(f"Added {len(chunks)} vectors. Index total: {self._index.ntotal}")
        return assigned_ids

    def remove_document(self, document_id: str) -> int:
        """
        Remove all chunks for a document from metadata.
        FAISS IndexFlatIP doesn't support deletion; we mark as removed in metadata
        and filter in search results. For production, use IndexIDMap.

        Returns:
            Number of chunks removed from metadata.
        """
        self._load_or_create_index()
        to_remove = [k for k, v in self._metadata.items()
                     if v["document_id"] == document_id]
        for k in to_remove:
            del self._metadata[k]
        self._save()
        logger.info(f"Removed {len(to_remove)} chunks for document {document_id}")
        return len(to_remove)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 20,
        filter_document_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Search for the top-k most similar chunks.

        Args:
            query_embedding: 1D normalized float32 array.
            top_k: Number of results to retrieve before reranking.
            filter_document_id: If set, only return chunks from this document.

        Returns:
            List of dicts with chunk metadata + similarity score.
        """
        self._load_or_create_index()

        if self._index.ntotal == 0:
            return []

        query_vec = query_embedding.astype(np.float32).reshape(1, -1)
        actual_k = min(top_k * 3, self._index.ntotal)  # Over-fetch to allow filtering

        scores, faiss_ids = self._index.search(query_vec, actual_k)

        results = []
        for score, fid in zip(scores[0], faiss_ids[0]):
            if fid == -1:  # FAISS padding for empty results
                continue
            meta = self._metadata.get(int(fid))
            if meta is None:  # Deleted document
                continue
            if filter_document_id and meta["document_id"] != filter_document_id:
                continue
            results.append({**meta, "similarity_score": float(score)})
            if len(results) >= top_k:
                break

        return results

    def get_document_chunks(self, document_id: str) -> List[dict]:
        """Return all stored chunks for a document (for context retrieval)."""
        self._load_or_create_index()
        chunks = [
            {**v, "faiss_id": k}
            for k, v in self._metadata.items()
            if v["document_id"] == document_id
        ]
        return sorted(chunks, key=lambda x: x["chunk_index"])


# Singleton instance shared across the app
faiss_store = FAISSStore()


# ─── Reranking ────────────────────────────────────────────────────────────────

def rerank_results(query: str, results: List[dict], top_n: int = 5) -> List[dict]:
    """
    Simple reranking based on term overlap + semantic score boost.
    In production, replace with a cross-encoder model (e.g., ms-marco-MiniLM).

    Scoring formula:
      final_score = 0.7 * semantic_score + 0.3 * keyword_overlap_ratio
    """
    if not results:
        return []

    query_terms = set(query.lower().split())

    for r in results:
        text_terms = set(r["text"].lower().split())
        overlap = len(query_terms & text_terms)
        overlap_ratio = overlap / max(len(query_terms), 1)
        r["relevance_score"] = 0.7 * r["similarity_score"] + 0.3 * overlap_ratio

    reranked = sorted(results, key=lambda x: x["relevance_score"], reverse=True)
    return reranked[:top_n]


# ─── Public RAG Functions ─────────────────────────────────────────────────────

async def index_document(db: AsyncSession, document_id: uuid.UUID) -> dict:
    """
    Full pipeline: extract → chunk → embed → store in FAISS.

    Args:
        db: Active database session.
        document_id: UUID of the Document to index.

    Returns:
        dict with status and chunk count.
    """
    doc: Document = await get_document_by_id(db, document_id)

    if doc.status == DocumentStatus.INDEXED:
        logger.info(f"Document {document_id} already indexed; re-indexing")
        faiss_store.remove_document(str(document_id))

    # Mark as indexing
    await update_document_status(db, document_id, DocumentStatus.INDEXING)

    try:
        # Step 1: Extract text
        logger.info(f"Extracting text from: {doc.file_path}")
        text = extract_text(doc.file_path, doc.mime_type)
        if not text.strip():
            raise ValueError("No text could be extracted from the document")

        # Step 2: Chunk text
        chunks = chunk_text(text, document_id=str(document_id))
        if not chunks:
            raise ValueError("Document produced zero chunks")

        # Step 3: Embed chunks
        texts_to_embed = [c["text"] for c in chunks]
        embeddings = embed_texts(texts_to_embed)

        # Step 4: Store in FAISS
        faiss_store.add_chunks(chunks, embeddings)

        # Update DB
        await update_document_status(db, document_id, DocumentStatus.INDEXED, len(chunks))

        logger.info(f"Document {document_id} indexed with {len(chunks)} chunks")
        return {
            "document_id": document_id,
            "status": "indexed",
            "chunks_indexed": len(chunks),
            "message": f"Successfully indexed {len(chunks)} chunks",
        }

    except Exception as e:
        logger.error(f"Indexing failed for {document_id}: {e}")
        await update_document_status(db, document_id, DocumentStatus.FAILED)
        raise


async def semantic_search(
    query: str,
    top_k: int = 5,
    company_name: Optional[str] = None,
    document_type: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> dict:
    """
    Full RAG retrieval pipeline:
      1. Embed query
      2. FAISS search (top 20)
      3. Rerank (top 5)
      4. Enrich with document metadata from DB

    Args:
        query: Natural language financial query.
        top_k: Final number of results after reranking.
        company_name: Optional filter.
        document_type: Optional filter.
        db: DB session for fetching document metadata.

    Returns:
        dict with query, total_retrieved, and results list.
    """
    logger.info(f"Semantic search: '{query[:80]}...'")

    # Step 1: Embed query
    q_embedding = embed_query(query)

    # Step 2: FAISS search (retrieve more for reranking)
    raw_results = faiss_store.search(q_embedding, top_k=20)

    if not raw_results:
        return {"query": query, "total_retrieved": 0, "results": []}

    # Step 3: Rerank
    reranked = rerank_results(query, raw_results, top_n=top_k)

    # Step 4: Enrich with document metadata
    enriched = []
    if db:
        from sqlalchemy import select
        from app.models.document import Document

        doc_ids = list({r["document_id"] for r in reranked})
        result = await db.execute(
            select(Document).where(Document.id.in_([uuid.UUID(d) for d in doc_ids]))
        )
        doc_map = {str(d.id): d for d in result.scalars()}

        for r in reranked:
            doc = doc_map.get(r["document_id"])
            if not doc:
                continue

            # Apply optional metadata filters
            if company_name and company_name.lower() not in doc.company_name.lower():
                continue
            if document_type and doc.document_type.value != document_type:
                continue

            enriched.append({
                "document_id": r["document_id"],
                "document_title": doc.title,
                "company_name": doc.company_name,
                "document_type": doc.document_type.value,
                "chunk_text": r["text"],
                "chunk_index": r["chunk_index"],
                "similarity_score": round(r["similarity_score"], 4),
                "relevance_score": round(r["relevance_score"], 4),
            })
    else:
        enriched = reranked

    return {
        "query": query,
        "total_retrieved": len(enriched),
        "results": enriched,
    }


async def remove_document_embeddings(document_id: uuid.UUID) -> int:
    """Remove all embeddings for a document from FAISS."""
    removed = faiss_store.remove_document(str(document_id))
    logger.info(f"Removed {removed} embeddings for document {document_id}")
    return removed


async def get_document_context(document_id: uuid.UUID) -> dict:
    """Retrieve all indexed chunks for a document (for context display)."""
    chunks = faiss_store.get_document_chunks(str(document_id))
    return {
        "document_id": str(document_id),
        "total_chunks": len(chunks),
        "chunks": [{"index": c["chunk_index"], "text": c["text"]} for c in chunks],
    }
