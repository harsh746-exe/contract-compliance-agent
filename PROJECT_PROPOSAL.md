# Project Proposal: Multi-Agent Contract and Policy Compliance System

**Document Version:** 1.0  
**Date:** February 2025  
**Scope:** General contract and policy compliance (domain-agnostic)

---

## 1. Executive Summary

This proposal outlines the design and implementation of an **automated Contract and Policy Compliance Agent**—a multi-agent AI system that compares any contract or policy document against a response document (e.g. proposal, commitment letter, implementation plan, design document) and produces a structured compliance matrix with evidence, labels, confidence scores, and actionable recommendations.

The system addresses a critical pain point: manual compliance review is time-consuming, inconsistent, and difficult to scale. Organizations comparing contracts to proposals, commitments to policies, or any policy to a responding document rely on human reviewers to map requirements to evidence and assign compliance status. This project delivers a **reproducible, auditable, and evaluable** pipeline that (1) extracts atomic requirements from the contract or policy text, (2) retrieves relevant evidence from the response document, (3) reasons over evidence using a strict decision rubric, and (4) flags uncertain cases for human review.

**Key deliverables:** A working system with five specialized agents orchestrated via LangGraph [1], persistent and working memory for reproducibility, CSV/JSON/Markdown outputs, and an evaluation framework with ground-truth comparison and baseline experiments. The architecture is **domain-agnostic** and applies to any contract or policy versus any response document.

---

## 2. Problem Statement and Motivation

### 2.1 The Problem

- **Volume and complexity:** Policy and contract documents contain dozens to hundreds of requirements. Response documents (proposals, technical narratives, compliance matrices) are long and unstructured. Manually matching each requirement to evidence and deciding compliance is labor-intensive and error-prone.
- **Inconsistency:** Different reviewers may interpret “compliant” vs “partial” differently. Lack of a clear rubric leads to inconsistent outcomes across teams and over time [9].
- **Traceability:** Audits and disputes require “where did this decision come from?” Without explicit evidence citations and explanations, compliance decisions are hard to defend or replicate.
- **Scalability:** As the number of contracts, policies, or proposals grows, human-only review does not scale. Organizations need tools that assist (not replace) reviewers and standardize the process.

### 2.2 Motivation

- **Automation with guardrails:** The system automates extraction, retrieval, and reasoning but constrains the reasoning agent to cite evidence and to avoid inventing compliance [12][14]. Low-confidence decisions are escalated to humans [20].
- **Structured output for downstream use:** A compliance matrix (requirement ↔ evidence ↔ label ↔ explanation) supports reporting, dashboards, and integration with procurement or governance workflows.
- **Research and evaluation:** By logging all agent actions, storing requirements and evidence, and comparing against ground truth, the project supports rigorous evaluation (precision, recall, agreement, calibration) and comparison with a single-agent baseline.

---

## 3. Objectives and Goals

### 3.1 Primary Objectives

1. **Build an end-to-end compliance pipeline** that takes as input: (a) a contract or policy document (PDF or DOCX), (b) a response document (e.g. proposal, commitment letter, implementation plan), and optionally (c) a glossary/definitions document; and produces a **compliance matrix** and supporting artifacts.
2. **Implement a multi-agent architecture** where distinct agents handle requirement extraction, classification, evidence retrieval, compliance reasoning, and confidence scoring, with clear interfaces and orchestration.
3. **Ensure traceability and reproducibility** via persistent storage of requirements and evidence, working memory (run logs), and citation of evidence chunk IDs in every decision.
4. **Provide a rigorous evaluation framework** including metrics (accuracy, Cohen's kappa [9], per-label precision/recall/F1 [10], calibration of confidence scores [11]), and comparison against a single-agent baseline.

### 3.2 Secondary Goals

- **Domain-agnostic design:** Use generic requirement categories (e.g. obligations, deliverables, reporting, confidentiality, liability) so the system works for any contract or policy type without domain-specific assumptions.
- **Human-in-the-loop:** Identify and output a “review queue” of requirements whose compliance decision has low confidence, so that human reviewers can focus effort where the system is uncertain.
- **Extensibility:** Design the system so that categories, document types, and output formats can be extended without re-architecting the pipeline.

---

## 4. Scope and Boundaries

### 4.1 In Scope

- Document ingestion and chunking (PDF, DOCX) with metadata (section, page) [7].
- Requirement extraction and normalization (atomic requirements, citations, conditions) [15].
- Requirement classification into a fixed set of categories.
- Evidence retrieval from the response document (vector [5] + keyword retrieval [6]).
- Compliance reasoning with a four-label rubric and explanations.
- Confidence scoring and escalation (accept / review / flag).
- Outputs: CSV matrix, JSON, and Markdown report.
- Evaluation: ground-truth comparison, metrics, baseline experiments.
- Logging and persistence for reproducibility and debugging.

### 4.2 Out of Scope (for This Proposal)

- Real-time or streaming processing of documents.
- Multi-document response aggregation (e.g., multiple proposals as one “response”).
- Legal or regulatory certification of the system’s decisions.
- Full-stack web UI (a CLI and scriptable API are in scope; optional UI can be a future phase).
- Automatic ingestion from external repositories (e.g., S3, SharePoint); input is file paths.

---

## 5. System Architecture and Methodology

### 5.1 High-Level Architecture

The system is organized into **five conceptual layers**:

| Layer | Purpose | Main Components |
|-------|---------|-----------------|
| **1. Ingestion** | Load and chunk policy and response documents | Document parser (PDF/DOCX), chunking strategy (sections + token cap) |
| **2. Requirement understanding** | Turn policy text into structured, categorized requirements | Requirement Extraction Agent, Requirement Classifier Agent |
| **3. Retrieval** | Find candidate evidence in the response document | Evidence Retrieval Agent (vector store [4][5] + optional keyword/BM25 [6]) |
| **4. Reasoning and decision** | Decide compliance and explain | Compliance Reasoning Agent (rubric-driven), Confidence Scorer Agent |
| **5. Output and evaluation** | Produce artifacts and measure performance | Matrix/report generators, evaluator, logging |

### 5.2 Agent Design

- **Requirement Extraction Agent:** Consumes policy chunks; uses keyword heuristics and an LLM to identify requirement sentences, split compound requirements, and output atomic requirements with source citation and conditions [15].
- **Requirement Classifier Agent:** Assigns each requirement to one (or more) generic categories (e.g., obligations, deliverables, reporting, confidentiality, liability, termination) to support retrieval and analysis.
- **Evidence Retrieval Agent:** Builds a vector index over response chunks [4][5]; for each requirement, constructs a query (requirement text + category hints), retrieves top-K chunks, and optionally fuses with keyword-based retrieval [6]. Returns evidence with chunk IDs and retrieval scores.
- **Compliance Reasoning Agent:** For each requirement and its evidence set, applies a strict rubric (compliant / partial / not_compliant / not_addressed), writes an explanation that cites evidence chunk IDs [13][14], and suggests edits when the label is not compliant.
- **Confidence and Escalation Agent:** Uses signals (retrieval scores, evidence count, label, contradictions) to assign a confidence score [11] and to place items in a review queue when confidence is below a threshold [20].

### 5.3 Orchestration and Control Flow

- **Orchestrator:** A manager (implemented as a LangGraph pipeline [1][2]) runs the agents in a defined order: ingest → extract requirements → classify → build index → for each requirement (retrieve evidence → reason → score confidence). Optionally, low-confidence items trigger a retry with query expansion before finalizing.
- **State:** A shared state object holds policy chunks, response chunks, requirements, evidence map, decisions, review queue, and references to persistent store and working memory [3].
- **Retry strategy:** If the confidence scorer marks a decision as low confidence, the orchestrator can re-invoke the retriever with an expanded query (e.g., synonyms, section headers) and then re-run the reasoner and confidence scorer, up to a maximum number of retries.

### 5.4 Memory and Traceability

- **Persistent store:** A database or set of JSON files stores the extracted requirements list, evidence per requirement, and final compliance decisions. This supports reproducibility and auditing.
- **Working memory:** Per run, a run log records which agents ran, with what inputs/outputs, errors, and retries. This supports debugging and analysis of failure modes.

---

## 6. Technical Approach

### 6.1 Technology Stack

- **Orchestration:** LangGraph [1] (state graph with nodes for each major step and conditional edges for retries).
- **LLM:** OpenAI GPT-4 (or configurable equivalent) for extraction, classification, and reasoning.
- **Embeddings and vector store:** Sentence transformers (e.g., all-MiniLM-L6-v2) [5] or OpenAI embeddings; ChromaDB [18] or FAISS [19] for the response-document index.
- **Document processing:** PyPDF2 / pdfplumber for PDF; python-docx for DOCX. Chunking by section and by token limit (e.g., 300–600 tokens per chunk) [7][8].
- **Evaluation:** Custom metrics (accuracy, kappa [9], precision/recall/F1 per label [10], confusion matrix) and optional confidence calibration [11]; scikit-learn [17] for metric computation.

### 6.2 Data Structures

- **Chunk:** `chunk_id`, `doc_type` (policy/response), `section_title`, `page_range`, `text`, metadata.
- **Requirement:** `req_id`, `requirement_text`, `source_citation`, `conditions`, `category`.
- **Evidence:** `evidence_chunk_id`, `evidence_text`, `evidence_citation`, `retrieval_score`, `requirement_id`.
- **Compliance decision:** `requirement_id`, `label`, `confidence`, `explanation`, `evidence_chunk_ids`, `suggested_edits`.

### 6.3 Output Artifacts

- **Compliance matrix (CSV):** Rows = requirements; columns = requirement text, category, evidence snippets with citations, compliance label, confidence, explanation, suggested edits.
- **JSON:** Structured export of requirements, evidence, and decisions for integration and evaluation.
- **Markdown report:** Human-readable summary and per-requirement analysis with evidence and review queue.

---

## 7. Evaluation Plan

### 7.1 Ground Truth

- For a subset of the target domain (e.g., 30–60 requirements), create human-annotated ground truth: each requirement ID mapped to a label (compliant / partial / not_compliant / not_addressed).
- Optionally, multiple annotators for inter-annotator agreement (e.g., Cohen’s kappa [9]) to assess difficulty and consistency of the task.

### 7.2 Metrics

- **Primary:** Accuracy (exact match on label), Cohen’s kappa [9] (agreement with ground truth).
- **Secondary:** Per-label precision, recall, F1 [10]; confusion matrix; calibration of confidence scores (e.g., reliability diagram or ECE [11]).
- **Operational:** Count of escalations (review queue size), distribution of labels and confidence.

### 7.3 Baselines and Ablations

- **Single-agent baseline:** One LLM call that receives policy and response text and outputs compliance decisions. Compare accuracy and kappa vs. the multi-agent system.
- **Ablations (optional):** Multi-agent with no retry; multi-agent with no confidence scoring; retrieval-only (no reasoning agent) to measure value of the reasoning step.

### 7.4 Qualitative Analysis

- Collect and log examples of: strong matches, false positives, missed requirements, and ambiguous or confusing requirements. Use these to drive discussion and future improvements.

---

## 8. Project Timeline and Milestones

| Phase | Activities | Deliverables |
|-------|------------|--------------|
| **Phase 1: Foundation** | Document ingestion (PDF/DOCX), chunking, persistent and working memory, config and project layout | Parser and chunker; memory modules; config |
| **Phase 2: Requirement layer** | Requirement Extraction Agent, Requirement Classifier Agent | Extracted and categorized requirements |
| **Phase 3: Retrieval and reasoning** | Evidence Retrieval Agent (vector + keyword), Compliance Reasoning Agent, rubric enforcement | Evidence per requirement; compliance decisions with explanations |
| **Phase 4: Orchestration and confidence** | LangGraph pipeline, Confidence Scorer Agent, retry logic, review queue | End-to-end pipeline; CSV/JSON/Markdown outputs |
| **Phase 5: Evaluation** | Ground-truth dataset, metrics, baseline, evaluation scripts and report | Evaluation report; comparison with baseline |
| **Phase 6: Documentation and demo** | README, architecture doc, proposal, demo script and example usage | Documentation; runnable demo |

---

## 9. Expected Outcomes and Deliverables

### 9.1 Artifacts

- **Codebase:** Structured project with ingestion, agents, orchestration, memory, and output modules.
- **Configuration:** Central config for model, chunk sizes, categories, confidence thresholds, and paths.
- **Demo:** Script(s) to run the pipeline on sample policy and response documents and to export the matrix and report.
- **Evaluation suite:** Scripts to compute metrics and compare with baseline; optional evaluation report generator.

### 9.2 Documentation

- **README:** Installation, usage, and high-level description.
- **Architecture document:** Layers, agents, data flow, and design choices.
- **Project proposal (this document):** Problem, objectives, architecture, evaluation, timeline.
- **Quick start guide:** Minimal steps to run the system and interpret outputs.

### 9.3 Research and Discussion Value

- **Reproducibility:** Logs and persistent store allow others to reproduce runs and inspect decisions.
- **Evaluation:** Ground-truth comparison and baseline provide a quantitative story for a paper or report.
- **Failure modes:** Categorized examples (false match, missed requirement, confusing requirement) support a substantive discussion section.

---

## 10. Risks and Mitigation

| Risk | Mitigation |
|------|------------|
| LLM variability (non-determinism) | Use low temperature; log model and seed; report variance over multiple runs if needed. |
| Hallucination of compliance [12] | Strict rubric; require citation of evidence chunk IDs [14]; no evidence → not_addressed or partial. |
| Poor retrieval for niche terms | Query expansion on retry; keyword/BM25 [6] in addition to vector search [4]; optional glossary injection. |
| Ground truth cost/time | Start with a small set (30–60 requirements); single annotator with spot checks; reuse for baseline and multi-agent. |
| Domain drift | Design categories and prompts to be configurable and domain-agnostic; avoid hard-coding industry-specific terms. |

---

## 11. Resources Required

- **Development:** Python 3.9+; standard ML/NLP stack (LangChain/LangGraph, OpenAI API, vector store, document libraries).
- **API:** OpenAI (or compatible) API key for LLM and optional embeddings.
- **Compute:** Local or cloud GPU optional for local embedding models; CPU sufficient for many runs.
- **Data:** At least one sample contract or policy and one response document; optional glossary; ground-truth labels for evaluation subset.

---

## 12. Success Criteria

- **Functional:** The system runs end-to-end on a policy and response document and produces a compliance matrix (CSV), JSON export, and Markdown report with evidence citations and a review queue.
- **Quality:** On the ground-truth subset, the multi-agent system achieves better or comparable accuracy and kappa versus the single-agent baseline.
- **Traceability:** Every compliance decision can be traced to specific evidence chunk IDs and to agent logs.
- **Usability:** A reviewer can open the CSV or report, see requirement → evidence → label → explanation, and use the review queue to prioritize manual checks.

---

## 13. Conclusion

This proposal describes a **multi-agent Contract and Policy Compliance System** that automates requirement extraction, evidence retrieval, and compliance reasoning while preserving traceability and supporting human review. The five-layer architecture and five specialized agents provide a clear, maintainable design. The system is **domain-agnostic**: it applies to any contract or policy compared against any response document, without assuming a specific industry or document type. The evaluation plan and baseline comparison offer a path to rigorous assessment and to a discussion of strengths and limitations. The intended outcome is a working, evaluable, and document-ready backbone for general contract and policy compliance checking.

---

## References

All references are listed in [REFERENCES.md](REFERENCES.md). Key citations: multi-agent orchestration [1][2][3]; retrieval and embeddings [4][5][6]; document chunking [7][8]; evaluation metrics [9][10][11]; LLM grounding and citation [12][13][14]; requirements extraction [15]; software [17][18][19]; human-in-the-loop [20].

---

## Appendix A: Glossary

- **Compliance matrix:** A table whose rows are requirements and whose columns include requirement text, category, evidence, compliance label, confidence, and explanation.
- **Evidence chunk:** A segment of the response document (with chunk_id, section, page) used to support a compliance decision.
- **Review queue:** The set of requirement IDs whose compliance decision has confidence below a chosen threshold and is recommended for human review.
- **Rubric:** The set of rules and definitions (compliant / partial / not_compliant / not_addressed) used by the Compliance Reasoning Agent.

## Appendix B: Reference Output Schema (JSON)

```json
{
  "metadata": {
    "total_requirements": 0,
    "compliance_summary": { "compliant": 0, "partial": 0, "not_compliant": 0, "not_addressed": 0 }
  },
  "requirements": [
    {
      "requirement": { "req_id": "", "requirement_text": "", "category": "", "source_citation": "" },
      "decision": { "label": "", "confidence": 0.0, "explanation": "", "suggested_edits": [] },
      "evidence": [ { "evidence_chunk_id": "", "evidence_text": "", "retrieval_score": 0.0 } ]
    }
  ]
}
```
