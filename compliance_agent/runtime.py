"""Runtime dependency helpers for the compliance agent."""

from __future__ import annotations

from importlib import import_module
from typing import Iterable, Tuple


DependencySpec = Tuple[str, str]


def missing_dependencies(dependencies: Iterable[DependencySpec]) -> list[str]:
    """Return human-readable names for dependencies that are unavailable."""
    missing = []
    for display_name, module_name in dependencies:
        try:
            import_module(module_name)
        except ImportError:
            missing.append(display_name)
    return missing


def require_dependencies(feature_name: str, dependencies: Iterable[DependencySpec]) -> None:
    """Raise a clear error when optional runtime dependencies are unavailable."""
    missing = missing_dependencies(dependencies)
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"{feature_name} requires additional dependencies that are not installed: "
            f"{missing_str}. Install the pinned project requirements before using this feature."
        )


def require_orchestration_runtime() -> None:
    """Validate dependencies needed to instantiate the full pipeline."""
    require_dependencies(
        "ComplianceAgent orchestration",
        [
            ("langgraph", "langgraph"),
            ("langchain", "langchain"),
            ("langchain-openai", "langchain_openai"),
            ("chromadb", "chromadb"),
            ("sentence-transformers", "sentence_transformers"),
        ],
    )


def require_langchain_llm_runtime() -> None:
    """Validate dependencies used by LLM-backed agents."""
    require_dependencies(
        "LLM-backed agent initialization",
        [
            ("langchain", "langchain"),
            ("langchain-openai", "langchain_openai"),
        ],
    )


def require_retrieval_runtime() -> None:
    """Validate dependencies used by retrieval components."""
    require_dependencies(
        "Evidence retrieval",
        [
            ("langchain", "langchain"),
            ("langchain-openai", "langchain_openai"),
            ("chromadb", "chromadb"),
            ("sentence-transformers", "sentence_transformers"),
        ],
    )
