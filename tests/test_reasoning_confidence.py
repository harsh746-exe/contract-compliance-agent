from compliance_agent.agents.compliance_reasoner import ComplianceReasonerAgent
from compliance_agent.agents.confidence_scorer import ConfidenceScorerAgent
from compliance_agent.orchestration.pipeline import ComplianceAgent


class FakeGraph:
    def invoke(self, state):
        return state


def test_reasoner_returns_not_addressed_without_evidence(requirement_objects):
    reasoner = ComplianceReasonerAgent(llm=object())
    decision = reasoner.reason(requirement_objects[0], [])

    assert decision.label == "not_addressed"
    assert decision.evidence_chunk_ids == []
    assert decision.suggested_edits


def test_confidence_scorer_flags_low_confidence(decision_objects, evidence_objects):
    scorer = ConfidenceScorerAgent(llm=object())
    low_confidence = decision_objects[1]
    low_confidence.confidence = 0.2

    scored = scorer.score(low_confidence, evidence_objects[:1])

    assert scored.confidence < 0.75
    assert "[ESCALATION:" in scored.explanation
    assert scorer.get_review_queue([scored]) == [scored.requirement_id]


def test_pipeline_retry_logic(monkeypatch):
    monkeypatch.setattr("compliance_agent.orchestration.pipeline.require_orchestration_runtime", lambda: None)
    monkeypatch.setattr(ComplianceAgent, "_build_graph", lambda self: FakeGraph())

    agent = ComplianceAgent(
        document_parser=object(),
        requirement_extractor=object(),
        requirement_classifier=object(),
        evidence_retriever=object(),
        compliance_reasoner=object(),
        confidence_scorer=object(),
        persistent_store=object(),
        matrix_generator=object(),
        report_generator=object(),
    )

    state = {
        "retry_count": 0,
        "decisions": [type("Decision", (), {"confidence": 0.2})()],
    }
    assert agent._should_retry(state) == "retry"

    state["retry_count"] = 99
    assert agent._should_retry(state) == "continue"
