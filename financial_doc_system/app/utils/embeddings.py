"""
utils/embeddings.py
Singleton embedding model using sentence-transformers.
Caches the model after first load to avoid repeated downloads.
"""

from functools import lru_cache
from typing import List

import numpy as np
from loguru import logger

from app.core.config import settings


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Load and cache the sentence-transformer model.
    Called once; subsequent calls return the cached instance.
    Uses all-MiniLM-L6-v2 (384-dim, fast, good for semantic similarity).
    """
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    logger.info("Embedding model loaded successfully")
    return model


def embed_texts(texts: List[str], batch_size: int = 64) -> np.ndarray:
    """
    Generate embeddings for a list of text strings.

    Args:
        texts: List of strings to embed.
        batch_size: Processing batch size (larger = faster on GPU).

    Returns:
        numpy array of shape (len(texts), embedding_dim).
    """
    if not texts:
        return np.array([])

    model = get_embedding_model()
    logger.debug(f"Embedding {len(texts)} texts in batches of {batch_size}")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,  # L2-normalize for cosine similarity via dot product
        convert_to_numpy=True,
    )
    return embeddings


def embed_query(query: str) -> np.ndarray:
    """
    Embed a single query string.

    Returns:
        1D numpy array of shape (embedding_dim,).
    """
    model = get_embedding_model()
    embedding = model.encode(
        query,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embedding


def get_embedding_dim() -> int:
    """Return the embedding dimension for the configured model."""
    model = get_embedding_model()
    return model.get_sentence_embedding_dimension()
