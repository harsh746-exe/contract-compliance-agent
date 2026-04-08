import pytest

from compliance_agent.agents.compliance_agent import ComplianceAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import reasoning, scoring


@pytest.mark.asyncio
async def test_agentic_compliance_agent_scores_and_flags():
    registry = SkillRegistry()
    reasoning.register_skills(registry)
    scoring.register_skills(registry)
    agent = ComplianceAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "assess_compliance",
        "requirements": [{"req_id": "REQ_0001", "requirement_text": "Provide monthly status reports"}],
        "evidence_map": {
            "REQ_0001": [{"chunk_id": "response_chunk_1", "text": "We provide monthly status reports.", "retrieval_score": 0.9}]
        },
    })

    assert result["decisions"][0]["requirement_id"] == "REQ_0001"
    assert result["decisions"][0]["label"] in {"compliant", "partial", "not_addressed", "not_compliant"}
