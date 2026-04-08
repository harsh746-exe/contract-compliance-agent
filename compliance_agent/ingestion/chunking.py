"""Chunking utilities for document text."""

import re
from typing import List, Dict, Any, Union
from .document_parser import DocumentChunk
from .. import config


def chunk_text_by_size(chunks: List[Union[DocumentChunk, Dict[str, Any]]], max_tokens: int = None) -> List[Dict[str, Any]]:
    """
    Further split chunks that exceed max_tokens.
    
    Args:
        chunks: List of DocumentChunk objects
        max_tokens: Maximum tokens per chunk (defaults to config.CHUNK_SIZE)
    
    Returns:
        List of DocumentChunk objects (may be longer than input)
    """
    if max_tokens is None:
        max_tokens = config.CHUNK_SIZE
    
    new_chunks = []
    
    for chunk in chunks:
        # Handle both DocumentChunk objects and dicts
        if isinstance(chunk, dict):
            text = chunk.get("text", "")
        else:
            text = chunk.text
        
        # Rough token estimation (1 token ≈ 4 characters)
        estimated_tokens = len(text) // 4
        
        if estimated_tokens <= max_tokens:
            if isinstance(chunk, dict):
                new_chunks.append(chunk)
            else:
                new_chunks.append({
                    "chunk_id": chunk.chunk_id,
                    "doc_type": chunk.doc_type,
                    "section_title": chunk.section_title,
                    "page_range": chunk.page_range,
                    "text": chunk.text,
                    "metadata": chunk.metadata
                })
        else:
            # Split the chunk
            split_chunks = _split_chunk(chunk, max_tokens)
            new_chunks.extend(split_chunks)
    
    return new_chunks


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def _split_oversized_sentence(sentence: str, max_tokens: int) -> List[str]:
    words = sentence.split()
    if len(words) <= max_tokens:
        return [sentence]
    return [
        " ".join(words[index:index + max_tokens]).strip()
        for index in range(0, len(words), max_tokens)
        if " ".join(words[index:index + max_tokens]).strip()
    ]


def _split_chunk(chunk: Union[DocumentChunk, Dict[str, Any]], max_tokens: int) -> List[Dict[str, Any]]:
    """Split a chunk into smaller pieces."""
    split_chunks = []
    
    # Extract text and metadata
    if isinstance(chunk, dict):
        text = chunk.get("text", "")
        chunk_id = chunk.get("chunk_id", "")
        doc_type = chunk.get("doc_type", "")
        section_title = chunk.get("section_title", "")
        page_range = chunk.get("page_range", "")
        metadata = chunk.get("metadata", {}).copy()
    else:
        text = chunk.text
        chunk_id = chunk.chunk_id
        doc_type = chunk.doc_type
        section_title = chunk.section_title
        page_range = chunk.page_range
        metadata = chunk.metadata.copy()
    
    raw_sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]
    sentences: List[str] = []
    for sentence in raw_sentences or [text]:
        sentences.extend(_split_oversized_sentence(sentence, max_tokens))
    current_text = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = _estimate_tokens(sentence)

        if current_tokens + sentence_tokens > max_tokens and current_text:
            # Create chunk from accumulated text
            chunk_text = ' '.join(current_text).strip()
            split_chunks.append({
                "chunk_id": f"{chunk_id}_part_{len(split_chunks)}",
                "doc_type": doc_type,
                "section_title": section_title,
                "page_range": page_range,
                "text": chunk_text,
                "metadata": metadata.copy()
            })
            current_text = []
            current_tokens = 0
        
        current_text.append(sentence)
        current_tokens += sentence_tokens

    # Add remaining text
    if current_text:
        chunk_text = ' '.join(current_text).strip()
        split_chunks.append({
            "chunk_id": f"{chunk_id}_part_{len(split_chunks)}",
            "doc_type": doc_type,
            "section_title": section_title,
            "page_range": page_range,
            "text": chunk_text,
            "metadata": metadata.copy()
        })
    
    if not split_chunks:
        # Return original as dict
        if isinstance(chunk, dict):
            return [chunk]
        else:
            return [{
                "chunk_id": chunk.chunk_id,
                "doc_type": chunk.doc_type,
                "section_title": chunk.section_title,
                "page_range": chunk.page_range,
                "text": chunk.text,
                "metadata": chunk.metadata
            }]
    
    return split_chunks
