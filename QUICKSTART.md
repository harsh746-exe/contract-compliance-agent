# Quick Start Guide

## Installation

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

3. Set up environment variables:

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY for live model-backed runs
```

## Local Verification

Run the offline-first verification flow from the project root:

```bash
pytest -q
python demo.py --help
```

Optional live smoke test:

```bash
RUN_LIVE_LLM_TESTS=1 pytest -q -m live
```

## Scenario Workflow

### Linear Scenario Run

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode linear
```

### Agentic Compliance Scenario Run

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode agentic
```

### Agentic Draft Scenario Run

```bash
python demo.py \
  --scenario-dir examples/scenarios/draft_proposal_case_01 \
  --mode agentic
```

### Scenario Evaluation

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --evaluate-only
```

### Resume After Approval Pause

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode agentic \
  --resume-run-id compliance_review_case_01
```

## Basic Usage

### Command Line

```bash
python demo.py --policy policy.txt --response response.txt --output-dir output/results
```

### Python Script

```python
from compliance_agent import ComplianceAgent

agent = ComplianceAgent()
results = agent.process(
    policy_path="policy.pdf",
    response_path="response.docx",
    glossary_path="glossary.pdf",  # optional
)

agent.export_matrix("compliance_matrix.csv")
agent.export_json("results.json")
agent.export_report("report.md")
```

Agentic Python API:

```python
from compliance_agent import AgenticWorkflowEngine
from compliance_agent.agentic import DocumentInput, WorkflowGoal

engine = AgenticWorkflowEngine()
result = engine.run(
    goal=WorkflowGoal(goal_type="compliance_review"),
    documents=[
        DocumentInput(path="policy.pdf", role="solicitation_or_requirement_source"),
        DocumentInput(path="response.docx", role="response_or_proposal"),
        DocumentInput(path="prior_contract.pdf", role="prior_contract"),
    ],
    run_id="quickstart_agentic_001",
)

print(result.status)
print(result.artifacts)
```

## Output Files

After processing, you'll get:

1. `*_matrix.csv`: Spreadsheet with all requirements and compliance status
2. `*_results.json`: Structured data with full metadata
3. `*_report.md`: Human-readable compliance report
4. `*_workflow_summary.md`: Agentic control-plane summary in agentic mode
5. `*_handoff_summary.json`: Handoff status, approvals, unresolved items, and artifact inventory
6. `*_comparison_summary.json`: Historical comparison artifact when prior context is supplied
7. `*_draft_outline.json`: Drafting artifact when the workflow goal requests drafting
8. `evaluation_metrics.json` and `evaluation_report.md`: Scenario evaluation artifacts

## Evaluation

To evaluate against ground truth:

```python
from evaluation import ComplianceEvaluator

evaluator = ComplianceEvaluator("ground_truth.json")
metrics = evaluator.evaluate("results.json", "evaluation_metrics.json")
evaluator.generate_evaluation_report(metrics, "evaluation_report.md")
```

Ground truth format:

```json
{
  "REQ_0001": "compliant",
  "REQ_0002": "partial",
  "REQ_0003": "not_addressed"
}
```

## Troubleshooting

### Missing Runtime Dependencies

If the full pipeline is unavailable, install the pinned dependencies from `requirements.txt`. The orchestrator now raises a clear runtime error when orchestration-only packages such as `langgraph` are missing.

### API Key Issues

Live model-backed runs require:

```text
OPENAI_API_KEY=sk-...
```

### Document Parsing Errors

- PDF files should be text-based rather than scanned images.
- DOCX files should be valid Word documents.
- TXT files are supported for lightweight committed demo scenarios.

## Notes

- Supported Python baseline: 3.9+
- Offline tests use mocks/fakes and do not make network calls.
- Live smoke tests are opt-in and intentionally narrow.
