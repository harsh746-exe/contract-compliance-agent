from compliance_agent.agentic.comparison import HistoricalComparisonWorker
from compliance_agent.agentic.drafting import DraftEvaluator, DraftRewriter, ProposalDrafter


def test_historical_comparison_worker_summarizes_prior_context(tmp_path):
    source = tmp_path / "source.txt"
    prior = tmp_path / "prior_contract.txt"
    source.write_text("The vendor shall provide cloud support, reporting, and cybersecurity monitoring.")
    prior.write_text("The prior contract covered cloud support and reporting but not cybersecurity monitoring.")

    worker = HistoricalComparisonWorker()
    summary = worker.compare(str(source), [str(prior)])

    assert summary["documents"][0]["path"] == str(prior)
    assert "cloud" in " ".join(summary["documents"][0]["reused_terms"])
    assert summary["summary"]


def test_drafting_flow_generates_and_rewrites_sections(requirement_objects, decision_objects):
    drafter = ProposalDrafter()
    evaluator = DraftEvaluator()
    rewriter = DraftRewriter()

    draft = drafter.draft_outline(requirement_objects, decision_objects, {"summary": "Prior contract reuse is possible."})
    # Force one weak section to exercise the bounded rewrite loop.
    draft["sections"][0]["content"] = "TBD"
    draft["traceability"][draft["sections"][0]["heading"]] = []

    evaluation = evaluator.evaluate(draft, [req.req_id for req in requirement_objects])
    rewritten = rewriter.rewrite(draft, evaluation)
    reevaluation = evaluator.evaluate(rewritten, [req.req_id for req in requirement_objects])

    assert draft["outline"]
    assert evaluation["issues"]
    assert not reevaluation["issues"]
