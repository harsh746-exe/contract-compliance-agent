"""Orchestration components."""

from typing import Any

__all__ = ["ComplianceAgent"]


def __getattr__(name: str) -> Any:
    """Lazily import orchestration-heavy modules."""
    if name == "ComplianceAgent":
        from .pipeline import ComplianceAgent
        return ComplianceAgent
    raise AttributeError(f"module 'compliance_agent.orchestration' has no attribute {name!r}")
