from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUTPUT_PATH = Path("output/pdf/contract_compliance_agent_in_depth_guide.pdf")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#334e68"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=8,
            spaceBefore=2,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#243b53"),
            spaceAfter=5,
            spaceBefore=4,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#334e68"),
            spaceAfter=3,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7.8,
            leading=9.5,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=2,
        ),
    }


def bullets(items, styles, style_name="body", left=14):
    return ListFlowable(
        [ListItem(Paragraph(item, styles[style_name])) for item in items],
        bulletType="bullet",
        leftIndent=left,
        bulletFontName="Helvetica",
        bulletFontSize=8,
    )


def callout_table(callouts, styles):
    rows = [[Paragraph("<b>Implementation Callouts</b>", styles["h2"])]]
    for text in callouts:
        rows.append([Paragraph(text, styles["callout"])])
    table = Table(rows, colWidths=[6.9 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2ec")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f0f4f8")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#829ab1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bcccdc")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def add_page_number(canvas, doc):
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#627d98"))
    canvas.drawRightString(7.25 * inch, 0.35 * inch, f"Page {doc.page}")


def build_pdf(output_path: Path):
    styles = _styles()
    story = []

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Page 1
    story.append(Spacer(1, 0.45 * inch))
    story.append(Paragraph("Contract/Policy Compliance Agent", styles["title"]))
    story.append(Paragraph("In-Depth Application Guide (Repo-Evidence Based)", styles["subtitle"]))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Document Metadata", styles["h2"]))
    story.append(
        bullets(
            [
                f"Generated: {generated}",
                "Repository focus: architecture, features, operations, and startup workflow.",
                "Evidence policy: all claims are based on checked-in files and source modules.",
                "Formatting intent: short sections, headings, and bullets for rapid scanning.",
                "Scope note: this codebase has 3 runtime surfaces that share concepts but differ in orchestration.",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 0.14 * inch))
    story.append(Paragraph("Guide Map", styles["h2"]))
    story.append(
        bullets(
            [
                "1) What it is.",
                "2) Who it is for (primary persona + supporting roles).",
                "3) What it does (features with implementation callouts).",
                "4) How it works (components, services, data flows).",
                "5) How to run (getting started commands and paths).",
                "6) Limits and Not found in repo declarations.",
            ],
            styles,
        )
    )
    story.append(PageBreak())

    # Page 2
    story.append(Paragraph("1) What It Is", styles["h1"]))
    story.append(Paragraph("Definition", styles["h2"]))
    story.append(
        bullets(
            [
                "Prototype/MVP for automated compliance checks between a requirement source document and a response/proposal document.",
                "Supports optional supporting context: glossary, prior contracts/proposals, amendments, past performance docs.",
                "Produces requirement-level compliance decisions, evidence traces, confidence signals, and export artifacts.",
                "Includes offline-first testing and optional live model paths.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Execution Surfaces Present In Repo", styles["h2"]))
    story.append(
        bullets(
            [
                "Linear LangGraph pipeline (`compliance_agent/orchestration/pipeline.py`).",
                "Planner-evaluator bounded agentic engine (`compliance_agent/agentic/engine.py`).",
                "MCP-style autonomous multi-agent runtime with message bus (`compliance_agent/main.py`, `compliance_agent/mcp/*`).",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "README.md: project summary + status + usage modes.",
        "PROJECT_CONTEXT.md: explicit note that 3 orchestration styles run in parallel.",
        "compliance_agent/__init__.py: lazy exports for `ComplianceAgent` and `AgenticWorkflowEngine`.",
    ], styles))
    story.append(PageBreak())

    # Page 3
    story.append(Paragraph("2) Who It Is For (Primary Persona)", styles["h1"]))
    story.append(Paragraph("Primary Persona (Evidence-Based Inference)", styles["h2"]))
    story.append(
        bullets(
            [
                "Compliance program stakeholders who need auditable requirement-to-evidence decisions.",
                "Procurement/proposal operations users reviewing source vs response alignment before submission.",
                "Review leads who need a dashboard view of runs, artifacts, timelines, and review queues.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Explicit Persona Naming", styles["h2"]))
    story.append(
        bullets(
            [
                "Named persona profile document: <b>Not found in repo.</b>",
                "Role-specific permissions model or RBAC mapping: <b>Not found in repo.</b>",
            ],
            styles,
        )
    )
    story.append(Paragraph("Likely User Groups In Code Paths", styles["h2"]))
    story.append(
        bullets(
            [
                "Technical operators: CLI (`demo.py`) with modes `mcp`, `linear`, `agentic`.",
                "Non-technical reviewers: FastAPI stakeholder workspace (`stakeholder_dashboard.py`).",
                "Evaluation owners: scenario metrics/report generation (`evaluation/__init__.py`, `evaluation/metrics.py`).",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "stakeholder_dashboard.py docstring: 'Stakeholder-facing operations UI'.",
        "README.md + QUICKSTART.md: dedicated dashboard launch workflow and artifact download focus.",
        "stakeholder_dashboard templates/routes: run detail, activity, workflow, files, uploads.",
    ], styles))
    story.append(PageBreak())

    # Page 4
    story.append(Paragraph("3) What It Does - Inputs And Requirement Pipeline", styles["h1"]))
    story.append(Paragraph("Document Intake + Parsing", styles["h2"]))
    story.append(
        bullets(
            [
                "Accepts `.pdf`, `.docx`, `.txt` input files through parser and scenario manifests.",
                "PDF parser uses `pdfplumber` first, then `PyPDF2` fallback when needed.",
                "Heuristic section-header detection supports chunk metadata (section, page range, file).",
                "TXT and DOCX are sectionized and converted to structured chunk objects/dicts.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Requirement Extraction + Classification", styles["h2"]))
    story.append(
        bullets(
            [
                "Extraction agent selects strategy (`lexical`, `hybrid`, or `llm`) based on chunk structure signals.",
                "Requirement records normalized with stable IDs (`REQ_0001`, etc.) and provenance.",
                "Classification uses keyword mapping first, with LLM fallback for low-confidence cases.",
                "Category tags are attached to requirements for downstream retrieval and drafting grouping.",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "compliance_agent/ingestion/document_parser.py: `DocumentParser.parse` + format-specific parsers.",
        "compliance_agent/skills/extraction.py: `lexical_extract`, `llm_extract`, `extract_requirements`.",
        "compliance_agent/agents/extraction_agent.py: strategy selection + normalization.",
        "compliance_agent/skills/classification.py: keyword and LLM classify paths.",
    ], styles))
    story.append(PageBreak())

    # Page 5
    story.append(Paragraph("4) What It Does - Retrieval, Decisions, Confidence, Exports", styles["h1"]))
    story.append(Paragraph("Evidence Retrieval", styles["h2"]))
    story.append(
        bullets(
            [
                "Hybrid retrieval mixes semantic scoring and lexical BM25 scoring.",
                "Requirement-level retrieval plans tune strategy and weights (`semantic`, `lexical`, `bm25_heavy`, `semantic_heavy`).",
                "Query expansion can add acronym/number/domain expansions before retrieval.",
                "Reranking computes hybrid score and keeps top evidence per requirement.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Compliance Decisions + Confidence", styles["h2"]))
    story.append(
        bullets(
            [
                "Decision labels: `compliant`, `partial`, `not_compliant`, `not_addressed`.",
                "Citation validation removes invalid chunk IDs and applies confidence penalty.",
                "Confidence scorer adjusts by evidence quality, contradictions, and evidence volume.",
                "Low-confidence decisions are pushed into `review_queue` for escalation.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Exports", styles["h2"]))
    story.append(
        bullets(
            [
                "CSV matrix (`*_matrix.csv`).",
                "JSON bundle (`*_results.json` or `compliance_results.json`).",
                "Markdown report (`*_report.md` / `compliance_report.md`).",
                "Agentic artifacts: `workflow_summary`, `handoff_summary`, optional `comparison_summary` and `draft_outline`.",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "compliance_agent/skills/retrieval.py: `vector_search`, `bm25_search`, `rerank`, `assemble_context`.",
        "compliance_agent/skills/reasoning.py: `assess_compliance`, calibration, citation validation.",
        "compliance_agent/skills/scoring.py: `score_confidence`, `flag_low_confidence`.",
        "compliance_agent/output/matrix_generator.py + report_generator.py + export.py.",
    ], styles))
    story.append(PageBreak())

    # Page 6
    story.append(Paragraph("5) What It Does - Agentic, MCP, And Dashboard Features", styles["h1"]))
    story.append(Paragraph("Planner Agentic Engine", styles["h2"]))
    story.append(
        bullets(
            [
                "Bounded action vocabulary (`route_documents`, `prepare_context`, `run_compliance_pipeline`, `reanalyze_low_confidence`, etc.).",
                "Evaluator can `accept`, `retry_subset`, `branch_to_other_action`, request approval, or block.",
                "Supports pause/resume with persisted workflow state (`run(..., resume=True)`).",
                "Drafting path can generate, evaluate, and rewrite draft outlines when goal requests drafting.",
            ],
            styles,
        )
    )
    story.append(Paragraph("MCP Multi-Agent Runtime", styles["h2"]))
    story.append(
        bullets(
            [
                "Bootstraps orchestrator + 7 role agents over in-process MCP bus.",
                "Bus logs `goal/result/tool_call/tool_result/status/error/spawn/terminate` events.",
                "Orchestrator uses planner loop, can spawn temporary reanalysis sub-agent for low-confidence subsets.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Stakeholder Dashboard", styles["h2"]))
    story.append(
        bullets(
            [
                "Routes for runs, documents, file manager, activity timeline, workflow view, and artifact downloads.",
                "Upload path supports source/response plus optional glossary/context, then launches run.",
                "Run pages expose metadata, decisions, evaluation metrics, and audit log/workflow visualization.",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "compliance_agent/agentic/engine.py + planner.py + evaluator.py + store.py.",
        "compliance_agent/main.py: bus/registry/agents bootstrap and `run` entrypoint.",
        "compliance_agent/mcp/bus.py + protocol.py: message contract and audit log.",
        "stakeholder_dashboard.py: `/runs`, `/activity`, `/run-upload`, `/runs/{scope}/workflow`.",
    ], styles))
    story.append(PageBreak())

    # Page 7
    story.append(Paragraph("6) How It Works - Architecture Components/Services", styles["h1"]))
    story.append(Paragraph("Core Components", styles["h2"]))
    story.append(
        bullets(
            [
                "Config + runtime guards: provider config, chunk/retrieval/threshold knobs, dependency checks.",
                "Ingestion service: parser + chunking modules create structured chunks with metadata.",
                "Requirement service: extraction + classification agents/skills.",
                "Retrieval service: vector and lexical retrieval with reranking and per-requirement plans.",
                "Decision service: compliance reasoning + citation validation + confidence adjustment.",
                "State/persistence: persistent store, workflow state store, working memory logs.",
                "Output service: CSV/JSON/Markdown generators and run artifact exporter.",
                "UI service: FastAPI dashboard with Jinja templates/static assets.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Interfaces", styles["h2"]))
    story.append(
        bullets(
            [
                "CLI entrypoint: `demo.py`.",
                "Python API entrypoints: `ComplianceAgent`, `AgenticWorkflowEngine`.",
                "Web API entrypoint: `stakeholder_dashboard:app`.",
                "Container runtime entrypoint: `uvicorn stakeholder_dashboard:app` via Dockerfile.",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "config.py + compliance_agent/runtime.py.",
        "compliance_agent/orchestration/pipeline.py (linear service graph).",
        "compliance_agent/agentic/models.py (state/action schemas).",
        "Dockerfile + render.yaml (deployment service definition).",
    ], styles))
    story.append(PageBreak())

    # Page 8
    story.append(Paragraph("7) How It Works - Data Flow By Execution Surface", styles["h1"]))
    story.append(Paragraph("A) Linear Flow", styles["h2"]))
    story.append(
        bullets(
            [
                "Input files -> parse/chunk -> extract requirements -> classify -> build index -> retrieve evidence -> reason -> score -> optional retry -> export.",
                "Context docs are merged into response corpus before retrieval.",
            ],
            styles,
        )
    )
    story.append(Paragraph("B) Planner Agentic Flow", styles["h2"]))
    story.append(
        bullets(
            [
                "Goal + documents -> route manifest -> prepare context -> optional comparison -> compliance run -> optional reanalysis -> optional drafting/evaluation/rewrite -> finalize outputs.",
                "Evaluator controls branch/retry/approval decisions and can pause workflow awaiting approval.",
                "Workflow state snapshots are persisted to `data/workflow_state/*`.",
            ],
            styles,
        )
    )
    story.append(Paragraph("C) MCP Multi-Agent Flow", styles["h2"]))
    story.append(
        bullets(
            [
                "`main.run` bootstraps bus, skill registry, and agents -> orchestrator planning loop dispatches goals to role agents -> skills invoked via tool calls -> final exports written by run exporter.",
                "Audit log captures agent communication and tool events for workflow replay and dashboard visualization.",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "compliance_agent/orchestration/pipeline.py: graph nodes and conditional retry.",
        "compliance_agent/agentic/engine.py: `_execute_action`, `_apply_evaluator_decision`, `_finalize_outputs`.",
        "compliance_agent/agents/orchestrator.py: dispatch methods and planning trace.",
        "compliance_agent/output/export.py: `RunArtifactsExporter.export`.",
    ], styles))
    story.append(PageBreak())

    # Page 9
    story.append(Paragraph("8) How To Run - Getting Started", styles["h1"]))
    story.append(Paragraph("Local Setup", styles["h2"]))
    story.append(
        bullets(
            [
                "`python3 -m venv .venv`",
                "`source .venv/bin/activate`",
                "`pip install -r requirements.txt`",
                "`python -m spacy download en_core_web_sm`",
                "`cp .env.example .env` and set provider keys (`DEEPINFRA_API_KEY` or `OPENAI_API_KEY`).",
            ],
            styles,
        )
    )
    story.append(Paragraph("Verification", styles["h2"]))
    story.append(
        bullets(
            [
                "`pytest -q`",
                "`python demo.py --help`",
                "Optional live smoke: `RUN_LIVE_LLM_TESTS=1 pytest -q -m live`",
            ],
            styles,
        )
    )
    story.append(Paragraph("Run Modes", styles["h2"]))
    story.append(
        bullets(
            [
                "MCP mode: `python demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode mcp`",
                "Linear mode: `python demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode linear`",
                "Agentic engine mode: `python demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --mode agentic`",
                "Evaluate existing scenario: `python demo.py --scenario-dir examples/scenarios/compliance_review_case_01 --evaluate-only`",
                "Resume paused agentic run: `python demo.py --mode agentic --resume-run-id <run_id>`",
                "Dashboard: `./.venv/bin/python -m uvicorn stakeholder_dashboard:app --reload`",
            ],
            styles,
        )
    )
    story.append(callout_table([
        "README.md + QUICKSTART.md + run_demo.sh: startup and command examples.",
        "demo.py: parser flags, scenario wiring, mode handlers.",
        "stakeholder_dashboard.py: `/health` + UI routes for run execution and downloads.",
    ], styles))
    story.append(PageBreak())

    # Page 10
    story.append(Paragraph("9) Limits, Not Found In Repo, And Final Notes", styles["h1"]))
    story.append(Paragraph("Known Limits In Repo", styles["h2"]))
    story.append(
        bullets(
            [
                "Repository explicitly marks system as prototype/MVP and not production hardened.",
                "LLM outputs are nondeterministic across runs/providers/models.",
                "Some paths require optional dependencies (`langgraph`, `langchain`, `chromadb`, `sentence-transformers`) and enforce runtime checks.",
                "Multiple orchestration surfaces are intentionally parallel and may not behave identically.",
            ],
            styles,
        )
    )
    story.append(Paragraph("Required 'Not found in repo' Declarations", styles["h2"]))
    story.append(
        bullets(
            [
                "Single canonical production architecture diagram artifact: <b>Not found in repo.</b>",
                "Formal primary persona profile document with explicit acceptance criteria: <b>Not found in repo.</b>",
                "Security hardening guide (authN/authZ, data retention policy, threat model): <b>Not found in repo.</b>",
                "SLO/SLA or performance benchmark targets for production scale: <b>Not found in repo.</b>",
            ],
            styles,
        )
    )
    story.append(Paragraph("Practical Operator Checklist", styles["h2"]))
    story.append(
        bullets(
            [
                "Choose execution surface first: linear, planner-agentic, or MCP runtime.",
                "Use scenarios for reproducible runs and stable output subdirectories.",
                "Inspect `review_queue`, confidence, and citation validity before handoff.",
                "Package and share artifacts (`matrix`, `results_json`, `report`, plus agentic summaries).",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("End of guide.", styles["small"]))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title="Contract Compliance Agent - In-Depth Guide",
        author="Codex",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


if __name__ == "__main__":
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(OUTPUT_PATH)
    print(str(OUTPUT_PATH.resolve()))
