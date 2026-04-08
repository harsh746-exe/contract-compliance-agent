"""Parsing skills."""

from __future__ import annotations

import asyncio

from ..ingestion.document_parser import DocumentParser
from .registry import Skill


def _chunk_to_dict(chunk):
    return {
        "chunk_id": chunk.chunk_id,
        "doc_type": chunk.doc_type,
        "section_title": chunk.section_title,
        "page_range": chunk.page_range,
        "text": chunk.text,
        "metadata": chunk.metadata,
    }


async def parse_document(file_path: str, doc_type: str = "unknown", preserve_metadata: bool = True) -> dict:
    parser = DocumentParser()
    chunks = await asyncio.to_thread(parser.parse, file_path, doc_type)
    payload = [_chunk_to_dict(chunk) for chunk in chunks]
    return {
        "chunks": payload,
        "metadata": {
            "file_path": file_path,
            "doc_type": doc_type,
            "preserve_metadata": preserve_metadata,
            "num_chunks": len(payload),
        },
    }


async def parse_pdf(file_path: str, preserve_metadata: bool = True) -> dict:
    return await parse_document(file_path=file_path, doc_type="pdf", preserve_metadata=preserve_metadata)


async def parse_docx(file_path: str, preserve_metadata: bool = True) -> dict:
    return await parse_document(file_path=file_path, doc_type="docx", preserve_metadata=preserve_metadata)


async def parse_txt(file_path: str, preserve_metadata: bool = True) -> dict:
    return await parse_document(file_path=file_path, doc_type="txt", preserve_metadata=preserve_metadata)


def register_skills(registry):
    for name, handler, doc_tag in [
        ("parse_document", parse_document, "generic"),
        ("parse_pdf", parse_pdf, "pdf"),
        ("parse_docx", parse_docx, "docx"),
        ("parse_txt", parse_txt, "txt"),
    ]:
        registry.register(Skill(
            name=name,
            description=f"Parse a {doc_tag} document into structured chunks with metadata.",
            handler=handler,
            input_schema={"file_path": "str", "preserve_metadata": "bool"},
            output_schema={"chunks": "list[dict]", "metadata": "dict"},
            tags=["parsing", "ingestion", doc_tag],
            llm_tier="none",
        ))
