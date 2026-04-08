# Skills Reference

This document explains each registered skill in the compliance workflow.  
Note: `ssemble_context` in your list maps to the implemented skill name `assemble_context`.

## Retrieval Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `assemble_context` | `retrieval, hybrid, context` | `none` | Retrieval Agent | Runs query expansion (optional), semantic retrieval, lexical retrieval, and reranking to build an `evidence_map` keyed by `req_id`. |
| `bm25_search` | `retrieval, bm25, lexical` | `none` | — | Performs lexical matching over chunk text using BM25 (or a deterministic fallback scorer) and returns top-ranked chunks. |
| `rerank` | `retrieval, rerank` | `none` | — | Merges semantic and lexical result lists, normalizes scores, applies configured weights, and returns a single ranked list. |
| `vector_search` | `retrieval, semantic` | `none` | — | Computes token-based semantic similarity between requirement queries and chunks, then returns top matches. |

## Reasoning and Scoring Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `assess_compliance` | `reasoning, compliance, llm` | `standard` | Compliance Agent | Uses the configured LLM to label each requirement as compliant/partial/not_compliant/not_addressed with explanation and citations; falls back to rules when needed. |
| `rules_fallback` | `reasoning, fallback` | `none` | — | Deterministic compliance logic based on text overlap, key-term coverage, and evidence presence when LLM reasoning is unavailable or fails. |
| `validate_citations` | `reasoning, validation` | `none` | — | Removes invalid cited chunk IDs, applies confidence penalties for bad citations, and augments explanations with valid citation context. |
| `score_confidence` | `scoring, confidence` | `none` | Compliance Agent | Adjusts decision confidence using retrieval quality, evidence volume, and contradiction markers; sets `review_required` when below threshold. |
| `flag_low_confidence` | `scoring, review` | `none` | Compliance Agent | Builds a review queue of requirement IDs whose confidence is below the configured threshold. |

## Ingestion Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `parse_document` | `parsing, ingestion, generic` | `none` | Intake Agent | Parses an input file into structured chunks with metadata using the shared document parser. |
| `parse_docx` | `parsing, ingestion, docx` | `none` | — | DOCX-specific wrapper around `parse_document`. |
| `parse_pdf` | `parsing, ingestion, pdf` | `none` | — | PDF-specific wrapper around `parse_document`. |
| `parse_txt` | `parsing, ingestion, txt` | `none` | — | Plain-text wrapper around `parse_document`. |
| `chunk_document` | `chunking, ingestion` | `none` | Intake Agent | Re-splits parsed content into overlap-aware token windows, preserving source metadata and part indices. |

## Extraction and Classification Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `extract_requirements` | `extraction, requirements, hybrid` | `standard` | — | Runs lexical and LLM extraction, deduplicates results, adds stable `REQ_####` IDs, and returns normalized requirement objects. |
| `lexical_extract` | `extraction, requirements` | `none` | Extraction Agent | Detects requirement-like sentences using keyword cues and produces requirement candidates with provenance metadata. |
| `llm_extract` | `extraction, requirements, llm` | `standard` | — | Uses an LLM to atomize and structure requirements in JSON format; falls back to lexical extraction on provider errors. |
| `split_compound` | `extraction, cleanup` | `none` | — | Splits a compound requirement sentence into multiple atomic requirements using conjunction delimiters. |
| `classify_requirements` | `classification, requirements, batch` | `fast` | Extraction Agent | Classifies each extracted requirement into category/subcategory with confidence, using rule-first then LLM escalation. |
| `keyword_classify` | `classification, requirements` | `none` | — | Deterministic keyword-based requirement category assignment. |
| `llm_classify` | `classification, requirements, llm` | `fast` | — | LLM-based requirement category classification with confidence score; fallback to keyword classification on failure. |

## QA and Drafting Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `check_acronyms` | `qa, text` | `none` | — | Extracts uppercase acronym tokens from text for quality checks and glossary support. |
| `coverage_check` | `qa, coverage` | `none` | — | Verifies that every extracted requirement has an associated decision. |
| `detect_placeholders` | `qa, draft` | `none` | — | Detects placeholder markers such as `TBD`, `TODO`, and insertion prompts. |
| `final_qa_check` | `qa, gate` | `none` | Qa Agent | Final quality gate that checks missing decisions and review-required items before completion/approval. |
| `format_check` | `qa, format` | `none` | — | Performs lightweight formatting checks (for example triple blank lines and line count). |
| `review_draft` | `qa, draft, review` | `none` | — | Reviews draft sections for quality issues, missing coverage, and rewrite requirements. |
| `generate_outline` | `drafting, outline` | `none` | — | Creates a traceable section outline from requirements and compliance decisions, optionally prefixed with historical context. |
| `write_section` | `drafting, write` | `none` | Drafting Agent | Drafts one section with explicit requirement IDs and evidence-backed coverage status. |
| `rewrite_section` | `drafting, rewrite` | `none` | Drafting Agent | Rewrites weak or placeholder-heavy sections into cleaner, handoff-ready language while keeping requirement traceability. |

## Comparison Skills

| Skill | Tags | LLM Tier | Primary Agent | Explanation |
|---|---|---|---|---|
| `match_prior_docs` | `comparison, historical` | `none` | — | Scores prior documents for relevance to a new source document using term overlap and returns ranked matches. |
| `compute_delta` | `comparison, delta` | `none` | — | Computes term-level differences between current and prior text (`new_terms` vs `reused_terms`). |
| `summarize_changes` | `comparison, summary` | `none` | Comparison Agent | Produces a concise historical reuse/change summary based on top prior-document matches. |
