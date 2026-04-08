"""Token-aware chunking skills."""

from __future__ import annotations

import re

from .. import config
from .registry import Skill


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _split_oversized_sentence(sentence: str, max_tokens: int) -> list[str]:
    words = sentence.split()
    if len(words) <= max_tokens:
        return [sentence]
    parts = []
    for start in range(0, len(words), max_tokens):
        parts.append(" ".join(words[start:start + max_tokens]).strip())
    return [part for part in parts if part]


async def chunk_document(
    chunks: list[dict],
    chunk_size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
    max_chunk_size: int = config.MAX_CHUNK_SIZE,
) -> dict:
    output = []
    effective_limit = max(1, min(max_chunk_size, chunk_size))

    for chunk in chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue

        raw_sentences = _split_sentences(text)
        sentences = []
        for sentence in raw_sentences or [text]:
            sentences.extend(_split_oversized_sentence(sentence, effective_limit))
        current_sentences: list[str] = []
        current_tokens = 0
        part_index = 0

        for sentence in sentences:
            sentence_tokens = _estimate_tokens(sentence)
            if current_sentences and current_tokens + sentence_tokens > effective_limit:
                output.append(_materialize_chunk(chunk, current_sentences, part_index))
                part_index += 1

                overlap_sentences: list[str] = []
                overlap_tokens = 0
                for previous in reversed(current_sentences):
                    previous_tokens = _estimate_tokens(previous)
                    if overlap_tokens + previous_tokens > overlap:
                        break
                    overlap_sentences.insert(0, previous)
                    overlap_tokens += previous_tokens

                current_sentences = overlap_sentences[:]
                current_tokens = sum(_estimate_tokens(item) for item in current_sentences)

            current_sentences.append(sentence)
            current_tokens += sentence_tokens

        if current_sentences:
            output.append(_materialize_chunk(chunk, current_sentences, part_index))

    return {"chunks": output, "metadata": {"num_chunks": len(output)}}


def _materialize_chunk(source_chunk: dict, sentences: list[str], part_index: int) -> dict:
    text = " ".join(sentences).strip()
    chunk_id = source_chunk.get("chunk_id", "chunk")
    return {
        **source_chunk,
        "chunk_id": f"{chunk_id}_part_{part_index}" if part_index else chunk_id,
        "text": text,
        "metadata": {
            **source_chunk.get("metadata", {}),
            "estimated_tokens": _estimate_tokens(text),
            "part_index": part_index,
        },
    }


def register_skills(registry):
    registry.register(Skill(
        name="chunk_document",
        description="Split parsed document chunks into overlap-aware token windows.",
        handler=chunk_document,
        input_schema={"chunks": "list[dict]", "chunk_size": "int", "overlap": "int", "max_chunk_size": "int"},
        output_schema={"chunks": "list[dict]", "metadata": "dict"},
        tags=["chunking", "ingestion"],
        llm_tier="none",
    ))
