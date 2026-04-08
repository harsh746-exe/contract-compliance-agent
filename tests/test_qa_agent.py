import pytest

from compliance_agent.agents.qa_agent import QAAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import qa


@pytest.mark.asyncio
async def test_qa_agent_runs_final_gate():
    registry = SkillRegistry()
    qa.register_skills(registry)
    agent = QAAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "final_qa_check",
        "requirements": [{"req_id": "REQ_0001"}],
        "decisions": [{"requirement_id": "REQ_0001", "confidence": 0.95, "review_required": False}],
    })

    assert result["overall_pass"] is True
    assert result["requires_approval"] is False
