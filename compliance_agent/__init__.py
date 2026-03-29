"""Contract/Policy Compliance Agent System."""

import sys
from pathlib import Path
from typing import Any

# Add root directory to path for config import
_root_dir = Path(__file__).parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

# Import config (try root first, then use internal)
try:
    import config as _root_config
    # Create a config module that can be imported
    import types
    _config_module = types.ModuleType('config')
    for attr in dir(_root_config):
        if not attr.startswith('_'):
            setattr(_config_module, attr, getattr(_root_config, attr))
    sys.modules['compliance_agent.config'] = _config_module
except ImportError:
    # Use internal config
    from . import config as _config_module
    sys.modules['compliance_agent.config'] = _config_module

__all__ = ["ComplianceAgent", "AgenticWorkflowEngine"]


def __getattr__(name: str) -> Any:
    """Lazily import heavy modules so utility submodules stay usable."""
    if name == "ComplianceAgent":
        from .orchestration.pipeline import ComplianceAgent
        return ComplianceAgent
    if name == "AgenticWorkflowEngine":
        from .agentic.engine import AgenticWorkflowEngine
        return AgenticWorkflowEngine
    raise AttributeError(f"module 'compliance_agent' has no attribute {name!r}")
