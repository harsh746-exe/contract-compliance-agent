# Project Context: Contract/Policy Compliance Agent

Last updated: April 7, 2026 (America/New_York)

## 1) What this project is

This repository implements a prototype/MVP system for automated compliance analysis between:

- a requirement-bearing source document (policy, SOW, solicitation, contract terms)
- a response/proposal/implementation document
- optional supporting context (prior contracts, amendments, past performance, glossary)

It produces:

- compliance decisions per requirement
- evidence traces
- confidence/review queue signals
- export artifacts (CSV, JSON, Markdown)
- optional comparison and draft artifacts in agentic workflows

The codebase intentionally includes multiple orchestration styles in parallel.

## 2) High-level architecture (critical)

There are three distinct execution surfaces:

1. Linear pipeline (legacy backbone)
- Entry: `compliance_agent.orchestration.pipeline.ComplianceAgent`
- Orchestration: LangGraph state graph
- Path: ingest -> extract -> classify -> retrieve -> reason -> score/retry -> export

2. Bounded planner-based agentic engine
- Entry: `compliance_agent.agentic.engine.AgenticWorkflowEngine`
- Orchestration: explicit planner + evaluator control loop
- Features: bounded action vocabulary, approval checkpoints, pause/resume, workflow state persistence

3. MCP-style autonomous multi-agent runtime
- Entry: `compliance_agent.main.run` (bootstraps bus + agents + skills)
- Orchestration: in-process message bus with role-specialized agents and skill invocations
- Used by dashboard agentic execution path

Important: these three paths share concepts but are not identical implementations.

## 3) Repository map

Top-level key files/folders:

- `compliance_agent/` main package
- `demo.py` CLI demo runner for linear + planner-agentic modes
- `stakeholder_dashboard.py` FastAPI stakeholder UI
- `stakeholder_dashboard/` templates/static assets
- `evaluation/` scoring + reports
- `examples/scenarios/` reproducible scenario fixtures + manifests
- `tests/` automated tests
- `config.py` root runtime config
- `requirements.txt`, `pyproject.toml`, `.env.example`
- `Dockerfile`, `render.yaml`

## 4) Core data contracts

### 4.1 Legacy dataclasses (`compliance_agent/memory/persistent_store.py`)

- `Requirement`
  - `req_id`
  - `requirement_text`
  - `source_citation`
  - optional `conditions`, `priority`, `category`

- `Evidence`
  - `evidence_chunk_id`
  - `evidence_text`
  - `evidence_citation`
  - `retrieval_score`
  - `requirement_id`

- `ComplianceDecision`
  - `requirement_id`
  - `label` in `{compliant, partial, not_compliant, not_addressed}`
  - `confidence`
  - `explanation`
  - `evidence_chunk_ids`
  - optional `suggested_edits`, `timestamp`

### 4.2 Planner-agentic models (`compliance_agent/agentic/models.py`)

Pydantic JSON-first models with strict vocabularies:

- bounded planner actions (`route_documents`, `prepare_context`, `run_compliance_pipeline`, `reanalyze_low_confidence`, `compare_with_prior_context`, `draft_response_outline`, `evaluate_draft`, `rewrite_draft`, `request_human_approval`, `finalize_outputs`, `stop_with_error`)
- document roles (`solicitation_or_requirement_source`, `response_or_proposal`, `glossary`, `prior_proposal`, `prior_contract`, `amendment`, `past_performance`, `unknown`)
- `WorkflowGoal`, `DocumentInput`, `DocumentManifest`, `WorkflowTask`, `PlannerDecision`, `EvaluatorDecision`, `ApprovalRequest`, `ApprovalDecision`, `WorkflowRunResult`

## 5) Linear pipeline details

File: `compliance_agent/orchestration/pipeline.py`

### 5.1 Graph topology

Nodes:

- `ingest_documents`
- `extract_requirements`
- `classify_requirements`
- `build_index`
- `retrieve_evidence`
- `reason_compliance`
- `score_confidence`
- `check_retry`

Conditional edge:

- from `score_confidence`
  - `retry` -> `check_retry` -> `retrieve_evidence`
  - `continue` -> END

### 5.2 Retry policy

- retries only if low-confidence decisions exist (`< CONFIDENCE_MEDIUM`) and query expansion enabled
- hard cap: `MAX_RETRIES`

### 5.3 Ingestion/chunking

- parser supports `.pdf`, `.docx`, `.txt`
- PDF: `pdfplumber` first, then `PyPDF2` fallback
- section heuristics based on all-caps/numbered headings
- additional sentence-aware chunk splitting for oversized chunks
- context docs are appended into response corpus for retrieval

### 5.4 Retrieval stack (linear)

- vector index from response/context chunks
- Chroma-backed search + embeddings (`sentence-transformers` wrapper by default)
- keyword search fallback/augmentation
- merged, deduped evidence ranked by retrieval score

### 5.5 Reasoning + confidence

- LLM-first compliance classification with strict rubric
- rule fallback when needed
- confidence adjusts using retrieval quality/evidence count/contradiction signals
- review queue populated for confidence below high threshold

### 5.6 Persistence/export

- writes requirements/evidence/decisions JSON to persistent store
- exports logs + run summary via `WorkingMemory`
- export methods write CSV matrix, JSON result bundle, Markdown report

## 6) Planner-based agentic engine details

Primary files:

- `compliance_agent/agentic/engine.py`
- `compliance_agent/agentic/planner.py`
- `compliance_agent/agentic/evaluator.py`
- `compliance_agent/agentic/router.py`
- `compliance_agent/agentic/store.py`
- `compliance_agent/agentic/comparison.py`
- `compliance_agent/agentic/drafting.py`

### 6.1 Control loop behavior

`run(...)` loop continues while state status is `running`:

1. if pending approval request -> execute approval action
2. planner chooses next bounded action
3. action executes
4. evaluator scores action outcome
5. evaluator decision is applied (accept/retry/branch/request approval/terminate blocked)
6. state snapshot is persisted

Bounded by `AGENTIC_MAX_STEPS`.

### 6.2 Approval semantics

- if approval needed and no `approval_handler` provided: workflow pauses with `awaiting_approval`
- resumable by `run(..., resume=True, run_id=...)`
- approval grant/deny recorded in state

### 6.3 Finalization artifacts

Engine writes:

- matrix/results/report (via linear compliance agent exports)
- optional `comparison_summary.json`
- optional `draft_outline.json`
- `workflow_summary.md`
- `handoff_summary.json` (contains safety signal `safe_for_demo_handoff`)

### 6.4 State persistence

`WorkflowStateStore` saves:

- mutable state: `data/workflow_state/<run_id>_workflow_state.json`
- result summary: `data/workflow_state/<run_id>_workflow_summary.json`

## 7) MCP autonomous multi-agent runtime

Primary files:

- `compliance_agent/main.py`
- `compliance_agent/mcp/protocol.py`
- `compliance_agent/mcp/bus.py`
- `compliance_agent/agents/*.py`
- `compliance_agent/skills/*.py`

### 7.1 Bus protocol

Message types:

- `goal`, `result`
- `tool_call`, `tool_result`
- `status`, `error`
- `spawn`, `terminate`

Every message is audit-logged.

### 7.2 Agent set

Registered agents:

- `orchestrator`
- `intake_agent`
- `extraction_agent`
- `retrieval_agent`
- `compliance_agent`
- `comparison_agent`
- `drafting_agent`
- `qa_agent`

`orchestrator` can spawn temporary sub-agents for low-confidence reanalysis.

### 7.3 Skill registry

Skills are async handlers with schemas and metadata (`tags`, `llm_tier`), including:

- parsing/chunking
- extraction/classification
- retrieval (`vector_search`, `bm25_search`, `rerank`, `assemble_context`)
- reasoning/citation validation
- confidence scoring/flagging
- comparison
- drafting/rewrite
- QA checks

### 7.4 MCP workflow output export

`RunArtifactsExporter` writes run folder artifacts including:

- workflow result
- requirements
- compliance decisions
- evidence map
- audit log
- qa report
- run manifest
- compliance matrix/results/report
- optional document manifest/comparison/draft artifacts

## 8) LLM/provider subsystem

Files:

- `compliance_agent/llm/provider.py`
- `compliance_agent/llm/openai_compat.py`
- `compliance_agent/llm/deepinfra.py`
- `compliance_agent/llm/__init__.py`
- `compliance_agent/utils/retry.py`

### 8.1 Providers

- `deepinfra` via OpenAI-compatible endpoint
- `openai` via OpenAI-compatible endpoint
- deterministic fallback if preferred provider unavailable

### 8.2 Request object model

- `LLMRequest(messages, model, temperature, max_tokens, response_format)`
- `LLMResponse(content, model, usage, provider, latency_ms)`

### 8.3 Reliability/logging

- per-request structured start/success/error logs with request IDs
- exponential backoff retry (`LLM_MAX_RETRIES`, `LLM_BACKOFF_BASE`)
- avoids retry on certain non-retriable network errors

## 9) Configuration and env

Main config is root `config.py` (re-exported through `compliance_agent/config.py` shim).

Key knobs:

- provider/model selection (`LLM_PROVIDER`, model vars, base URLs, keys)
- chunking (`CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_CHUNK_SIZE`)
- retrieval (`TOP_K_RETRIEVAL`, `BM25_TOP_K`, `RERANK_TOP_K`, `RETRIEVAL_MAX_TOP_K`)
- confidence thresholds (`CONFIDENCE_HIGH`, `CONFIDENCE_MEDIUM`, `CONFIDENCE_THRESHOLD`)
- retry bounds (`MAX_RETRIES`, `AGENTIC_MAX_ACTION_RETRIES`, `AGENTIC_MAX_STEPS`)
- execution mode (`EXECUTION_MODE`, defaults to `agentic`)

Output/data dirs created at startup:

- `output/`, `output/results`, `output/logs`, `output/agentic`, `output/demo_cases`, `output/evaluation`
- `data/workflow_state`, `data/workflow_compliance_store`, `data/vector_store`, `data/run_store`, `data/skill_audit`

## 10) CLI usage model (`demo.py`)

Modes:

- `--mode linear`
- `--mode agentic`

Other important flags:

- `--scenario-dir`
- `--evaluate-only`
- `--resume-run-id` (agentic resume)
- direct file args: `--policy`, `--response`, optional `--glossary`, repeatable `--context`

Scenario helper (`compliance_agent/scenarios.py`) validates manifests and roles, resolves paths, and supports evaluation artifacts.

## 11) Dashboard app details

Main server: `stakeholder_dashboard.py` (FastAPI + Jinja2 templates + static JS/CSS)

### 11.1 Primary routes

- `/` overview
- `/documents` mock company document shelf
- `/files` managed file explorer
- `/activity` timeline feed
- `/runs/{scope}` run detail
- `/runs/{scope}/workflow` agent swim-lane visualization
- `/run-demo` run default scenario
- `/run-upload` upload and execute custom case
- `/downloads/{scope}/{artifact}` artifact downloads
- `/health` healthcheck

### 11.2 Execution path from dashboard

- if `EXECUTION_MODE == "agentic"`:
  - calls `compliance_agent.main.run(...)` (MCP orchestrator path)
- otherwise:
  - calls linear `ComplianceAgent`

### 11.3 Dashboard data assembly

It builds run bundles by reading run metadata + artifacts, then:

- creates requirement rows (linear or agentic artifact style)
- merges evidence and review queue signals
- derives focus items and case snapshot metrics
- renders timeline from either working-memory logs or MCP audit log
- for MCP logs, generates workflow data consumed by `static/workflow.js`

## 12) Evaluation subsystem

Files:

- `evaluation/metrics.py`
- `evaluation/__init__.py`
- `evaluation/baseline.py`

Metrics:

- accuracy
- Cohen's kappa
- per-label precision/recall/F1/support
- confusion matrix
- confidence calibration bins + expected calibration error (if confidence exists)

Convenience entry points:

- `evaluate_system(...)`
- `evaluate_scenario_run(...)` (writes `evaluation_metrics.json` + `evaluation_report.md`)

## 13) Scenario corpus

`examples/scenarios/` includes:

- `compliance_review_case_01`
- `stakeholder_demo_case`
- `multi_doc_compliance`
- `draft_proposal_case_01`
- `proposal_drafting`
- `ambiguous_requirements`
- `real_case_template` (template scaffold)

Typical scenario manifest fields:

- `name`, `mode`, `goal`
- `output_subdir`
- `evaluate_after_run`
- `ground_truth_path`
- `documents[]` with role-labeled inputs

## 14) Testing and reliability status

Test suite coverage spans:

- parser/chunking
- persistent store
- output generators
- evaluation utilities
- linear pipeline mock wiring
- planner/router/model constraints
- planner-agentic engine complete/pause-resume behavior
- MCP agents and end-to-end orchestration
- scenario resolution and evaluation path
- provider selection + logging
- optional live smoke test guarded by env marker

Most recent local run (April 7, 2026):

- `pytest -q` -> `47 passed, 1 skipped, 1 warning`
- warning observed: unknown pytest option `asyncio_default_fixture_loop_scope`

## 15) Deployment/runtime

- `Dockerfile` runs `uvicorn stakeholder_dashboard:app` on `${PORT:-8000}`
- `render.yaml` configures a Docker web service for dashboard deployment
- `.env.example` includes provider and smoke-test settings

## 16) Known implementation nuances and caveats

1. Dual/parallel architectures are intentional
- Legacy linear agent classes and new MCP skill-driven agents coexist.
- Behavior may differ slightly across paths.

2. Runtime dependency gating exists
- certain modules call explicit `require_*_runtime` checks for optional deps.

3. LLM nondeterminism
- outputs can vary by provider/model/temperature and prompt format.

4. Dashboard run mode depends on `EXECUTION_MODE`
- this changes which orchestration stack is used.

5. Retrieval implementations differ
- linear path uses vector store integrations
- MCP skills implement in-memory lexical/semantic approximations + BM25/rerank

## 17) Quick operational commands

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
```

Tests:

```bash
pytest -q
```

Demo CLI:

```bash
python3 demo.py --help
python3 demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode linear
python3 demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode agentic
```

Dashboard:

```bash
./.venv/bin/python -m uvicorn stakeholder_dashboard:app --reload
```

## 18) Recommended entry points for future AI agents

If the goal is:

- understand orchestration quickly:
  - start with `demo.py`, then `compliance_agent/main.py`, `compliance_agent/agentic/engine.py`, `compliance_agent/orchestration/pipeline.py`

- modify extraction/retrieval/reasoning logic:
  - inspect both `compliance_agent/agents/*` and `compliance_agent/skills/*` to ensure the intended runtime path is changed

- modify dashboard UX or run interpretation:
  - `stakeholder_dashboard.py` + `stakeholder_dashboard/templates/*` + `stakeholder_dashboard/static/*`

- extend schema/state contracts:
  - `compliance_agent/agentic/models.py` + `compliance_agent/agentic/store.py` + tests under `tests/test_agentic_*`

