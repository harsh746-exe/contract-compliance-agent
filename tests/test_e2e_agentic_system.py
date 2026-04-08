import pytest

from compliance_agent.main import bootstrap


@pytest.mark.asyncio
async def test_compliance_e2e(agentic_text_documents):
    orchestrator = await bootstrap()
    result = await orchestrator.execute_goal({
        "task": "compliance_review",
        "documents": [
            agentic_text_documents["source"],
            agentic_text_documents["response"],
            agentic_text_documents["prior"],
        ],
    })

    assert result["workflow"] == "compliance_review"
    assert all(step[1] == "completed" for step in result["steps"])
    assert len(result["outputs"]["decisions"]) > 0
    assert result["qa_report"]["overall_pass"] is not None
    agent_ids = {entry["sender"] for entry in result["audit_log"]}
    assert "intake_agent" in agent_ids
    assert "extraction_agent" in agent_ids
    assert "compliance_agent" in agent_ids


@pytest.mark.asyncio
async def test_drafting_e2e(agentic_text_documents):
    orchestrator = await bootstrap()
    result = await orchestrator.execute_goal({
        "task": "proposal_drafting",
        "documents": [
            agentic_text_documents["source"],
            agentic_text_documents["response"],
            agentic_text_documents["prior"],
        ],
    })

    assert result["workflow"] == "proposal_drafting"
    assert any(step[0] == "drafting" for step in result["steps"])
    assert "draft" in result
    assert result["draft"]["outline"]
