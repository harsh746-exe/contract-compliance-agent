# System Architecture

## Overview

This system runs a single MCP architecture: an orchestrated team of specialized agents communicating over an in-process message bus.

## Core Components

1. **MCP Bus (`compliance_agent/mcp/`)**
- Provides message routing, agent discovery, and audit logging.
- Ensures all agent-to-agent interactions are observable.

2. **Orchestrator (`compliance_agent/agents/orchestrator.py`)**
- Plans next actions based on current workflow state.
- Delegates work to specialist agents.
- Collects outputs into a coherent run result.

3. **Specialist Agents (`compliance_agent/agents/`)**
- `intake_agent`: document parsing/chunking preparation.
- `extraction_agent`: requirement extraction.
- `retrieval_agent`: evidence retrieval and context assembly.
- `compliance_agent`: compliance assessment and confidence scoring.
- `comparison_agent`: historical comparison support.
- `drafting_agent`: proposal drafting support.
- `qa_agent`: quality checks and consistency validation.
- `notification_agent`: stakeholder notifications.
- `chat_agent`: question answering over run outputs.

4. **Skill Registry (`compliance_agent/skills/`)**
- Central registry of stateless capabilities invoked by agents.
- Skills are grouped by parsing, extraction, classification, retrieval, reasoning, scoring, comparison, drafting, and QA.

5. **Run Artifact Export (`compliance_agent/output/export.py`)**
- Persists run outputs to a stable run directory.
- Emits machine-readable and stakeholder-facing artifacts.

## End-to-End Flow

1. User submits goal and document set.
2. Orchestrator routes parsing/intake work.
3. Requirements are extracted and categorized.
4. Evidence is retrieved per requirement.
5. Compliance decisions and confidence are produced.
6. Optional comparison/drafting/QA stages execute based on workflow.
7. Artifacts and audit log are exported.

## Transparency and Traceability

- Every MCP message is captured in `audit_log.json`.
- Workflow state snapshots are exported for post-run analysis.
- Dashboard views are generated from run artifacts rather than hidden state.

## Outputs

Typical outputs per run:

- `requirements.json`
- `evidence_map.json`
- `compliance_decisions.json`
- `compliance_matrix.csv`
- `compliance_report.md`
- `compliance_results.json`
- `audit_log.json`
- `workflow_result.json`
- `qa_report.json`

## Notes

This repository intentionally maintains one execution architecture (MCP multi-agent) to reduce complexity and keep behavior easy to reason about.
