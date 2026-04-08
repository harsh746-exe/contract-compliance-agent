"""Compatibility shim that keeps ``compliance_agent.config`` importable."""

# Re-export root-level configuration so package modules and scripts share one source of truth.
from config import *  # noqa: F401,F403
