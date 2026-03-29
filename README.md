# Contract/Policy Compliance Agent

A multi-agent prototype for automated compliance checking between a contract or policy document and a response document such as a proposal, commitment letter, or implementation plan.

## Status

This repository is currently a prototype/MVP. The core pipeline is implemented, but full orchestration still depends on the pinned external LangChain/LangGraph stack and live model behavior remains nondeterministic.

## Python Baseline

- Supported baseline: Python 3.9+

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Environment

Copy the example file and update only what you need:

```bash
cp .env.example .env
```

Required for live model-backed usage:

- `OPENAI_API_KEY`

Optional:

- `OPENAI_MODEL` to override the default model
- `RUN_LIVE_LLM_TESTS=1` to opt into the guarded live smoke test

## Developer Workflow

Create and activate an environment, install the dependencies, then use this local verification sequence:

```bash
pip install -r requirements.txt
pytest -q
python demo.py --help
```

Optional live smoke test:

```bash
RUN_LIVE_LLM_TESTS=1 pytest -q -m live
```

## Usage

### Scenario-Driven Demo Path

Run the committed compliance scenario in linear mode:

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode linear
```

Run the committed compliance scenario in agentic mode:

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode agentic
```

Run the committed drafting scenario in agentic mode:

```bash
python demo.py \
  --scenario-dir examples/scenarios/draft_proposal_case_01 \
  --mode agentic
```

Evaluate an existing scenario run:

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --evaluate-only
```

Resume a paused approval-gated scenario run:

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --mode agentic \
  --resume-run-id compliance_review_case_01
```

### Direct Command Line

```bash
python demo.py --policy policy.txt --response response.txt --output-dir output/results
```

### Python API

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

Agentic workflow API:

```python
from compliance_agent import AgenticWorkflowEngine
from compliance_agent.agentic import ApprovalDecision, DocumentInput, WorkflowGoal

engine = AgenticWorkflowEngine()
result = engine.run(
    goal=WorkflowGoal(
        goal_type="compliance_review",
        description="Run the bounded agentic compliance workflow.",
    ),
    documents=[
        DocumentInput(path="policy.pdf", role="solicitation_or_requirement_source"),
        DocumentInput(path="response.docx", role="response_or_proposal"),
        DocumentInput(path="prior_contract.pdf", role="prior_contract"),
    ],
    approval_handler=lambda request: ApprovalDecision(
        request_id=request.request_id,
        approved=True,
        rationale="Approved for bounded continuation.",
        reviewer="demo_user",
    ),
    run_id="agentic_demo_001",
)

print(result.status)
print(result.artifacts["workflow_summary"])
```

## Output Format

The system produces:

1. CSV matrix
2. JSON results
3. Markdown compliance report
4. Agentic workflow summary markdown in agentic mode
5. `handoff_summary.json` for completed or approval-paused agentic runs
6. Optional comparison and draft artifacts in agentic mode
7. Scenario evaluation artifacts: `evaluation_metrics.json` and `evaluation_report.md`

## Evaluation

Run evaluation on ground truth data directly:

```python
from evaluation import evaluate_system

metrics = evaluate_system(
    ground_truth_path="ground_truth.json",
    system_output_path="results.json",
)
```

## Limitations

- This is a prototype/MVP, not a production-hardened service.
- LLM outputs are nondeterministic and may vary across runs.
- Offline tests use mocks and fakes by design to avoid network dependency.
- Full orchestration runtime still depends on the pinned external LangChain/LangGraph stack.

## Project Structure

```text
.
├── compliance_agent/
├── examples/scenarios/
├── evaluation/
├── tests/
├── demo.py
├── QUICKSTART.md
├── requirements.txt
└── pyproject.toml
```
