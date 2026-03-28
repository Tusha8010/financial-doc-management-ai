"""
utils/chunking.py
Split extracted document text into overlapping chunks for embedding.

Strategy: sentence-aware sliding window.
  - Tries to keep chunks at ~CHUNK_SIZE words
  - Overlaps by CHUNK_OVERLAP words to preserve context at boundaries
  - Respects sentence boundaries to avoid mid-sentence splits
"""

import re
from typing import List

from app.core.config import settings
from loguru import logger


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences using a simple regex pattern."""
    # Split on common sentence terminators followed by whitespace/newline
    sentence_pattern = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_pattern.split(text)
    # Also split on double newlines (paragraphs)
    all_sentences = []
    for s in sentences:
        parts = s.split('\n\n')
        all_sentences.extend([p.strip() for p in parts if p.strip()])
    return all_sentences


def word_count(text: str) -> int:
    """Count whitespace-delimited tokens (approximate)."""
    return len(text.split())


def chunk_text(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
    document_id: str = None,
) -> List[dict]:
    """
    Split text into semantically meaningful chunks with metadata.

    Args:
        text: Full document text.
        chunk_size: Target word count per chunk (default from settings).
        chunk_overlap: Overlap word count between chunks (default from settings).
        document_id: Optional document ID to embed in chunk metadata.

    Returns:
        List of dicts: [{chunk_index, text, word_count, char_count}]
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    if not text or not text.strip():
        logger.warning("Empty text passed to chunker")
        return []

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    sentences = split_into_sentences(text)
    chunks = []
    current_chunk_sentences = []
    current_word_count = 0
    chunk_index = 0

    for sentence in sentences:
        sentence_words = word_count(sentence)

        # If adding this sentence would exceed chunk_size, finalize current chunk
        if current_word_count + sentence_words > chunk_size and current_chunk_sentences:
            chunk_text_str = ' '.join(current_chunk_sentences)
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_text_str,
                "word_count": current_word_count,
                "char_count": len(chunk_text_str),
                "document_id": document_id,
            })
            chunk_index += 1

            # Overlap: keep last N words worth of sentences
            overlap_sentences = []
            overlap_words = 0
            for s in reversed(current_chunk_sentences):
                s_wc = word_count(s)
                if overlap_words + s_wc <= chunk_overlap:
                    overlap_sentences.insert(0, s)
                    overlap_words += s_wc
                else:
                    break

            current_chunk_sentences = overlap_sentences
            current_word_count = overlap_words

        current_chunk_sentences.append(sentence)
        current_word_count += sentence_words

    # Add remaining text as final chunk
    if current_chunk_sentences:
        chunk_text_str = ' '.join(current_chunk_sentences)
        chunks.append({
            "chunk_index": chunk_index,
            "text": chunk_text_str,
            "word_count": current_word_count,
            "char_count": len(chunk_text_str),
            "document_id": document_id,
        })

    logger.info(f"Created {len(chunks)} chunks from {word_count(text)} words")
    return chunks
