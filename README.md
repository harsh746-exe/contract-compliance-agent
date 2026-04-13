# Contract/Policy Compliance Agent

MCP-based multi-agent system for automated compliance checking between a source document (policy/contract/RFP) and a response document (proposal/plan).

## Status

Prototype/MVP. Core MCP workflow is implemented and testable locally.

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

```bash
cp .env.example .env
```

Required for live model-backed usage:

- `LLM_PROVIDER` and provider credentials

Supported providers:

- `LLM_PROVIDER=deepinfra` with `DEEPINFRA_API_KEY` or `DEEPIN_API_KEY`
- `LLM_PROVIDER=openai` with `OPENAI_API_KEY`

Optional:

- `LLM_MODEL` to override provider default model
- `RUN_LIVE_LLM_TESTS=1` for guarded live tests

## Developer Workflow

```bash
pip install -r requirements.txt
pytest -q
python demo.py --help
```

## Stakeholder Dashboard

```bash
./.venv/bin/python -m uvicorn stakeholder_dashboard:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Usage

### Scenario-Driven Demo

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01
```

Evaluate an existing scenario run:

```bash
python demo.py \
  --scenario-dir examples/scenarios/compliance_review_case_01 \
  --evaluate-only
```

### Direct Command Line

```bash
python demo.py --policy policy.txt --response response.txt --output-dir output/results
```

## Output Format

The system produces run artifacts including:

1. `compliance_matrix.csv`
2. `compliance_results.json`
3. `compliance_report.md`
4. `audit_log.json`
5. `workflow_result.json`
6. Optional evaluation artifacts: `evaluation_metrics.json`, `evaluation_report.md`

## Limitations

- Prototype/MVP, not production-hardened.
- LLM outputs are nondeterministic.
- Offline tests use mocks/fakes by design.

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
