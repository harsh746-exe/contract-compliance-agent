"""Bootstrap entrypoint for the new MCP-based agentic system."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import config
from .agents.comparison_agent import ComparisonAgent
from .agents.compliance_agent import ComplianceAgent
from .agents.drafting_agent import DraftingAgent
from .agents.extraction_agent import ExtractionAgent
from .agents.intake_agent import IntakeAgent
from .agents.orchestrator import Orchestrator
from .agents.qa_agent import QAAgent
from .agents.retrieval_agent import RetrievalAgent
from .mcp.bus import MCPBus
from .output.export import RunArtifactsExporter
from .skills.registry import SkillRegistry
from .skills import (
    chunking,
    classification,
    comparison,
    drafting,
    extraction,
    parsing,
    qa,
    reasoning,
    retrieval,
    scoring,
)
from .utils.logging import configure_logging

logger = logging.getLogger(__name__)


def _prepare_run(goal: dict) -> tuple[str, Path]:
    run_id = goal.get("run_id") or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    output_root = Path(goal.get("output_dir") or config.OUTPUT_DIR)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


async def bootstrap() -> Orchestrator:
    """Initialize the shared infrastructure, skills, and agents."""
    configure_logging()
    bus = MCPBus()
    skill_registry = SkillRegistry()

    for module in [
        parsing,
        chunking,
        extraction,
        classification,
        retrieval,
        reasoning,
        scoring,
        comparison,
        drafting,
        qa,
    ]:
        module.register_skills(skill_registry)

    orchestrator = Orchestrator(bus=bus, skill_registry=skill_registry)
    IntakeAgent(bus=bus, skill_registry=skill_registry)
    ExtractionAgent(bus=bus, skill_registry=skill_registry)
    RetrievalAgent(bus=bus, skill_registry=skill_registry)
    ComplianceAgent(bus=bus, skill_registry=skill_registry)
    ComparisonAgent(bus=bus, skill_registry=skill_registry)
    DraftingAgent(bus=bus, skill_registry=skill_registry)
    QAAgent(bus=bus, skill_registry=skill_registry)

    logger.info("System ready with %s agents and %s skills", len(bus.discover_agents()), len(skill_registry.list_all()))
    return orchestrator


async def run(goal: dict) -> dict:
    """Bootstrap and execute one top-level workflow goal."""
    run_id, run_dir = _prepare_run(goal)
    configure_logging(log_path=run_dir / "agent_trace.log")
    orchestrator = await bootstrap()
    result = await orchestrator.execute_goal({
        **goal,
        "run_id": run_id,
        "run_dir": str(run_dir),
    })
    for agent in list(orchestrator.bus.discover_agents())[::-1]:
        orchestrator.bus.unregister_agent(agent.agent_id, reason="workflow_complete")
    result["audit_log"] = orchestrator.bus.get_audit_log()
    exporter = RunArtifactsExporter(run_dir)
    artifacts = exporter.export(result)
    result["run_id"] = run_id
    result["run_dir"] = str(run_dir)
    result["artifacts"] = artifacts
    return result


if __name__ == "__main__":
    if sys.platform == "darwin":
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    document_args = sys.argv[1:]
    goal = {
        "task": "compliance_review",
        "documents": document_args,
        "output_dir": "output/",
    }
    result = asyncio.run(run(goal))
    logger.info(
        "Workflow result:\n%s",
        json.dumps({
            "workflow": result.get("workflow"),
            "run_id": result.get("run_id"),
            "run_dir": result.get("run_dir"),
            "artifacts": result.get("artifacts", {}),
            "review_queue": result.get("outputs", {}).get("review_queue", []),
        }, indent=2, default=str),
    )
