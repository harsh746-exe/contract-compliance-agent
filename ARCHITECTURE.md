# System Architecture

## Overview

This document describes the architecture of the Contract/Policy Compliance Agent system, a multi-agent system for automated compliance checking [1][2]. For full references, see [REFERENCES.md](REFERENCES.md).

## Architecture Layers

### 1. Ingestion Layer

**Components:**
- `DocumentParser`: Parses PDF and DOCX files
- `chunking`: Splits documents into manageable chunks

**Responsibilities:**
- Load documents (PDF/DOCX)
- Extract text with structure (sections, pages)
- Chunk documents by sections and size
- Preserve metadata (page numbers, sections, citations)

**Output:** List of `DocumentChunk` objects with metadata

### 2. Requirement Understanding Layer

**Agents:**
- **Requirement Extraction Agent**: Extracts atomic requirements from policy text
- **Requirement Classifier Agent**: Tags requirements by category

**Responsibilities:**
- Identify requirement statements (keywords: shall, must, required, etc.)
- Split compound requirements into atomic ones
- Preserve conditions and context
- Classify requirements into categories (security, reporting, privacy, etc.)

**Output:** List of `Requirement` objects with categories

### 3. Retrieval Layer

**Agent:**
- **Evidence Retrieval Agent**: Retrieves relevant evidence from response documents

**Responsibilities:**
- Build vector index from response document chunks [4][5]
- Generate search queries from requirements
- Retrieve top-K evidence chunks using semantic search
- Combine vector search with keyword matching [6]
- Return evidence with retrieval scores

**Output:** List of `Evidence` objects per requirement

### 4. Reasoning and Decision Layer

**Agent:**
- **Compliance Reasoning Agent**: Makes compliance decisions

**Responsibilities:**
- Apply decision rubric:
  - **Compliant**: Evidence explicitly satisfies requirement
  - **Partial**: Evidence related but missing specifics
  - **Not Addressed**: No relevant evidence found
  - **Not Compliant**: Evidence contradicts requirement
- Generate explanations citing evidence
- Provide suggested edits for non-compliant items

**Output:** `ComplianceDecision` objects with labels and explanations

### 5. Output and Evaluation Layer

**Components:**
- **Confidence Scorer Agent**: Assigns confidence scores
- **Matrix Generator**: Creates CSV compliance matrix
- **Report Generator**: Creates Markdown reports
- **Evaluator**: Compares against ground truth

**Responsibilities:**
- Score confidence based on signals (retrieval scores, evidence count, etc.)
- Flag items for human review
- Generate compliance matrix (CSV)
- Generate detailed reports (Markdown)
- Evaluate system performance

**Output:** CSV matrix, JSON results, Markdown reports

## Agent Design

### Agent 1: Requirement Extraction Agent

**Input:** Policy document chunks
**Output:** List of atomic requirements

**Process:**
1. Group chunks by section
2. Extract requirements using keyword patterns
3. Use LLM to refine and split compound requirements
4. Deduplicate requirements
5. Assign unique IDs

**Tools:** LLM (GPT-4), regex patterns

### Agent 2: Requirement Classifier Agent

**Input:** List of requirements
**Output:** Requirements with category tags

**Process:**
1. Quick keyword-based classification
2. LLM-based classification for uncertain cases
3. Assign primary category and optional subcategory

**Tools:** LLM, keyword matching

### Agent 3: Evidence Retrieval Agent

**Input:** Requirements, response document chunks
**Output:** Evidence chunks per requirement

**Process:**
1. Build vector index from response chunks [5][18]
2. Generate search query from requirement + category
3. Retrieve top-K chunks using semantic search [4]
4. Perform keyword-based search for exact matches
5. Merge and rank evidence

**Tools:** ChromaDB [18] vector store, SentenceTransformer [5] embeddings, keyword search [6]

### Agent 4: Compliance Reasoning Agent

**Input:** Requirement + evidence chunks
**Output:** Compliance decision

**Process:**
1. If no evidence → "not_addressed"
2. Apply decision rubric using LLM
3. Generate explanation citing evidence chunk IDs [13][14]
4. Provide suggested edits if not compliant

**Tools:** LLM with structured prompt and rubric

### Agent 5: Confidence Scorer Agent

**Input:** Compliance decision + evidence
**Output:** Confidence score + escalation status

**Process:**
1. Calculate confidence signals:
   - Retrieval score distribution
   - Evidence count
   - Label baseline confidence
   - Contradiction detection
2. Adjust base confidence
3. Determine escalation (accept/review/flag)

**Tools:** Heuristics, optional LLM scoring

## Orchestration

### LangGraph Pipeline

The system uses LangGraph [1] for orchestration with the following flow:

```
ingest_documents → extract_requirements → classify_requirements 
→ build_index → retrieve_evidence → reason_compliance 
→ score_confidence → [retry if needed] → END
```

**State Management:**
- `ComplianceState` TypedDict holds all intermediate data
- Persistent store saves requirements, evidence, decisions
- Working memory logs all agent actions

**Retry Logic:**
- If confidence < threshold, retry with query expansion
- Maximum retries: 3
- Only retry low-confidence requirements

## Memory Systems

### Persistent Store

Stores:
- Extracted requirements (JSON)
- Evidence per requirement (JSON)
- Compliance decisions (JSON)

Location: `data/persistent_store/`

### Working Memory

Tracks per-run:
- Agent execution logs
- Intermediate results
- Errors and retries
- Performance metrics

Location: `output/logs/`

## Data Flow

1. **Document Ingestion**
   - Policy PDF/DOCX → chunks with metadata
   - Response PDF/DOCX → chunks with metadata

2. **Requirement Extraction**
   - Policy chunks → atomic requirements
   - Each requirement has: text, citation, conditions

3. **Classification**
   - Requirements → categorized requirements

4. **Evidence Retrieval**
   - Requirements + response chunks → evidence per requirement
   - Vector search + keyword search

5. **Compliance Reasoning**
   - Requirement + evidence → compliance decision
   - Decision includes: label, explanation, confidence, suggestions

6. **Confidence Scoring**
   - Decision + evidence → adjusted confidence + escalation

7. **Output Generation**
   - All data → CSV matrix + JSON + Markdown report

## Evaluation Framework

### Metrics

- **Accuracy**: Overall correctness
- **Cohen's Kappa**: Inter-annotator agreement
- **Per-label metrics**: Precision, recall, F1 for each label
- **Confusion matrix**: Detailed error analysis
- **Calibration**: Confidence score calibration

### Baselines

- **Single-agent baseline**: One LLM call for everything
- **Multi-agent system**: Full pipeline with all agents

### Ground Truth Format

```json
{
  "REQ_0001": "compliant",
  "REQ_0002": "partial",
  ...
}
```

## Configuration

Key settings in `config.py`:

- Chunk size: 600 tokens
- Top-K retrieval: 5 chunks
- Confidence thresholds: 0.75 (high), 0.50 (medium)
- Max retries: 3
- Categories: configurable set of generic categories (see config)

## Domain: General Contract and Policy

The system is **domain-agnostic**. It uses generic requirement categories that apply to any contract or policy, for example:
- Obligations and duties
- Deliverables and milestones
- Reporting and notifications
- Confidentiality and data protection
- Liability, indemnity, and insurance
- Termination and dispute resolution
- Payment and fees
- Audit and documentation

No industry-specific terms (e.g. RFP, HIPAA, SOP) are hard-coded; categories and prompts are generic.

## Output Formats

### CSV Matrix

Columns:
- Requirement ID, Text, Category, Citation
- Compliance Label, Confidence, Explanation
- Evidence Count, Top Evidence Snippet, Citations
- Suggested Edits

### JSON Output

Structure:
```json
{
  "metadata": {...},
  "requirements": [
    {
      "requirement": {...},
      "decision": {...},
      "evidence": [...]
    }
  ]
}
```

### Markdown Report

- Executive summary
- Requirements grouped by category
- Detailed analysis per requirement
- Review queue

## Extensibility

The system is designed to be extensible:

1. **New categories**: Add to `config.CATEGORIES`
2. **New document formats**: Extend `DocumentParser`
3. **Custom agents**: Implement agent interface
4. **Different domains**: Update categories and prompts
5. **Alternative LLMs**: Swap LLM provider in agent initialization

## References

See [REFERENCES.md](REFERENCES.md) for the full bibliography. In-text citations refer to that list (e.g. [1] LangGraph, [4] RAG, [5] Sentence-BERT, [9] Cohen's kappa, [18] ChromaDB).
