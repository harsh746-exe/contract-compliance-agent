import pytest

from compliance_agent.agents.extraction_agent import ExtractionAgent
from compliance_agent.mcp.bus import MCPBus
from compliance_agent.skills.registry import SkillRegistry
from compliance_agent.skills import classification, extraction


@pytest.mark.asyncio
async def test_extraction_agent_extracts_requirements():
    registry = SkillRegistry()
    extraction.register_skills(registry)
    classification.register_skills(registry)
    agent = ExtractionAgent(bus=MCPBus(), skill_registry=registry)

    result = await agent.execute_goal({
        "action": "extract_and_classify",
        "parsed_documents": [
            {
                "role": "solicitation_or_requirement_source",
                "chunks": [
                    {
                        "chunk_id": "source_chunk_1",
                        "section_title": "Section 1",
                        "page_range": "1-1",
                        "text": "The contractor shall provide monthly status reports.",
                        "metadata": {"file": "source.txt"},
                    }
                ],
            }
        ],
    })

    assert result["requirements"][0]["req_id"] == "REQ_0001"
    assert result["requirements"][0]["category"] in {"obligations", "reporting"}
