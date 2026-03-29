"""Example usage of the linear and agentic workflow entrypoints."""

from compliance_agent import AgenticWorkflowEngine, ComplianceAgent
from compliance_agent.agentic import WorkflowGoal
from compliance_agent.scenarios import load_scenario

# Linear backbone usage
agent = ComplianceAgent()
linear_results = agent.process(
    policy_path="examples/scenarios/compliance_review_case_01/source.txt",
    response_path="examples/scenarios/compliance_review_case_01/response.txt",
    glossary_path="examples/scenarios/compliance_review_case_01/glossary.txt",  # optional
    context_paths=["examples/scenarios/compliance_review_case_01/prior_contract.txt"],
    run_id="example_linear_001",
)

print(f"Processed {len(linear_results['requirements'])} requirements")
print(f"Found {len(linear_results['decisions'])} compliance decisions")
print(f"{len(linear_results['review_queue'])} items require review")

agent.export_matrix("output/compliance_matrix.csv")
agent.export_json("output/results.json")
agent.export_report("output/compliance_report.md")

# Agentic workflow usage
scenario = load_scenario("examples/scenarios/draft_proposal_case_01")
engine = AgenticWorkflowEngine()
agentic_result = engine.run(
    goal=WorkflowGoal(
        goal_type="draft_proposal",
        description="Run the bounded agentic workflow over the committed draft scenario.",
        draft_requested=True,
    ),
    documents=scenario.documents,
    run_id="example_agentic_001",
)

print(agentic_result.status)
print(agentic_result.artifacts)
