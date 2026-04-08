import pytest

from compliance_agent.main import bootstrap


@pytest.mark.asyncio
async def test_orchestrator_runs_compliance_flow(agentic_text_documents):
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
    assert result["outputs"]["decisions"]
    assert result["audit_log"]
