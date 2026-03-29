from compliance_agent.ingestion.chunking import chunk_text_by_size
from compliance_agent.ingestion.document_parser import DocumentChunk


def test_chunk_text_by_size_preserves_small_chunk():
    chunk = DocumentChunk(
        chunk_id="policy_chunk_1",
        doc_type="policy",
        section_title="Section A",
        page_range="1-1",
        text="Short requirement sentence.",
        metadata={"page": 1},
    )

    result = chunk_text_by_size([chunk], max_tokens=100)

    assert result == [{
        "chunk_id": "policy_chunk_1",
        "doc_type": "policy",
        "section_title": "Section A",
        "page_range": "1-1",
        "text": "Short requirement sentence.",
        "metadata": {"page": 1},
    }]


def test_chunk_text_by_size_splits_large_chunk_and_preserves_metadata():
    text = "Sentence one is intentionally long. Sentence two is also intentionally long. Sentence three stays long too."
    chunk = {
        "chunk_id": "response_chunk_1",
        "doc_type": "response",
        "section_title": "Section B",
        "page_range": "2-3",
        "text": text,
        "metadata": {"page": 2, "source": "doc"},
    }

    result = chunk_text_by_size([chunk], max_tokens=8)

    assert len(result) >= 2
    assert result[0]["chunk_id"].startswith("response_chunk_1_part_")
    assert all(item["metadata"] == {"page": 2, "source": "doc"} for item in result)
    assert all(item["section_title"] == "Section B" for item in result)
