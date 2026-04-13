"""Helpers for managing the shared company document library."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = BASE_DIR / "data" / "library"

CATEGORIES = (
    "opportunities",
    "past_performance",
    "corporate",
    "hr",
    "management",
)


def _safe_name(value: str, default: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    return cleaned or default


def _size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def get_selectable_documents() -> list[dict[str, Any]]:
    """Return every library file in a form-friendly structure."""
    if not LIBRARY_ROOT.exists():
        return []

    documents: list[dict[str, Any]] = []
    files = sorted((path for path in LIBRARY_ROOT.rglob("*") if path.is_file()), key=lambda path: path.as_posix().lower())
    for path in files:
        relative_path = path.resolve().relative_to(LIBRARY_ROOT.resolve()).as_posix()
        category = relative_path.split("/", 1)[0]
        if category not in CATEGORIES:
            continue
        size_bytes = path.stat().st_size
        documents.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "display_path": relative_path,
                "category": category,
                "size_bytes": size_bytes,
                "size": _size_label(size_bytes),
            }
        )
    return documents


def get_library_tree() -> dict[str, Any]:
    """Return library files grouped by top-level category."""
    documents = get_selectable_documents()
    grouped: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORIES}
    for document in documents:
        grouped[document["category"]].append(document)
    categories = [
        {
            "key": category,
            "label": category.replace("_", " ").title(),
            "count": len(grouped[category]),
            "documents": grouped[category],
        }
        for category in CATEGORIES
    ]
    return {
        "root": str(LIBRARY_ROOT),
        "total_files": len(documents),
        "categories": categories,
    }


def upload_to_library(content: bytes | str, filename: str, category: str = "opportunities", bucket: str = "uploads") -> Path:
    """Store uploaded content in the shared library and return the file path."""
    target_category = category if category in CATEGORIES else "opportunities"
    safe_bucket = _safe_name(bucket, "uploads")
    safe_filename = _safe_name(Path(filename or "upload.txt").name, "upload.txt")

    destination_dir = LIBRARY_ROOT / target_category / safe_bucket / "uploads"
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / safe_filename
    if destination.exists():
        destination = destination_dir / f"{destination.stem}_{uuid4().hex[:6]}{destination.suffix}"

    if isinstance(content, bytes):
        destination.write_bytes(content)
    else:
        destination.write_text(content, encoding="utf-8")
    return destination


__all__ = [
    "CATEGORIES",
    "LIBRARY_ROOT",
    "get_library_tree",
    "get_selectable_documents",
    "upload_to_library",
]
