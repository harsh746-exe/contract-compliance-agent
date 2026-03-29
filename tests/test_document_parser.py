from pathlib import Path

import pytest

from compliance_agent.ingestion.document_parser import DocumentChunk, DocumentParser


def test_parse_missing_file_raises():
    parser = DocumentParser()

    with pytest.raises(FileNotFoundError):
        parser.parse("does-not-exist.pdf")


def test_parse_unsupported_file_raises(tmp_path):
    parser = DocumentParser()
    markdown_file = tmp_path / "notes.md"
    markdown_file.write_text("unsupported")

    with pytest.raises(ValueError, match="Unsupported file format"):
        parser.parse(str(markdown_file))


def test_parse_routes_pdf_and_docx(monkeypatch, tmp_path):
    parser = DocumentParser()
    pdf_path = tmp_path / "policy.pdf"
    docx_path = tmp_path / "response.docx"
    txt_path = tmp_path / "context.txt"
    pdf_path.write_text("placeholder")
    docx_path.write_text("placeholder")
    txt_path.write_text("INTRODUCTION\nExample text")

    calls = []

    def fake_parse_pdf(path: Path, doc_type: str):
        calls.append(("pdf", path.name, doc_type))
        return [DocumentChunk("pdf_chunk", doc_type, "Intro", "1-1", "text", {})]

    def fake_parse_docx(path: Path, doc_type: str):
        calls.append(("docx", path.name, doc_type))
        return [DocumentChunk("docx_chunk", doc_type, "Intro", "N/A", "text", {})]

    def fake_parse_text(path: Path, doc_type: str):
        calls.append(("txt", path.name, doc_type))
        return [DocumentChunk("txt_chunk", doc_type, "Intro", "N/A", "text", {})]

    monkeypatch.setattr(parser, "_parse_pdf", fake_parse_pdf)
    monkeypatch.setattr(parser, "_parse_docx", fake_parse_docx)
    monkeypatch.setattr(parser, "_parse_text", fake_parse_text)

    pdf_chunks = parser.parse(str(pdf_path), doc_type="policy")
    docx_chunks = parser.parse(str(docx_path), doc_type="response")
    txt_chunks = parser.parse(str(txt_path), doc_type="context")

    assert pdf_chunks[0].chunk_id == "pdf_chunk"
    assert docx_chunks[0].chunk_id == "docx_chunk"
    assert txt_chunks[0].chunk_id == "txt_chunk"
    assert calls == [
        ("pdf", "policy.pdf", "policy"),
        ("docx", "response.docx", "response"),
        ("txt", "context.txt", "context"),
    ]
