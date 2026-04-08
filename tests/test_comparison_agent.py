import pytest

from compliance_agent.agents.comparison_agent import ComparisonAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import comparison


@pytest.mark.asyncio
async def test_comparison_agent_summarizes_history(agentic_text_documents):
    registry = SkillRegistry()
    comparison.register_skills(registry)
    agent = ComparisonAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "compare_documents",
        "source_path": agentic_text_documents["source"],
        "prior_paths": [agentic_text_documents["prior"]],
    })

    assert result["documents"]
    assert result["summary"]
