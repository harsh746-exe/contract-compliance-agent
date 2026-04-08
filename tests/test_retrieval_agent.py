import pytest

from compliance_agent.agents.retrieval_agent import RetrievalAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import retrieval


@pytest.mark.asyncio
async def test_retrieval_agent_builds_evidence_map():
    registry = SkillRegistry()
    retrieval.register_skills(registry)
    agent = RetrievalAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "build_index_and_retrieve",
        "requirements": [{"req_id": "REQ_0001", "requirement_text": "Provide monthly status reports"}],
        "corpus_chunks": [
            {"chunk_id": "response_chunk_1", "text": "We provide monthly status reports.", "metadata": {}},
            {"chunk_id": "response_chunk_2", "text": "We maintain security monitoring.", "metadata": {}},
        ],
    })

    assert "REQ_0001" in result["evidence_map"]
    assert result["evidence_map"]["REQ_0001"]
