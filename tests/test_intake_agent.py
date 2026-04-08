import pytest

from compliance_agent.agents.intake_agent import IntakeAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import parsing, chunking


@pytest.mark.asyncio
async def test_intake_agent_parses_and_routes_documents(agentic_text_documents):
    registry = SkillRegistry()
    parsing.register_skills(registry)
    chunking.register_skills(registry)
    agent = IntakeAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "process_documents",
        "documents": [
            agentic_text_documents["source"],
            agentic_text_documents["response"],
            agentic_text_documents["prior"],
        ],
    })

    assert result["document_manifest"]["primary_source"].endswith("sample_rfp_source.txt")
    assert result["document_manifest"]["primary_response"].endswith("sample_response.txt")
    assert result["all_chunks"]
