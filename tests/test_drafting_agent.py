import pytest

from compliance_agent.agents.drafting_agent import DraftingAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import drafting


@pytest.mark.asyncio
async def test_drafting_agent_generates_outline():
    registry = SkillRegistry()
    drafting.register_skills(registry)
    agent = DraftingAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "draft_proposal",
        "requirements": [{"req_id": "REQ_0001", "category": "reporting", "requirement_text": "Provide monthly status reports"}],
        "decisions": [{"requirement_id": "REQ_0001", "label": "compliant"}],
        "evidence_map": {"REQ_0001": [{"chunk_id": "response_chunk_1"}]},
    })

    assert result["draft"]["outline"]
    assert result["draft"]["sections"]
