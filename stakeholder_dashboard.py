"""Stakeholder-facing operations UI for the compliance agent."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
from compliance_agent.agents.notification_agent import generate_notifications
from compliance_agent.ingestion.document_parser import DocumentParser
from compliance_agent.main import run as mcp_run
from compliance_agent.scenarios import (
    extract_linear_inputs,
    load_scenario,
    scenario_ground_truth_path,
    scenario_output_dir,
)
from compliance_agent.skills import (
    chunking,
    classification,
    comparison,
    drafting,
    extraction,
    parsing,
    qa,
    reasoning,
    retrieval,
    scoring,
)
from compliance_agent.skills.registry import SkillRegistry
from evaluation import evaluate_scenario_run


logger = logging.getLogger(__name__)

# In-memory tracker for live background run progress.
_run_status: Dict[str, Dict[str, Any]] = {}
_run_lock = threading.Lock()


BASE_DIR = Path(__file__).parent.resolve()
DASHBOARD_DIR = BASE_DIR / "stakeholder_dashboard"
DEFAULT_SCENARIO_DIR = BASE_DIR / "examples" / "scenarios" / "stakeholder_demo_case"
COMPANY_SYSTEM_DIR = BASE_DIR / "examples" / "mock_company_systems" / "northstar_it_services_2025"
DOCUMENT_REGISTER_PATH = COMPANY_SYSTEM_DIR / "document_register.csv"
CUSTOM_RUNS_DIR = config.OUTPUT_DIR / "dashboard_runs"
UPLOADS_DIR = BASE_DIR / "data" / "uploads"
LEGACY_UPLOADS_DIR = BASE_DIR / "data" / "dashboard_uploads"
CUSTOM_RUNS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
TEXT_PREVIEW_SUFFIXES = {".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml"}
MANAGED_ROOTS = {
    "company-records": {
        "label": "Company Records",
        "description": "Policies, contracts, reports, security evidence, finance summaries, and incident history.",
        "path": COMPANY_SYSTEM_DIR,
    },
    "case-outputs": {
        "label": "Case Outputs & Logs",
        "description": "Generated reports, matrices, results JSON, workflow summaries, and execution logs.",
        "path": BASE_DIR / "output",
    },
    "uploaded-inputs": {
        "label": "Uploaded Inputs",
        "description": "Files that were uploaded into the workspace for custom runs.",
        "path": UPLOADS_DIR,
    },
}
WORKSPACE_ROOTS = {
    "output": BASE_DIR / "output",
    "data": BASE_DIR / "data",
    "examples": BASE_DIR / "examples",
}
DELETABLE_ROOTS = {
    "output",
    "uploads",
}

HIDDEN_RUNS = {"zzz_execution_mode_check", "scenario_case"}

STAGE_EXPLANATIONS = {
    "forecast": "These opportunities are on our radar. No agent work yet; we are gathering intelligence and building relationships.",
    "solicitation": "The RFP or RFI is out. Documents are ready for the agent team to begin compliance analysis.",
    "review": "The agent team has analyzed (or is analyzing) these contracts. Open the analysis to see findings and recommended actions.",
    "drafting": "Agents are helping draft or refine proposal responses based on compliance findings.",
    "submitted": "The proposal is submitted. Agent analysis informed the final submission while we await an award decision.",
    "active": "The contract is awarded and in delivery. Performance and execution metrics are tracked here.",
    "completed": "The contract is complete. This past performance record supports future proposals.",
}

CATEGORY_DESCRIPTIONS = {
    "opportunities": "Solicitations, proposals, and amendments for each contract. The agent team pulls SOW requirements and proposal responses from here.",
    "past_performance": "Contract summaries, CPARS narratives, and performance data used when drafting past performance sections.",
    "corporate": "Capability statements, certifications, and proposal templates available for corporate volume drafting.",
    "hr": "Key personnel resumes and certifications used to verify staffing requirements.",
    "management": "Facility information, financial data, and insurance records used for administrative volume support.",
}

ARTIFACT_LABELS = {
    "compliance_decisions.json": "Compliance findings (JSON)",
    "compliance_matrix.csv": "Compliance matrix (spreadsheet)",
    "compliance_report.md": "Full compliance report",
    "compliance_results.json": "Results summary (JSON)",
    "evidence_map.json": "Evidence mapping",
    "requirements.json": "Extracted requirements",
    "audit_log.json": "Agent communication log",
    "workflow_result.json": "Orchestrator planning trace",
    "qa_report.json": "Quality assurance report",
    "run_manifest.json": "Run configuration",
    "document_manifest.json": "Document inventory",
    "retrieval_plans.json": "Search strategy log",
    "evaluation_metrics.json": "Accuracy evaluation",
    "evaluation_report.md": "Evaluation report",
    "comparison_summary.json": "Historical comparison",
}

AGENT_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "orchestrator": {
        "title": "Orchestrator",
        "role": "Team coordinator",
        "description": "Plans the analysis workflow and decides what the team should do next based on intermediate results.",
        "analogy": "Like a project manager running a review meeting.",
    },
    "intake_agent": {
        "title": "Intake Specialist",
        "role": "Document processing",
        "description": "Reads uploaded documents, identifies key sections, and prepares content for downstream analysis.",
        "analogy": "Like the person organizing the binder before a review.",
    },
    "extraction_agent": {
        "title": "Requirements Analyst",
        "role": "Requirement extraction",
        "description": "Extracts individual requirements from the SOW and tags each by category and priority.",
        "analogy": "Like the analyst highlighting every 'shall' statement in the SOW.",
    },
    "retrieval_agent": {
        "title": "Evidence Researcher",
        "role": "Evidence gathering",
        "description": "Searches proposals and supporting records for evidence tied to each requirement.",
        "analogy": "Like the reviewer cross-referencing the proposal against the checklist.",
    },
    "compliance_agent": {
        "title": "Compliance Assessor",
        "role": "Compliance judgment",
        "description": "Assesses whether requirements are met, partially met, or missing, with confidence and rationale.",
        "analogy": "Like the color-team reviewer marking each requirement green, yellow, or red.",
    },
    "comparison_agent": {
        "title": "Historical Analyst",
        "role": "Document comparison",
        "description": "Compares current work against prior contracts and proposals to identify deltas and reusable content.",
        "analogy": "Like the capture manager reviewing what was proposed last time.",
    },
    "drafting_agent": {
        "title": "Proposal Writer",
        "role": "Content generation",
        "description": "Drafts proposal sections from requirements and evidence, then iterates based on QA feedback.",
        "analogy": "Like the writer producing technical volume sections.",
    },
    "qa_agent": {
        "title": "Quality Reviewer",
        "role": "Quality assurance",
        "description": "Checks outputs for completeness, consistency, and quality before delivery.",
        "analogy": "Like the final reviewer before submission.",
    },
    "notification_agent": {
        "title": "Notification Agent",
        "role": "Monitoring and alerts",
        "description": (
            "Continuously monitors contract deadlines, compliance review results, SLA "
            "performance, and staffing gaps. Generates prioritized alerts so stakeholders "
            "know what needs attention."
        ),
        "analogy": "Like the program coordinator who sends the Monday morning status email.",
    },
    "chat_agent": {
        "title": "Assistant",
        "role": "Stakeholder inquiry",
        "description": (
            "Answers questions about contracts, compliance findings, deadlines, and system "
            "activity. Grounded in real-time system data so answers are always current."
        ),
        "analogy": (
            "Like the analyst you can ping on Slack to ask 'what's the status on the DOL proposal?'"
        ),
    },
}

SKILL_GROUP_DEFINITIONS = [
    {
        "label": "Document processing",
        "skills": ["parse_document", "parse_pdf", "parse_docx", "parse_txt", "chunk_document"],
        "used_by": "Intake Specialist",
    },
    {
        "label": "Requirements analysis",
        "skills": [
            "lexical_extract",
            "extract_requirements",
            "llm_extract",
            "split_compound",
            "classify_requirements",
            "keyword_classify",
            "llm_classify",
        ],
        "used_by": "Requirements Analyst",
    },
    {
        "label": "Evidence retrieval",
        "skills": ["vector_search", "bm25_search", "rerank", "assemble_context"],
        "used_by": "Evidence Researcher",
    },
    {
        "label": "Compliance reasoning",
        "skills": [
            "assess_compliance",
            "validate_citations",
            "rules_fallback",
            "score_confidence",
            "flag_low_confidence",
        ],
        "used_by": "Compliance Assessor",
    },
    {
        "label": "Comparison and drafting",
        "skills": [
            "match_prior_docs",
            "compute_delta",
            "summarize_changes",
            "generate_outline",
            "write_section",
            "rewrite_section",
            "review_draft",
        ],
        "used_by": "Historical Analyst, Proposal Writer",
    },
    {
        "label": "Quality assurance",
        "skills": [
            "check_acronyms",
            "detect_placeholders",
            "format_check",
            "coverage_check",
            "final_qa_check",
        ],
        "used_by": "Quality Reviewer",
    },
]

app = FastAPI(title="Compliance Operations Workspace")
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "review"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _update_run_status(run_id: str, **kwargs: Any) -> None:
    with _run_lock:
        if run_id not in _run_status:
            _run_status[run_id] = {
                "status": "pending",
                "stage": "",
                "stages_completed": [],
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "error": None,
                "requirements_count": 0,
                "decisions_count": 0,
            }
        _run_status[run_id].update(kwargs)


def _get_run_status(run_id: str) -> Dict[str, Any]:
    with _run_lock:
        status = _run_status.get(run_id)
        if not status:
            return {"status": "not_found"}
        data = dict(status)
        data["stages_completed"] = list(status.get("stages_completed", []))
        return data


def _normalize_stage_key(action: str) -> str:
    if action.startswith("dispatch_"):
        return action
    if action.startswith("request_"):
        return action
    return action.replace(" ", "_").lower()


def _execute_run_in_background(
    *,
    run_id: str,
    title: str,
    workflow_type: str,
    documents: List[Dict[str, Any]],
    output_dir: Path,
) -> None:
    """Execute one review in a background thread and update live status."""

    _update_run_status(
        run_id,
        status="pending",
        stage="Queued",
        stages_completed=[],
        started_at=datetime.now().isoformat(),
        finished_at=None,
        error=None,
        requirements_count=0,
        decisions_count=0,
    )

    def _runner() -> None:
        _update_run_status(run_id, status="running", stage="Initializing agents")
        try:
            seen_actions: List[str] = []

            def stage_cb(payload: Any) -> None:
                if isinstance(payload, dict):
                    action = _normalize_stage_key(str(payload.get("action", "")))
                    if payload.get("status") == "completed" and action and action not in seen_actions:
                        seen_actions.append(action)
                    _update_run_status(
                        run_id,
                        stage=str(payload.get("label") or payload.get("action") or "Working"),
                        stages_completed=list(payload.get("stages_completed") or seen_actions),
                        requirements_count=int(payload.get("requirements_count") or 0),
                        decisions_count=int(payload.get("decisions_count") or 0),
                    )
                    return
                _update_run_status(run_id, stage=str(payload or "Working"))

            _update_run_status(run_id, stage="Starting agent team")

            _execute_review(
                title=title,
                workflow_type=workflow_type,
                documents=documents,
                output_dir=output_dir,
                run_id=run_id,
                stage_callback=stage_cb,
            )

            run_bundle = _load_run_bundle(output_dir, scope=run_id)
            requirements_count = int(run_bundle.get("requirements_count", 0)) if run_bundle else 0
            decisions_count = int(run_bundle.get("decisions_count", 0)) if run_bundle else 0

            _update_run_status(
                run_id,
                status="complete",
                stage="Done - redirecting to results",
                finished_at=datetime.now().isoformat(),
                requirements_count=requirements_count,
                decisions_count=decisions_count,
            )
        except Exception as exc:
            logger.exception("Background run failed for %s", run_id)
            _update_run_status(
                run_id,
                status="error",
                stage="Failed",
                error=str(exc),
                finished_at=datetime.now().isoformat(),
            )

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _format_timestamp(value: str) -> str:
    if not value:
        return "n/a"
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y at %I:%M %p")
    except ValueError:
        return value


def _format_date(value: str) -> str:
    if not value:
        return "n/a"
    try:
        return datetime.fromisoformat(value).strftime("%b %d, %Y")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            return value


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "n/a"
    total_seconds = int(round(seconds))
    minutes, remainder = divmod(total_seconds, 60)
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().title() if value else "Unknown"


def _readable_run_title(run_id: str, title: str) -> str:
    candidate = (title or "").strip()
    if candidate and candidate.lower() != (run_id or "").lower():
        return candidate
    cleaned = re.sub(r"[-_]+", " ", run_id or "").strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.title() if cleaned else "Compliance Review"


def _is_hidden_run(scope: str, run_id: str, title: str) -> bool:
    haystack = " ".join([scope or "", run_id or "", title or ""]).lower()
    return any(token in haystack for token in HIDDEN_RUNS)


def _friendly_agent_name(agent_id: str) -> str:
    return str(agent_id or "").replace("_agent", "").replace("_", " ").strip().title() or "Unknown"


def _summarize_text(text: str, max_chars: int = 240) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def _format_payload(payload: Any, max_chars: Optional[int] = 420) -> str:
    if payload in (None, "", [], {}):
        return "{}"
    try:
        rendered = json.dumps(payload, indent=2)
    except TypeError:
        rendered = str(payload)
    if max_chars is None or len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3].rstrip() + "..."


def _normalize_suggested_edits(value: Any) -> List[str]:
    def _clean_text(text: str) -> str:
        cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        cleaned = re.sub(r"^\s*(?:[-*•]\s*|\d+[.)]\s*)", "", cleaned).strip()
        return cleaned

    def _looks_like_char_stream(items: List[str]) -> bool:
        if len(items) < 6:
            return False
        short = 0
        for item in items:
            token = item.strip()
            if len(token) <= 1:
                short += 1
            elif len(token) == 2 and token.endswith("."):
                short += 1
        return (short / len(items)) >= 0.8

    def _join_char_tokens(tokens: List[str]) -> str:
        joined = "".join(tokens)
        joined = re.sub(r"\s+", " ", joined).strip()
        return joined

    def _normalize_text_block(text: str) -> List[str]:
        cleaned = _clean_text(text)
        if not cleaned:
            return []
        if cleaned.lower() in {"none", "n/a", "na", "null"}:
            return []

        # Handle serialized JSON/list payloads coming through as strings.
        if cleaned[:1] in {"[", "{"} and cleaned[-1:] in {"]", "}"}:
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = None
            if parsed is not None and parsed != cleaned:
                return _normalize_suggested_edits(parsed)

        raw_lines = re.split(r"\n+", cleaned)
        lines: List[str] = []
        for raw_line in raw_lines:
            # Preserve explicit bullet-space rows (e.g. "-  ") as a word separator token.
            spacer_row = bool(re.match(r"^\s*(?:[-*•]|\d+[.)])\s*$", raw_line))
            normalized_line = _clean_text(raw_line)
            if spacer_row and not normalized_line:
                lines.append(" ")
                continue
            if normalized_line and normalized_line.lower() not in {"none", "n/a", "na", "null"}:
                lines.append(normalized_line)

        if _looks_like_char_stream(lines):
            joined = _join_char_tokens(lines)
            return [joined] if joined else []

        if len(lines) == 1:
            parts = [part.strip() for part in re.split(r"\s*;\s+", lines[0]) if part.strip()]
            if len(parts) > 1 and all(len(part) > 3 for part in parts):
                return parts
        return lines

    if isinstance(value, str):
        return _normalize_text_block(value)

    if isinstance(value, dict):
        for key in ("suggested_edits", "suggestion", "suggestions", "edit", "text"):
            if key in value:
                return _normalize_suggested_edits(value.get(key))
        return []

    if isinstance(value, (list, tuple, set)):
        if all(isinstance(item, str) for item in value):
            raw_items = list(value)
            if _looks_like_char_stream(raw_items):
                joined = _join_char_tokens(raw_items)
                if joined and joined.lower() not in {"none", "n/a", "na", "null"}:
                    return [joined]

        flattened: List[str] = []
        for item in value:
            flattened.extend(_normalize_suggested_edits(item))

        if _looks_like_char_stream(flattened):
            joined = _join_char_tokens(flattened)
            flattened = [joined] if joined else []

        deduped: List[str] = []
        seen = set()
        for item in flattened:
            if item and item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped

    return []


def trim_audit_for_embed(audit_log: List[Dict[str, Any]], max_payload_chars: int = 500) -> List[Dict[str, Any]]:
    """Trim large payloads for safe browser embedding."""
    trimmed: List[Dict[str, Any]] = []
    for entry in audit_log:
        entry_copy = dict(entry)
        payload_str = json.dumps(entry_copy.get("payload", {}), default=str)
        if len(payload_str) > max_payload_chars:
            entry_copy["payload"] = {
                "_truncated": True,
                "_preview": payload_str[:max_payload_chars] + "...",
            }
        trimmed.append(entry_copy)
    return trimmed


def _role_label(role: str) -> str:
    labels = {
        "solicitation_or_requirement_source": "Source document",
        "response_or_proposal": "Response document",
        "glossary": "Glossary",
        "prior_proposal": "Prior proposal",
        "prior_contract": "Prior contract",
        "amendment": "Amendment",
        "past_performance": "Past performance",
        "unknown": "Supporting document",
    }
    return labels.get(role, _humanize(role))


def _normalize_agentic_documents(documents: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for index, document in enumerate(documents, start=1):
        if isinstance(document, dict):
            payload = dict(document)
        else:
            payload = {"path": str(document)}
        payload.setdefault("label", payload.get("role") and _role_label(payload["role"]) or f"Document {index}")
        payload.setdefault("role", "unknown")
        normalized.append(payload)
    return normalized


@lru_cache(maxsize=1)
def _agentic_capabilities() -> Dict[str, Any]:
    registry = SkillRegistry()
    for module in [
        parsing,
        chunking,
        extraction,
        classification,
        retrieval,
        reasoning,
        scoring,
        comparison,
        drafting,
        qa,
    ]:
        module.register_skills(registry)

    agent_ids = [
        "orchestrator",
        "intake_agent",
        "extraction_agent",
        "retrieval_agent",
        "compliance_agent",
        "comparison_agent",
        "drafting_agent",
        "qa_agent",
        "notification_agent",
        "chat_agent",
    ]
    skills = registry.list_all()
    return {
        "agent_ids": agent_ids,
        "agent_count": len(agent_ids),
        "skills": skills,
        "skill_count": len(skills),
    }


def _extract_requirement_id(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    direct = payload.get("requirement_id") or payload.get("req_id")
    if direct:
        return str(direct)
    for key in ("requirement", "decision"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_id = nested.get("requirement_id") or nested.get("req_id")
            if nested_id:
                return str(nested_id)
    items = payload.get("items")
    if isinstance(items, list):
        for item in items:
            nested_id = _extract_requirement_id(item)
            if nested_id:
                return nested_id
    return None


def _relative_label(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _tone_for_status(label: str) -> str:
    return {
        "compliant": "good",
        "partial": "warn",
        "not_compliant": "bad",
        "not_addressed": "muted",
    }.get(label, "muted")


def _area_label(segment: str) -> str:
    normalized = re.sub(r"^\d+_", "", segment)
    return _humanize(normalized)


def _document_preview(path_str: str, max_chars: int = 700) -> str:
    path = Path(path_str)
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".json", ".csv"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            parser = DocumentParser()
            parsed = parser.parse(str(path), doc_type="preview")
            text = "\n\n".join(chunk.text for chunk in parsed[:3])
    except Exception as exc:
        return f"Preview unavailable for {path.name}: {exc}"
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return "Document"
    if suffix in {".json", ".csv"}:
        return "Structured data"
    if "log" in path.name.lower():
        return "Log"
    if suffix in {".pdf", ".docx"}:
        return "Uploaded file"
    return suffix[1:].upper() if suffix else "File"


def _safe_relative_path(root: Path, target: Path) -> str:
    return target.resolve().relative_to(root.resolve()).as_posix()


def _managed_preview(path: Path, max_chars: int = 560) -> str:
    if path.suffix.lower() in TEXT_PREVIEW_SUFFIXES or path.suffix.lower() in {".pdf", ".docx"}:
        return _document_preview(str(path), max_chars=max_chars)
    return f"Preview unavailable for {path.name}. This file type is not rendered inline."


def _build_managed_file_entry(root_key: str, root_info: Dict[str, Any], file_path: Path) -> Dict[str, Any]:
    root_path = Path(root_info["path"])
    rel_path = _safe_relative_path(root_path, file_path)
    relative_parts = rel_path.split("/")
    folder_label = _humanize(relative_parts[0]) if len(relative_parts) > 1 else root_info["label"]
    stat = file_path.stat()
    entry = {
        "root_key": root_key,
        "root_label": root_info["label"],
        "root_description": root_info["description"],
        "title": file_path.name,
        "relative_path": rel_path,
        "path": str(file_path),
        "path_label": _relative_label(file_path),
        "folder_label": folder_label,
        "kind": _file_kind(file_path),
        "size_bytes": stat.st_size,
        "size_label": f"{max(1, round(stat.st_size / 1024))} KB" if stat.st_size >= 1024 else f"{stat.st_size} B",
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "modified_label": _format_timestamp(datetime.fromtimestamp(stat.st_mtime).isoformat()),
        "preview": _managed_preview(file_path),
        "view_url": f"/files/view/{root_key}/{rel_path}",
        "download_url": f"/files/download/{root_key}/{rel_path}",
    }
    entry["search_text"] = " ".join(
        [
            entry["root_label"],
            entry["title"],
            entry["relative_path"],
            entry["path_label"],
            entry["kind"],
            entry["folder_label"],
            entry["preview"],
        ]
    ).lower()
    return entry


def _build_file_workspace() -> Dict[str, Any]:
    groups = []
    all_files: List[Dict[str, Any]] = []
    for root_key, root_info in MANAGED_ROOTS.items():
        root_path = Path(root_info["path"])
        files = []
        if root_path.exists():
            for file_path in sorted((path for path in root_path.rglob("*") if path.is_file()), reverse=True):
                files.append(_build_managed_file_entry(root_key, root_info, file_path))
        all_files.extend(files)
        groups.append(
            {
                "key": root_key,
                "label": root_info["label"],
                "description": root_info["description"],
                "count": len(files),
                "files": files[:30],
            }
        )

    all_files.sort(key=lambda item: item["modified_at"], reverse=True)
    return {
        "groups": groups,
        "all_files": all_files,
        "file_count": len(all_files),
        "root_count": len(groups),
        "recent_files": all_files[:12],
    }


def _resolve_managed_path(root_key: str, relative_path: str) -> Path:
    root_info = MANAGED_ROOTS.get(root_key)
    if not root_info:
        raise HTTPException(status_code=404, detail="File root not found.")
    root_path = Path(root_info["path"]).resolve()
    target = (root_path / relative_path).resolve()
    if root_path not in target.parents and target != root_path:
        raise HTTPException(status_code=404, detail="File not found.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return target


def _artifact_candidates(output_dir: Path, run_id: str) -> Dict[str, Path]:
    candidates: Dict[str, Path] = {}

    agentic_files = {
        "compliance_decisions": output_dir / "compliance_decisions.json",
        "requirements": output_dir / "requirements.json",
        "evidence_map": output_dir / "evidence_map.json",
        "audit_log": output_dir / "audit_log.json",
        "agent_trace": output_dir / "agent_trace.log",
        "compliance_report": output_dir / "compliance_report.md",
        "compliance_matrix": output_dir / "compliance_matrix.csv",
        "qa_report": output_dir / "qa_report.json",
        "comparison_summary": output_dir / "comparison_summary.json",
        "retrieval_plans": output_dir / "retrieval_plans.json",
        "workflow_result": output_dir / "workflow_result.json",
        "run_manifest": output_dir / "run_manifest.json",
        "compliance_results": output_dir / "compliance_results.json",
        "document_manifest": output_dir / "document_manifest.json",
        "draft": output_dir / "draft.json",
        "draft_review": output_dir / "draft_review.json",
        "draft_iterations": output_dir / "draft_iterations.json",
    }
    for label, path in agentic_files.items():
        if path.exists():
            candidates[label] = path

    alias_map = {
        "matrix": "compliance_matrix",
        "results_json": "compliance_results",
        "report": "compliance_report",
    }
    for alias, label in alias_map.items():
        if label in candidates:
            candidates[alias] = candidates[label]

    legacy_files = {
        "matrix": output_dir / f"{run_id}_matrix.csv",
        "results_json": output_dir / f"{run_id}_results.json",
        "report": output_dir / f"{run_id}_report.md",
    }
    for label, path in legacy_files.items():
        if label not in candidates and path.exists():
            candidates[label] = path

    eval_files = {
        "evaluation_metrics": output_dir / "evaluation_metrics.json",
        "evaluation_report": output_dir / "evaluation_report.md",
    }
    for label, path in eval_files.items():
        if path.exists():
            candidates[label] = path

    return candidates


def _collect_artifacts(output_dir: Path, run_id: str) -> Dict[str, str]:
    artifacts = {}
    for label, path in _artifact_candidates(output_dir, run_id).items():
        if path.exists():
            artifacts[label] = str(path)
    return artifacts


def _meta_path(output_dir: Path) -> Path:
    return output_dir / "dashboard_meta.json"


def _log_paths(run_id: str) -> tuple[Path, Path]:
    return (
        config.LOGS_DIR / f"{run_id}_logs.json",
        config.LOGS_DIR / f"{run_id}_summary.json",
    )


def _read_document_register_rows() -> List[Dict[str, str]]:
    if not DOCUMENT_REGISTER_PATH.exists():
        return []
    with DOCUMENT_REGISTER_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _document_index() -> Dict[str, Any]:
    rows = _read_document_register_rows()
    owners = sorted({row.get("owner", "unknown") for row in rows})
    types = sorted({row.get("document_type", "unknown") for row in rows})
    area_counts: Dict[str, int] = {}
    for row in rows:
        rel_path = row.get("path", "")
        segment = rel_path.split("/", 1)[0] if rel_path else "misc"
        area = _area_label(segment)
        area_counts[area] = area_counts.get(area, 0) + 1
    area_list = [{"name": key, "count": area_counts[key]} for key in sorted(area_counts)]
    return {
        "rows": rows,
        "document_count": len(rows),
        "owner_count": len(owners),
        "type_count": len(types),
        "areas": area_list,
    }


def _build_document_library() -> Dict[str, Any]:
    rows = _read_document_register_rows()
    documents = []
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        relative_path = row.get("path", "")
        absolute_path = COMPANY_SYSTEM_DIR / relative_path
        area_segment = relative_path.split("/", 1)[0] if relative_path else "misc"
        area = _area_label(area_segment)
        doc = {
            "doc_id": row.get("doc_id", ""),
            "title": Path(relative_path).stem.replace("_", " ").title(),
            "date": row.get("date", ""),
            "date_label": _format_date(row.get("date", "")),
            "document_type": row.get("document_type", "unknown"),
            "document_type_label": _humanize(row.get("document_type", "unknown")),
            "owner": row.get("owner", "unknown"),
            "owner_label": _humanize(row.get("owner", "unknown")),
            "summary": row.get("summary", ""),
            "path": str(absolute_path),
            "path_label": _relative_label(absolute_path),
            "area": area,
            "preview": _document_preview(str(absolute_path), max_chars=520),
        }
        doc["search_text"] = " ".join(
            [
                doc["doc_id"],
                doc["title"],
                doc["date"],
                doc["document_type"],
                doc["owner"],
                doc["summary"],
                doc["path_label"],
                doc["preview"],
                doc["area"],
            ]
        ).lower()
        documents.append(doc)
        grouped.setdefault(area, []).append(doc)

    area_groups = []
    for area_name in sorted(grouped):
        docs = sorted(grouped[area_name], key=lambda item: item["date"], reverse=True)
        area_groups.append({"name": area_name, "count": len(docs), "documents": docs})

    index = _document_index()
    return {
        "documents": documents,
        "area_groups": area_groups,
        "document_count": index["document_count"],
        "owner_count": index["owner_count"],
        "type_count": index["type_count"],
        "areas": index["areas"],
    }


def _build_document_panels(meta: Dict[str, Any]) -> List[Dict[str, str]]:
    panels: List[Dict[str, str]] = []
    if meta.get("documents"):
        for index, document in enumerate(_normalize_agentic_documents(meta.get("documents", [])), start=1):
            path = document.get("path")
            if not path:
                continue
            resolved = Path(path)
            panels.append(
                {
                    "label": document.get("label") or _role_label(document.get("role", "unknown")),
                    "name": resolved.name,
                    "path": str(resolved),
                    "path_label": _relative_label(resolved),
                    "preview": _document_preview(path, max_chars=520),
                }
            )
        if panels:
            return panels

    doc_map = [
        ("source_document", "Source document"),
        ("response_document", "Response document"),
        ("glossary_document", "Glossary"),
    ]
    for field, label in doc_map:
        path = meta.get(field)
        if path:
            resolved = Path(path)
            panels.append(
                {
                    "label": label,
                    "name": resolved.name,
                    "path": str(resolved),
                    "path_label": _relative_label(resolved),
                    "preview": _document_preview(path, max_chars=520),
                }
            )
    for idx, path in enumerate(meta.get("context_documents", []), start=1):
        resolved = Path(path)
        panels.append(
            {
                "label": f"Context {idx}",
                "name": resolved.name,
                "path": str(resolved),
                "path_label": _relative_label(resolved),
                "preview": _document_preview(path, max_chars=520),
            }
        )
    return panels


def _build_summary_cards(results_payload: Dict[str, Any], metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    requirements = results_payload.get("requirements", [])
    decisions = [item.get("decision", {}) for item in requirements]
    confidence_values = [decision.get("confidence", 0.0) for decision in decisions]
    summary = results_payload.get("metadata", {}).get("compliance_summary", {})
    review_items = sum(1 for decision in decisions if decision.get("confidence", 0.0) < config.CONFIDENCE_HIGH)
    return {
        "total_requirements": results_payload.get("metadata", {}).get("total_requirements", 0),
        "compliant": summary.get("compliant", 0),
        "partial": summary.get("partial", 0),
        "not_compliant": summary.get("not_compliant", 0),
        "not_addressed": summary.get("not_addressed", 0),
        "avg_confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
        "review_items": review_items,
        "accuracy": metrics.get("accuracy") if metrics else None,
        "cohen_kappa": metrics.get("cohen_kappa") if metrics else None,
        "ece": metrics.get("calibration", {}).get("expected_calibration_error") if metrics else None,
    }


def _attention_reason(status: str, is_review_queue: bool, confidence: float) -> str:
    if is_review_queue:
        return "Flagged for human review"
    if status == "not_compliant":
        return "Potential contradiction"
    if status == "not_addressed":
        return "No clear supporting evidence"
    if status == "partial":
        return "Requirement only partially covered"
    if confidence < config.CONFIDENCE_HIGH:
        return "Lower-confidence decision"
    return "Evidence-backed decision"


def _build_requirement_rows(
    results_payload: Dict[str, Any],
    review_queue: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    review_queue_ids = set(review_queue or [])
    rows = []
    for item in results_payload.get("requirements", []):
        requirement = item.get("requirement", {})
        decision = item.get("decision", {})
        evidence = item.get("evidence", [])
        requirement_id = requirement.get("req_id", "")
        status = decision.get("label", "not_addressed")
        confidence = round(float(decision.get("confidence", 0.0)), 2)
        is_review_queue = requirement_id in review_queue_ids
        top_evidence = evidence[0] if evidence else None
        search_text = " ".join(
            [
                requirement_id,
                requirement.get("requirement_text", ""),
                requirement.get("source_citation", ""),
                requirement.get("category", "") or "",
                decision.get("explanation", ""),
                " ".join(decision.get("suggested_edits", []) or []),
                " ".join(chunk.get("evidence_text", "") for chunk in evidence),
                " ".join(chunk.get("evidence_citation", "") for chunk in evidence),
            ]
        ).lower()
        rows.append(
            {
                "id": requirement_id,
                "text": requirement.get("requirement_text", ""),
                "source": requirement.get("source_citation", "Not specified"),
                "conditions": requirement.get("conditions"),
                "category": requirement.get("category") or "uncategorized",
                "extraction_method": None,
                "extraction_confidence": None,
                "strategy_reason": "",
                "status": status,
                "status_tone": _tone_for_status(status),
                "confidence": confidence,
                "explanation": decision.get("explanation", ""),
                "short_explanation": _summarize_text(decision.get("explanation", "")),
                "suggested_edits": _normalize_suggested_edits(decision.get("suggested_edits", [])),
                "citation_coverage": None,
                "citation_penalty": None,
                "citation_validation_status": None,
                "invalid_citation_ids": [],
                "supporting_citations": [],
                "review_required": False,
                "retrieval_strategy": None,
                "retrieval_reason": "",
                "retrieval_weights": {},
                "execution_mode": decision.get("execution_mode"),
                "evidence": evidence,
                "evidence_count": len(evidence),
                "top_evidence": top_evidence,
                "top_score": round(float(top_evidence.get("retrieval_score", 0.0)), 2) if top_evidence else None,
                "is_review_queue": is_review_queue,
                "needs_attention": is_review_queue or status in {"partial", "not_compliant", "not_addressed"},
                "attention_reason": _attention_reason(status, is_review_queue, confidence),
                "search_text": search_text,
            }
        )
    return rows


def _build_agentic_requirement_rows(
    decisions_path: Path,
    requirements_path: Path,
    evidence_map_path: Optional[Path] = None,
    review_queue: Optional[List[str]] = None,
    retrieval_plans_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Build requirement rows using workflow artifacts."""
    decisions = _read_json(decisions_path) if decisions_path.exists() else []
    requirements = _read_json(requirements_path) if requirements_path.exists() else []
    raw_evidence_map = _read_json(evidence_map_path) if evidence_map_path and evidence_map_path.exists() else {}
    retrieval_plans = _read_json(retrieval_plans_path) if retrieval_plans_path and retrieval_plans_path.exists() else {}
    review_queue_ids = set(review_queue or [])

    req_by_id = {}
    for requirement in requirements:
        requirement_id = requirement.get("req_id", requirement.get("id", ""))
        if requirement_id:
            req_by_id[requirement_id] = requirement

    rows = []
    for decision in decisions:
        req_id = decision.get("requirement_id", "")
        requirement = req_by_id.get(req_id, {})
        status = decision.get("label", "not_addressed")
        confidence = round(float(decision.get("confidence", 0.0)), 2)
        is_review_queue = req_id in review_queue_ids or bool(decision.get("review_required"))
        raw_evidence = raw_evidence_map.get(req_id, [])
        if isinstance(raw_evidence, dict):
            raw_evidence = raw_evidence.get("results", [])

        evidence = []
        for chunk in raw_evidence or []:
            evidence.append(
                {
                    "evidence_chunk_id": chunk.get("chunk_id", chunk.get("evidence_chunk_id", "")),
                    "evidence_text": chunk.get("text", chunk.get("evidence_text", "")),
                    "evidence_citation": chunk.get(
                        "section_title",
                        chunk.get("evidence_citation", chunk.get("page_range", chunk.get("chunk_id", "Unknown citation"))),
                    ),
                    "retrieval_score": chunk.get("hybrid_score", chunk.get("retrieval_score", 0.0)),
                    **chunk,
                }
            )

        retrieval_plan = retrieval_plans.get(req_id, {}) if isinstance(retrieval_plans, dict) else {}
        row = {
            "id": req_id,
            "text": requirement.get("requirement_text", requirement.get("text", "")),
            "source": requirement.get("source_citation", "Not specified"),
            "conditions": requirement.get("conditions"),
            "category": requirement.get("category", "uncategorized") or "uncategorized",
            "extraction_method": requirement.get("extraction_method", "unknown"),
            "extraction_confidence": round(float(requirement.get("extraction_confidence", 0.0)), 2)
            if requirement.get("extraction_confidence") is not None
            else None,
            "strategy_reason": requirement.get("strategy_reason", ""),
            "status": status,
            "status_tone": _tone_for_status(status),
            "confidence": confidence,
            "explanation": decision.get("explanation", ""),
            "short_explanation": _summarize_text(decision.get("explanation", "")),
            "suggested_edits": _normalize_suggested_edits(decision.get("suggested_edits", [])),
            "citation_coverage": decision.get("citation_coverage"),
            "citation_penalty": decision.get("citation_penalty"),
            "citation_validation_status": decision.get("citation_validation_status", "unknown"),
            "invalid_citation_ids": decision.get("invalid_citation_ids", []) or [],
            "supporting_citations": decision.get("supporting_citations", []) or [],
            "review_required": bool(decision.get("review_required")),
            "retrieval_strategy": retrieval_plan.get("strategy"),
            "retrieval_reason": retrieval_plan.get("reason"),
            "retrieval_weights": retrieval_plan.get("weights", {}),
            "execution_mode": decision.get("execution_mode"),
            "evidence": evidence,
            "evidence_count": len(evidence),
            "is_review_queue": is_review_queue,
            "needs_attention": is_review_queue or status in {"partial", "not_compliant", "not_addressed"},
            "attention_reason": _attention_reason(status, is_review_queue, confidence),
        }
        row["search_text"] = " ".join(
            [
                req_id,
                row["text"],
                row["source"],
                row["category"],
                row["explanation"],
                row["extraction_method"],
                row["citation_validation_status"],
                row.get("retrieval_strategy") or "",
                " ".join(row["supporting_citations"]),
                " ".join(item.get("evidence_text", "") for item in evidence),
            ]
        ).lower()
        rows.append(row)

    return rows


def _activity_title(action: str, input_data: Dict[str, Any]) -> str:
    requirement_id = input_data.get("requirement_id")
    if action == "parse_documents":
        return "Prepared source files for review"
    if action == "extract_requirements":
        return "Extracted atomic requirements"
    if action == "classify_requirements":
        return "Classified requirement categories"
    if action == "build_index":
        return "Built searchable evidence index"
    if action == "retrieve_evidence" and requirement_id:
        return f"Retrieved evidence for {requirement_id}"
    if action == "reason_compliance" and requirement_id:
        return f"Decided compliance for {requirement_id}"
    if action == "score_confidence" and requirement_id:
        return f"Scored confidence for {requirement_id}"
    return _humanize(action)


def _activity_comment(event: Dict[str, Any]) -> str:
    action = event.get("action", "")
    input_data = event.get("input_data", {}) or {}
    output_data = event.get("output_data", {}) or {}
    if action == "parse_documents":
        policy_chunks = output_data.get("policy_chunks", 0)
        response_chunks = output_data.get("response_chunks", 0)
        context_chunks = output_data.get("context_chunks", 0)
        total_chunks = policy_chunks + response_chunks + context_chunks
        return f"The ingestion agent organized the submitted files into {total_chunks} chunks so the rest of the workflow could search and reason over them."
    if action == "extract_requirements":
        count = output_data.get("num_requirements", 0)
        sections = input_data.get("num_sections", 0)
        return f"The requirement extractor pulled out {count} atomic requirements from {sections} source sections."
    if action == "classify_requirements":
        distribution = output_data.get("category_distribution", {})
        if distribution:
            top_category = next(iter(distribution))
            return f"The classifier organized the extracted requirements by category, with {distribution[top_category]} items landing in {top_category.replace('_', ' ')}."
        return "The classifier tagged the extracted requirements so downstream agents could retrieve more targeted evidence."
    if action == "build_index":
        return f"The retrieval agent built a searchable evidence index across {input_data.get('num_chunks', 0)} response chunks."
    if action == "retrieve_evidence":
        requirement_id = input_data.get("requirement_id", "this requirement")
        num_evidence = output_data.get("num_evidence", 0)
        top_score = output_data.get("top_score")
        if top_score is not None:
            return f"The retrieval agent gathered {num_evidence} supporting chunks for {requirement_id} and ranked the strongest match at {top_score:.2f}."
        return f"The retrieval agent gathered supporting material for {requirement_id}."
    if action == "reason_compliance":
        requirement_id = input_data.get("requirement_id", "this requirement")
        label = str(output_data.get("label", "undetermined")).replace("_", " ")
        confidence = output_data.get("confidence")
        if confidence is not None:
            return f"The compliance reasoner marked {requirement_id} as {label} with {confidence:.2f} confidence."
        return f"The compliance reasoner produced a decision for {requirement_id}."
    if action == "score_confidence":
        requirement_id = input_data.get("requirement_id", "this requirement")
        label = str(output_data.get("status", "review")).replace("_", " ")
        return f"The confidence scorer routed {requirement_id} into the {label} lane based on evidence strength and decision certainty."
    return "The agent completed a workflow step and recorded its inputs and outputs for traceability."


def _build_timeline(log_payload: List[Dict[str, Any]], *, run_scope: str, run_title: str) -> List[Dict[str, Any]]:
    timeline = []
    for index, event in enumerate(log_payload):
        input_data = event.get("input_data", {}) or {}
        output_data = event.get("output_data", {}) or {}
        requirement_id = input_data.get("requirement_id") or output_data.get("requirement_id")
        item = {
            "index": index,
            "agent": event.get("agent_name", "agent"),
            "agent_label": _humanize(event.get("agent_name", "agent")),
            "action": event.get("action", "step"),
            "action_label": _humanize(event.get("action", "step")),
            "title": _activity_title(event.get("action", "step"), input_data),
            "comment": _activity_comment(event),
            "timestamp": event.get("timestamp", ""),
            "timestamp_label": _format_timestamp(event.get("timestamp", "")),
            "input": input_data,
            "output": output_data,
            "input_preview": _format_payload(input_data),
            "output_preview": _format_payload(output_data),
            "input_json": _format_payload(input_data, max_chars=None),
            "output_json": _format_payload(output_data, max_chars=None),
            "error": event.get("error"),
            "duration": event.get("duration_seconds"),
            "duration_label": _format_duration(event.get("duration_seconds")),
            "requirement_id": requirement_id,
            "run_scope": run_scope,
            "run_title": run_title,
            "detail_url": f"/activity/{run_scope}/{index}",
        }
        item["search_text"] = " ".join(
            [
                item["agent"],
                item["action"],
                item["title"],
                item["comment"],
                item["run_title"],
                requirement_id or "",
                item["input_preview"],
                item["output_preview"],
            ]
        ).lower()
        timeline.append(item)
    return timeline


def _agentic_event_display(
    msg_type: str,
    sender: str,
    recipient: str,
    payload_keys: List[str],
) -> tuple[str, str, str]:
    """Return a readable title, comment, and visual class for an MCP event."""
    if msg_type == "spawn":
        return (
            f"{_humanize(recipient)} joined the workflow",
            f"The MCP bus registered {_humanize(recipient)} as an active agent and exposed its tools to the rest of the system.",
            "event-spawn",
        )
    if msg_type == "terminate":
        return (
            f"{_humanize(recipient)} completed and exited",
            f"{_humanize(recipient)} finished its assigned work and was unregistered from the bus.",
            "event-terminate",
        )
    if msg_type == "goal":
        action_hint = " with a specific action directive" if "action" in payload_keys else ""
        return (
            f"{_humanize(sender)} delegated a goal to {_humanize(recipient)}",
            f"The orchestrator sent a goal message{action_hint} so {_humanize(recipient)} could choose a strategy and execute autonomously.",
            "event-goal",
        )
    if msg_type == "result":
        result_keys = ", ".join(payload_keys) if payload_keys else "structured outputs"
        return (
            f"{_humanize(sender)} delivered results to {_humanize(recipient)}",
            f"{_humanize(sender)} completed its goal and returned {result_keys}.",
            "event-result",
        )
    if msg_type == "tool_call":
        skill_name = recipient.replace("skill:", "") if recipient.startswith("skill:") else recipient
        return (
            f"{_humanize(sender)} invoked skill: {skill_name}",
            f"The agent called the shared {skill_name} skill to perform a bounded operation inside the workflow.",
            "event-tool-call",
        )
    if msg_type == "tool_result":
        skill_name = sender.replace("skill:", "") if sender.startswith("skill:") else sender
        return (
            f"Skill {skill_name} returned results to {_humanize(recipient)}",
            f"The {skill_name} skill finished and returned its output to the requesting agent.",
            "event-tool-result",
        )
    if msg_type == "status":
        return (
            f"{_humanize(sender)} reported status",
            f"{_humanize(sender)} broadcast a progress update so the workflow remained observable.",
            "event-status",
        )
    if msg_type == "error":
        return (
            f"{_humanize(sender)} reported an error",
            f"The workflow recorded an exception or missing dependency while {_humanize(sender)} was handling a message.",
            "event-error",
        )
    return (
        f"{_humanize(msg_type)} from {_humanize(sender)} to {_humanize(recipient)}",
        "An MCP message was exchanged between agents.",
        "event-default",
    )


def _build_agentic_timeline(
    audit_log: List[Dict[str, Any]],
    *,
    run_scope: str,
    run_title: str,
) -> List[Dict[str, Any]]:
    """Build a dashboard activity timeline from MCP audit log messages."""
    timeline = []
    for index, entry in enumerate(audit_log):
        msg_type = entry.get("type", "unknown")
        sender = entry.get("sender", "unknown")
        recipient = entry.get("recipient", "unknown")
        payload = entry.get("payload", {}) or {}
        payload_keys = entry.get("payload_keys", []) or []
        timestamp = entry.get("timestamp", "")
        correlation_id = entry.get("correlation_id")
        requirement_id = _extract_requirement_id(payload)
        title, comment, icon_class = _agentic_event_display(msg_type, sender, recipient, payload_keys)

        input_payload = payload if msg_type in {"goal", "tool_call"} else {}
        output_payload = payload if msg_type not in {"goal", "tool_call"} else {}
        item = {
            "index": index,
            "msg_type": msg_type,
            "sender": sender,
            "recipient": recipient,
            "agent": sender,
            "agent_label": _humanize(sender),
            "recipient_label": _humanize(recipient),
            "action": msg_type,
            "action_label": _humanize(msg_type),
            "title": title,
            "comment": comment,
            "icon_class": icon_class,
            "timestamp": timestamp,
            "timestamp_label": _format_timestamp(timestamp),
            "payload": payload,
            "payload_keys": payload_keys,
            "payload_preview": _format_payload(payload),
            "payload_json": _format_payload(payload, max_chars=None),
            "input": input_payload,
            "output": output_payload,
            "input_preview": _format_payload(input_payload),
            "output_preview": _format_payload(output_payload),
            "input_json": _format_payload(input_payload, max_chars=None),
            "output_json": _format_payload(output_payload, max_chars=None),
            "correlation_id": correlation_id,
            "duration": None,
            "duration_label": "n/a",
            "requirement_id": requirement_id,
            "error": payload.get("error") if isinstance(payload, dict) else None,
            "run_scope": run_scope,
            "run_title": run_title,
            "detail_url": f"/activity/{run_scope}/{index}",
        }
        item["search_text"] = " ".join(
            [
                sender,
                recipient,
                msg_type,
                title,
                comment,
                run_title,
                requirement_id or "",
                " ".join(payload_keys),
                item["payload_preview"],
            ]
        ).lower()
        timeline.append(item)
    return timeline


def _build_agentic_log_summary(audit_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    timestamps = [entry.get("timestamp") for entry in audit_log if entry.get("timestamp")]
    duration_seconds = None
    if len(timestamps) >= 2:
        try:
            started = datetime.fromisoformat(timestamps[0])
            ended = datetime.fromisoformat(timestamps[-1])
            duration_seconds = max((ended - started).total_seconds(), 0.0)
        except ValueError:
            duration_seconds = None

    agents = sorted(
        {
            entry.get("sender")
            for entry in audit_log
            if entry.get("type") not in {"spawn", "terminate"}
            and entry.get("sender")
            and entry.get("sender") not in {"bus", "broadcast"}
            and not str(entry.get("sender")).startswith("skill:")
        }
    )
    return {
        "agents_executed": agents,
        "duration_seconds": duration_seconds,
        "message_count": len(audit_log),
    }


def _build_focus_items(requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priority = {
        "not_compliant": 0,
        "not_addressed": 1,
        "partial": 2,
        "compliant": 3,
    }
    items = [item for item in requirements if item.get("needs_attention")]
    items.sort(
        key=lambda item: (
            0 if item.get("is_review_queue") else 1,
            priority.get(item.get("status", "compliant"), 4),
            item.get("confidence", 1.0),
        )
    )
    return items[:6]


def _build_run_snapshot(
    *,
    meta: Dict[str, Any],
    summary_cards: Dict[str, Any],
    requirements: List[Dict[str, Any]],
    log_summary: Dict[str, Any],
    documents: List[Dict[str, str]],
    timeline: List[Dict[str, Any]],
) -> Dict[str, Any]:
    total_requirements = summary_cards.get("total_requirements", 0) or 0
    compliant = summary_cards.get("compliant", 0) or 0
    attention_count = sum(1 for item in requirements if item.get("needs_attention"))
    review_queue_count = sum(1 for item in requirements if item.get("is_review_queue"))
    return {
        "coverage_rate": round((compliant / total_requirements) * 100) if total_requirements else 0,
        "attention_count": attention_count,
        "review_queue_count": review_queue_count,
        "document_count": len(documents),
        "runtime": _format_duration(log_summary.get("duration_seconds")),
        "created_label": _format_timestamp(meta.get("created_at", "")),
        "agent_labels": [_humanize(agent) for agent in log_summary.get("agents_executed", [])],
        "activity_count": len(timeline),
    }


@lru_cache(maxsize=1)
def _scenario_catalog() -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    scenarios_root = BASE_DIR / "examples" / "scenarios"
    for scenario_file in sorted(scenarios_root.glob("*/scenario.json")):
        try:
            payload = _read_json(scenario_file)
        except Exception:
            continue
        scenario_dir = scenario_file.parent
        output_subdir = payload.get("output_subdir") or scenario_dir.name
        docs = []
        for doc in payload.get("documents", []):
            rel = doc.get("path")
            if not rel:
                continue
            abs_path = (scenario_dir / rel).resolve()
            docs.append(
                {
                    "path": str(abs_path),
                    "role": doc.get("role", "unknown"),
                    "label": doc.get("label") or _role_label(doc.get("role", "unknown")),
                }
            )
        catalog[output_subdir] = {
            "name": payload.get("name") or output_subdir.replace("_", " ").title(),
            "mode": payload.get("mode", "agentic"),
            "goal": payload.get("goal"),
            "documents": docs,
            "scenario_dir": str(scenario_dir.resolve()),
            "ground_truth_path": str((scenario_dir / payload["ground_truth_path"]).resolve())
            if payload.get("ground_truth_path")
            else None,
        }
    return catalog


def _default_demo_scope() -> str:
    scenario = load_scenario(DEFAULT_SCENARIO_DIR)
    return scenario.effective_output_subdir


def _run_directories() -> List[Dict[str, Any]]:
    runs: List[Dict[str, Any]] = []
    demo_root = config.DEMO_CASES_DIR
    if demo_root.exists():
        for directory in demo_root.iterdir():
            if directory.is_dir() and directory.name != "_archived":
                runs.append(
                    {
                        "scope": directory.name,
                        "path": directory,
                        "source": "demo_cases",
                    }
                )
    if CUSTOM_RUNS_DIR.exists():
        for directory in CUSTOM_RUNS_DIR.iterdir():
            if directory.is_dir():
                runs.append(
                    {
                        "scope": directory.name,
                        "path": directory,
                        "source": "dashboard_runs",
                    }
                )
    return runs


def _is_archivable_run_dir(path: Path) -> bool:
    resolved = path.resolve()
    demo_root = config.DEMO_CASES_DIR.resolve()
    if resolved.name == "_archived":
        return False
    return resolved.parent == demo_root


def _resolve_scope_to_dir(scope: str) -> Optional[Path]:
    if scope == "demo":
        default_scope = _default_demo_scope()
        candidate = config.DEMO_CASES_DIR / default_scope
        return candidate if candidate.exists() else None
    for entry in _run_directories():
        if entry["scope"] == scope:
            return Path(entry["path"])
    return None


def _load_document_manifest(artifacts: Dict[str, str]) -> Dict[str, Any]:
    path_str = artifacts.get("document_manifest")
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.exists():
        return {}
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else {}


def _normalize_documents_for_meta(
    *,
    meta: Dict[str, Any],
    artifacts: Dict[str, str],
    run_id: str,
) -> List[Dict[str, Any]]:
    if meta.get("documents"):
        return _normalize_agentic_documents(meta.get("documents", []))

    docs: List[Dict[str, Any]] = []
    document_manifest = _load_document_manifest(artifacts)
    if document_manifest:
        primary_source = document_manifest.get("primary_source")
        if primary_source:
            docs.append(
                {
                    "path": primary_source,
                    "role": "solicitation_or_requirement_source",
                    "label": _role_label("solicitation_or_requirement_source"),
                }
            )
        primary_response = document_manifest.get("primary_response")
        if primary_response:
            docs.append(
                {
                    "path": primary_response,
                    "role": "response_or_proposal",
                    "label": _role_label("response_or_proposal"),
                }
            )
        glossary = document_manifest.get("glossary")
        if glossary:
            docs.append({"path": glossary, "role": "glossary", "label": _role_label("glossary")})
        for path in document_manifest.get("prior_context", []):
            docs.append({"path": path, "role": "prior_contract", "label": _role_label("prior_contract")})
        for path in document_manifest.get("unknown", []):
            docs.append({"path": path, "role": "unknown", "label": _role_label("unknown")})

    if not docs:
        for key, role in [
            ("source_document", "solicitation_or_requirement_source"),
            ("response_document", "response_or_proposal"),
            ("glossary_document", "glossary"),
        ]:
            path = meta.get(key)
            if path:
                docs.append({"path": path, "role": role, "label": _role_label(role)})
        for path in meta.get("context_documents", []):
            docs.append({"path": path, "role": "prior_contract", "label": _role_label("prior_contract")})

    if not docs:
        scenario_entry = _scenario_catalog().get(run_id)
        if scenario_entry:
            docs = list(scenario_entry.get("documents", []))

    return _normalize_agentic_documents(docs)


def _planning_trace_from_artifacts(
    artifacts: Dict[str, str],
    audit_log: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    workflow_result_path = artifacts.get("workflow_result")
    if workflow_result_path:
        workflow_payload = _read_json(Path(workflow_result_path))
        trace = workflow_payload.get("planning_trace", [])
        if isinstance(trace, list) and trace:
            return trace

    planning_trace = []
    for entry in audit_log or []:
        payload = entry.get("payload", {})
        if (
            entry.get("type") == "status"
            and isinstance(payload, dict)
            and payload.get("event") == "planning_decision"
        ):
            planning_trace.append(
                {
                    "step": payload.get("step"),
                    "action": payload.get("action"),
                    "reasoning": payload.get("reasoning"),
                    "target_requirements": payload.get("target_requirements", []),
                    "planner_mode": payload.get("planner_mode", "llm"),
                    "confidence_after": payload.get("confidence_after", {}),
                }
            )
    return planning_trace


def _step_label(action: str) -> str:
    mapping = {
        "dispatch_intake": "Intake",
        "dispatch_extraction": "Extraction",
        "dispatch_retrieval": "Retrieval",
        "dispatch_compliance": "Compliance",
        "request_reanalysis": "Reanalysis",
        "dispatch_qa": "QA",
        "finalize": "Finalize",
    }
    return mapping.get(action or "", _humanize(action or "Step"))


def _step_tone(action: str) -> str:
    if action in {"dispatch_intake", "dispatch_extraction", "dispatch_retrieval", "dispatch_compliance"}:
        return "dispatch"
    if action == "request_reanalysis":
        return "reanalysis"
    if action == "dispatch_qa":
        return "qa"
    if action == "finalize":
        return "finalize"
    return "dispatch"


def _confidence_summary_from_rows(requirements: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    values = [float(item.get("confidence", 0.0)) for item in requirements if item.get("confidence") is not None]
    if not values:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(values), "max": max(values), "mean": mean(values)}


def _build_summary_cards_from_rows(requirements: List[Dict[str, Any]], metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {
        "compliant": 0,
        "partial": 0,
        "not_compliant": 0,
        "not_addressed": 0,
    }
    review_items = 0
    confidence_values = []
    for row in requirements:
        label = row.get("status", "not_addressed")
        if label in counts:
            counts[label] += 1
        confidence = float(row.get("confidence", 0.0))
        confidence_values.append(confidence)
        if confidence < config.CONFIDENCE_HIGH:
            review_items += 1

    return {
        "total_requirements": len(requirements),
        "compliant": counts["compliant"],
        "partial": counts["partial"],
        "not_compliant": counts["not_compliant"],
        "not_addressed": counts["not_addressed"],
        "avg_confidence": round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
        "review_items": review_items,
        "accuracy": metrics.get("accuracy") if metrics else None,
        "cohen_kappa": metrics.get("cohen_kappa") if metrics else None,
        "ece": metrics.get("calibration", {}).get("expected_calibration_error") if metrics else None,
    }


def _artifact_groups(artifacts: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
    groups = {
        "analysis_outputs": [
            "compliance_decisions",
            "compliance_matrix",
            "compliance_report",
            "compliance_results",
        ],
        "evidence": [
            "evidence_map",
            "requirements",
            "retrieval_plans",
        ],
        "system_traces": [
            "audit_log",
            "workflow_result",
            "qa_report",
            "run_manifest",
            "agent_trace",
            "document_manifest",
            "comparison_summary",
        ],
        "evaluation": [
            "evaluation_metrics",
            "evaluation_report",
        ],
    }
    label_map = {
        "analysis_outputs": "Analysis outputs",
        "evidence": "Evidence and requirements",
        "system_traces": "System traces",
        "evaluation": "Evaluation",
    }
    fallback_labels = {
        "analysis_outputs": "Analysis output",
        "evidence": "Evidence artifact",
        "system_traces": "System trace",
        "evaluation": "Evaluation artifact",
    }

    output: Dict[str, List[Dict[str, Any]]] = {key: [] for key in groups}
    for group_key, names in groups.items():
        for artifact_name in names:
            path_str = artifacts.get(artifact_name)
            if not path_str:
                continue
            path = Path(path_str)
            preview = ""
            if path.suffix.lower() in TEXT_PREVIEW_SUFFIXES:
                try:
                    if path.suffix.lower() == ".json":
                        preview = json.dumps(_read_json(path), indent=2)[:4000]
                    else:
                        preview = path.read_text(encoding="utf-8", errors="ignore")[:4000]
                except Exception:
                    preview = "Preview unavailable."
            display_label = (
                ARTIFACT_LABELS.get(path.name)
                or ARTIFACT_LABELS.get(f"{artifact_name}{path.suffix}")
                or f"{fallback_labels[group_key]}: {path.name}"
            )
            output[group_key].append(
                {
                    "name": artifact_name,
                    "label": display_label,
                    "filename": path.name,
                    "preview": preview,
                }
            )
    return {
        "groups": [
            {
                "key": key,
                "label": label_map[key],
                "files": output[key],
            }
            for key in ["analysis_outputs", "evidence", "system_traces", "evaluation"]
            if output[key]
        ]
    }


def _infer_meta(output_dir: Path, scope: str) -> Dict[str, Any]:
    meta = {}
    meta_file = _meta_path(output_dir)
    if meta_file.exists():
        loaded = _read_json(meta_file)
        if isinstance(loaded, dict):
            meta = loaded

    run_id = str(meta.get("run_id") or output_dir.name)
    artifacts = _collect_artifacts(output_dir, run_id)
    scenario_entry = _scenario_catalog().get(run_id)
    created_at = meta.get("created_at")
    if not created_at:
        created_at = datetime.fromtimestamp(output_dir.stat().st_mtime).isoformat()

    workflow_result = {}
    if artifacts.get("workflow_result"):
        workflow_result = _read_json(Path(artifacts["workflow_result"]))

    run_manifest = {}
    if artifacts.get("run_manifest"):
        run_manifest = _read_json(Path(artifacts["run_manifest"]))

    inferred = {
        "run_id": run_id,
        "title": meta.get("title")
        or (scenario_entry.get("name") if scenario_entry else run_id.replace("_", " ").title()),
        "mode": meta.get("mode")
        or ("mcp" if artifacts.get("audit_log") else "mcp"),
        "created_at": created_at,
        "workflow": meta.get("workflow")
        or workflow_result.get("workflow")
        or run_manifest.get("workflow")
        or "compliance_review",
        "review_queue": meta.get("review_queue")
        or run_manifest.get("review_queue")
        or workflow_result.get("outputs", {}).get("review_queue", []),
        "ground_truth_path": meta.get("ground_truth_path") or (scenario_entry.get("ground_truth_path") if scenario_entry else None),
    }
    inferred.update(meta)
    inferred["scope"] = scope
    inferred["documents"] = _normalize_documents_for_meta(meta=inferred, artifacts=artifacts, run_id=run_id)
    return inferred


def _default_demo_bundle() -> Optional[Dict[str, Any]]:
    scope = _default_demo_scope()
    bundle = _load_run_bundle(config.DEMO_CASES_DIR / scope, scope=scope)
    return bundle


def _load_run_bundle(output_dir: Path, *, scope: str) -> Optional[Dict[str, Any]]:
    if not output_dir.exists() or not output_dir.is_dir():
        return None

    meta = _infer_meta(output_dir, scope)
    run_id = str(meta["run_id"])
    artifacts = _collect_artifacts(output_dir, run_id)

    metrics_payload = _read_json(Path(artifacts["evaluation_metrics"])) if "evaluation_metrics" in artifacts else None
    title = meta.get("title", run_id.replace("_", " ").title())
    documents = _build_document_panels(meta)

    results_payload: Dict[str, Any] = {}
    if "results_json" in artifacts:
        results_payload = _read_json(Path(artifacts["results_json"]))

    is_mcp = meta.get("mode") == "mcp" or "audit_log" in artifacts

    if is_mcp and "requirements" in artifacts and "compliance_decisions" in artifacts:
        requirements = _build_agentic_requirement_rows(
            Path(artifacts["compliance_decisions"]),
            Path(artifacts["requirements"]),
            Path(artifacts["evidence_map"]) if "evidence_map" in artifacts else None,
            meta.get("review_queue"),
            Path(artifacts["retrieval_plans"]) if "retrieval_plans" in artifacts else None,
        )
    else:
        requirements = _build_requirement_rows(results_payload, meta.get("review_queue"))

    summary_cards = _build_summary_cards_from_rows(requirements, metrics_payload)

    audit_log = []
    if is_mcp and "audit_log" in artifacts:
        audit_log = _read_json(Path(artifacts["audit_log"]))
        meta["agentic_metadata"] = _build_agentic_metadata(audit_log)
        timeline = _build_agentic_timeline(audit_log, run_scope=scope, run_title=title)
        log_summary = _build_agentic_log_summary(audit_log)
    else:
        logs_path, summary_path = _log_paths(run_id)
        logs_payload = _read_json(logs_path) if logs_path.exists() else []
        log_summary = _read_json(summary_path) if summary_path.exists() else {}
        timeline = _build_timeline(logs_payload, run_scope=scope, run_title=title)

    planning_trace = _planning_trace_from_artifacts(artifacts, audit_log=audit_log)
    for step in planning_trace:
        step["step_label"] = _step_label(step.get("action", ""))
        step["tone"] = _step_tone(step.get("action", ""))

    confidence_summary = _confidence_summary_from_rows(requirements)

    bundle = {
        "scope": scope,
        "url": f"/runs/{scope}",
        "title": title,
        "run_id": run_id,
        "mode": meta.get("mode", "mcp"),
        "mode_label": _humanize(meta.get("mode", "mcp")),
        "created_at": meta.get("created_at", ""),
        "created_label": _format_timestamp(meta.get("created_at", "")),
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "artifact_groups": _artifact_groups(artifacts),
        "documents": documents,
        "summary_cards": summary_cards,
        "requirements": requirements,
        "requirement_map": {row["id"]: row for row in requirements},
        "focus_items": _build_focus_items(requirements),
        "timeline": timeline,
        "timeline_preview": list(reversed(timeline[-8:])),
        "log_summary": log_summary,
        "evaluation": metrics_payload,
        "meta": meta,
        "results_payload": results_payload,
        "planning_trace": planning_trace,
        "confidence_summary": confidence_summary,
    }
    bundle["snapshot"] = _build_run_snapshot(
        meta=meta,
        summary_cards=summary_cards,
        requirements=requirements,
        log_summary=log_summary,
        documents=documents,
        timeline=timeline,
    )
    bundle["requirements_count"] = len(requirements)
    bundle["decisions_count"] = len(requirements)
    bundle["steps_count"] = len(planning_trace) or len(bundle.get("meta", {}).get("steps_completed", []))
    bundle["planner_mode"] = planning_trace[0].get("planner_mode", "llm") if planning_trace else "unknown"
    return bundle


def _all_run_bundles() -> List[Dict[str, Any]]:
    bundles = []
    for item in _run_directories():
        bundle = _load_run_bundle(Path(item["path"]), scope=item["scope"])
        if bundle and not _is_hidden_run(bundle.get("scope", ""), bundle.get("run_id", ""), bundle.get("title", "")):
            bundles.append(bundle)
    bundles.sort(key=lambda entry: entry.get("created_at", ""), reverse=True)
    return bundles


def _load_bundle_for_scope(scope: str) -> Optional[Dict[str, Any]]:
    resolved = _resolve_scope_to_dir(scope)
    if not resolved:
        return None
    real_scope = _default_demo_scope() if scope == "demo" else scope
    return _load_run_bundle(resolved, scope=real_scope)


def _size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def build_run_summaries(runs: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    bundles = runs if runs is not None else _all_run_bundles()
    summaries = []
    for bundle in bundles:
        if _is_hidden_run(bundle.get("scope", ""), bundle.get("run_id", ""), bundle.get("title", "")):
            continue
        confidence = bundle.get("confidence_summary", {}) or {}
        output_dir = Path(bundle.get("output_dir", ""))
        can_archive = _is_archivable_run_dir(output_dir) if output_dir.exists() else False
        readable_title = _readable_run_title(bundle.get("run_id", ""), bundle.get("title", ""))
        summaries.append(
            {
                "scope": bundle["scope"],
                "run_id": bundle["run_id"],
                "title": bundle["title"],
                "readable_title": readable_title,
                "requirements": bundle.get("requirements_count", 0),
                "decisions": bundle.get("decisions_count", 0),
                "steps": bundle.get("steps_count", 0),
                "planning_steps": bundle.get("steps_count", 0),
                "planner_mode": bundle.get("planner_mode", "unknown"),
                "compliant": bundle.get("summary_cards", {}).get("compliant", 0),
                "partial": bundle.get("summary_cards", {}).get("partial", 0),
                "not_compliant": bundle.get("summary_cards", {}).get("not_compliant", 0),
                "not_addressed": bundle.get("summary_cards", {}).get("not_addressed", 0),
                "accuracy": bundle.get("summary_cards", {}).get("accuracy"),
                "cohen_kappa": bundle.get("summary_cards", {}).get("cohen_kappa"),
                "confidence_min": confidence.get("min"),
                "confidence_max": confidence.get("max"),
                "confidence_mean": confidence.get("mean"),
                "confidence_min_label": f"{confidence.get('min'):.2f}" if confidence.get("min") is not None else "n/a",
                "confidence_max_label": f"{confidence.get('max'):.2f}" if confidence.get("max") is not None else "n/a",
                "date_label": bundle.get("created_label"),
                "view_url": f"/runs/{bundle['scope']}",
                "workflow_url": f"/runs/{bundle['scope']}/workflow",
                "live_url": f"/runs/{bundle['scope']}/live",
                "download_url": f"/runs/{bundle['scope']}/download",
                "archive_url": f"/runs/{bundle['scope']}/archive" if can_archive else None,
                "can_archive": can_archive,
            }
        )
    return summaries


def _documents_inventory(runs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    bundles = runs if runs is not None else _all_run_bundles()
    usage_by_path: Dict[str, List[Dict[str, Any]]] = {}

    for bundle in bundles:
        for document in bundle.get("meta", {}).get("documents", []):
            path = document.get("path")
            if not path:
                continue
            abs_path = str(Path(path).resolve())
            usage_by_path.setdefault(abs_path, []).append(
                {
                    "run_id": bundle["run_id"],
                    "scope": bundle["scope"],
                    "role": document.get("role", "unknown"),
                    "role_label": _role_label(document.get("role", "unknown")),
                    "requirements_extracted": bundle["summary_cards"]["total_requirements"]
                    if document.get("role") == "solicitation_or_requirement_source"
                    else 0,
                }
            )

    library_root = BASE_DIR / "data" / "library"
    category_docs: Dict[str, List[Dict[str, Any]]] = {}

    if library_root.exists():
        files = sorted(
            (path for path in library_root.rglob("*") if path.is_file()),
            key=lambda p: p.name.lower(),
        )
        for path in files:
            abs_path = str(path.resolve())
            rel_path = path.resolve().relative_to(library_root.resolve()).as_posix()
            category = rel_path.split("/", 1)[0]
            stat = path.stat()
            doc = {
                "path": abs_path,
                "name": path.name,
                "relative_path": rel_path,
                "folder_label": _humanize(category),
                "role_label": "Library document",
                "type": path.suffix.replace(".", "").upper() or "FILE",
                "size_bytes": stat.st_size,
                "size_label": _size_label(stat.st_size),
                "preview": _document_preview(abs_path, max_chars=9000),
                "usage": usage_by_path.get(abs_path, []),
                "search_text": " ".join([path.name, rel_path, category]).lower(),
            }
            category_docs.setdefault(category, []).append(doc)

    library_categories = []
    for category in sorted(category_docs):
        docs = category_docs[category]
        library_categories.append(
            {
                "key": category,
                "label": _humanize(category),
                "description": CATEGORY_DESCRIPTIONS.get(
                    category,
                    "Supporting documents available to the agent team during review and drafting.",
                ),
                "documents": docs,
                "count": len(docs),
            }
        )

    uploaded_documents: List[Dict[str, Any]] = []

    for upload_root in [UPLOADS_DIR, LEGACY_UPLOADS_DIR]:
        if not upload_root.exists():
            continue
        for path in sorted((p for p in upload_root.rglob("*") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True):
            abs_path = str(path.resolve())
            stat = path.stat()
            try:
                relative_path = path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
            except ValueError:
                relative_path = path.name
            uploaded_documents.append(
                {
                    "path": abs_path,
                    "name": path.name,
                    "scenario": "Workspace uploads",
                    "relative_path": relative_path,
                    "role": "uploaded_input",
                    "role_label": "Uploaded input",
                    "type": path.suffix.replace(".", "").upper() or "FILE",
                    "size_bytes": stat.st_size,
                    "size_label": _size_label(stat.st_size),
                    "preview": _document_preview(abs_path, max_chars=9000),
                    "usage": usage_by_path.get(abs_path, []),
                    "search_text": " ".join(
                        [
                            path.name,
                            relative_path,
                            "uploaded input",
                        ]
                    ).lower(),
                }
            )

    library_documents = [doc for category in library_categories for doc in category["documents"]]
    return {
        "library_categories": library_categories,
        "library_documents": library_documents,
        "uploaded_documents": uploaded_documents,
        "all_documents": library_documents + uploaded_documents,
    }


def _activity_event_from_timeline(item: Dict[str, Any]) -> Dict[str, Any]:
    msg_type = item.get("msg_type")
    if msg_type == "tool_call":
        category = "tool"
        category_label = "Tool Calls"
    elif msg_type in {"goal", "result", "spawn", "terminate"}:
        category = "agent"
        category_label = "Agent Communication"
    elif msg_type == "status" and "planning_decision" in item.get("payload_preview", ""):
        category = "planning"
        category_label = "Planning"
    elif msg_type in {"status", "error"}:
        category = "system"
        category_label = "System Events"
    else:
        category = "system"
        category_label = "System Events"

    source = _friendly_agent_name(str(item.get("sender") or item.get("agent") or "system"))
    target = _friendly_agent_name(str(item.get("recipient") or "")) if item.get("recipient") else ""
    payload_json = item.get("payload_json") or item.get("output_json") or "{}"
    return {
        "timestamp": item.get("timestamp", ""),
        "timestamp_label": item.get("timestamp_label", ""),
        "event_type": item.get("msg_type") or item.get("action", "event"),
        "category": category,
        "category_label": category_label,
        "run_scope": item.get("run_scope"),
        "run_title": item.get("run_title"),
        "source": source,
        "target": target,
        "summary": item.get("title") or item.get("comment"),
        "details": item.get("comment", ""),
        "payload_json": payload_json,
        "search_text": " ".join(
            [
                str(item.get("title", "")),
                str(item.get("comment", "")),
                str(item.get("run_title", "")),
                source,
                target,
                str(item.get("msg_type", "")),
                str(item.get("action", "")),
            ]
        ).lower(),
    }


def _planning_events_for_bundle(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = []
    for step in bundle.get("planning_trace", []):
        confidence_after = step.get("confidence_after", {}) or {}
        confidence_text = ""
        if confidence_after:
            min_c = confidence_after.get("min")
            max_c = confidence_after.get("max")
            mean_c = confidence_after.get("mean")
            if min_c is not None and max_c is not None and mean_c is not None:
                confidence_text = f" Confidence: {min_c:.2f}-{max_c:.2f} (mean {mean_c:.2f})."
        events.append(
            {
                "timestamp": bundle.get("created_at", ""),
                "timestamp_label": bundle.get("created_label", ""),
                "event_type": "planning_decision",
                "category": "planning",
                "category_label": "Planning",
                "run_scope": bundle.get("scope"),
                "run_title": bundle.get("title"),
                "source": "Orchestrator",
                "target": _step_label(step.get("action", "")).lower(),
                "summary": f"Step {step.get('step')}: {_step_label(step.get('action', ''))}",
                "details": f"{step.get('reasoning', '')}{confidence_text}",
                "payload_json": json.dumps(step, indent=2),
                "search_text": " ".join(
                    [
                        str(step.get("action", "")),
                        str(step.get("reasoning", "")),
                        str(bundle.get("title", "")),
                    ]
                ).lower(),
            }
        )
    return events


def _file_events_for_bundle(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    events = [
        {
            "timestamp": bundle.get("created_at", ""),
            "timestamp_label": bundle.get("created_label", ""),
            "event_type": "run_started",
            "category": "system",
            "category_label": "System Events",
            "run_scope": bundle.get("scope"),
            "run_title": bundle.get("title"),
            "source": "system",
            "target": bundle.get("run_id"),
            "summary": f"Review started: {_readable_run_title(bundle.get('run_id', ''), bundle.get('title', ''))}",
            "details": f"Workflow {str(bundle.get('meta', {}).get('workflow', 'compliance_review')).replace('_', ' ')} initialized.",
            "payload_json": json.dumps({"run_id": bundle.get("run_id"), "output_dir": bundle.get("output_dir")}, indent=2),
            "search_text": f"review started {bundle.get('run_id')} {bundle.get('title')}".lower(),
        }
    ]
    for artifact_name, path_str in bundle.get("artifacts", {}).items():
        path = Path(path_str)
        if not path.exists():
            continue
        timestamp = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        events.append(
            {
                "timestamp": timestamp,
                "timestamp_label": _format_timestamp(timestamp),
                "event_type": "artifact_written",
                "category": "system",
                "category_label": "System Events",
                "run_scope": bundle.get("scope"),
                "run_title": bundle.get("title"),
                "source": "filesystem",
                "target": artifact_name,
                "summary": f"Artifact written: {path.name}",
                "details": f"Generated file: {path.name}",
                "payload_json": json.dumps({"artifact": artifact_name, "file": path.name}, indent=2),
                "search_text": f"artifact {artifact_name} {path.name} {bundle.get('title')}".lower(),
            }
        )
    return events


def summarize_activity(audit_log: List[Dict[str, Any]], planning_trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw audit events into human-readable activity summaries."""
    summaries: List[Dict[str, Any]] = []
    spawn_agents: List[str] = []
    goals_sent: List[Dict[str, str]] = []
    results_received: List[str] = []
    skills_used: List[str] = []

    for entry in audit_log:
        msg_type = entry.get("type", "")
        payload = entry.get("payload", {}) or {}

        if msg_type == "spawn":
            agent_id = payload.get("agent_id") or entry.get("recipient", "")
            if agent_id:
                spawn_agents.append(_friendly_agent_name(str(agent_id)))
        elif msg_type == "goal":
            goals_sent.append(
                {
                    "from": _friendly_agent_name(str(entry.get("sender", ""))),
                    "to": _friendly_agent_name(str(entry.get("recipient", ""))),
                    "task": _summarize_text(str(payload.get("task", payload.get("goal", ""))), max_chars=100),
                }
            )
        elif msg_type == "result":
            sender = entry.get("sender", "")
            if sender:
                results_received.append(_friendly_agent_name(str(sender)))
        elif msg_type == "tool_call":
            skill = payload.get("tool", payload.get("skill", "unknown"))
            if skill:
                skills_used.append(str(skill))

    if spawn_agents:
        unique_agents = sorted(set(spawn_agents))
        summaries.append(
            {
                "type": "lifecycle",
                "title": f"{len(unique_agents)} agents activated",
                "detail": ", ".join(unique_agents),
                "icon": "team",
            }
        )

    if goals_sent:
        targets = sorted({goal["to"] for goal in goals_sent if goal["to"]})
        summaries.append(
            {
                "type": "delegation",
                "title": f"{len(goals_sent)} tasks delegated",
                "detail": "Orchestrator assigned work to " + ", ".join(targets),
                "icon": "assign",
            }
        )

    if results_received:
        summaries.append(
            {
                "type": "result",
                "title": f"{len(results_received)} results returned",
                "detail": "Results came back from " + ", ".join(sorted(set(results_received))),
                "icon": "result",
            }
        )

    if skills_used:
        unique_skills = sorted(set(skills_used))
        summaries.append(
            {
                "type": "skill",
                "title": f"{len(skills_used)} skill invocations ({len(unique_skills)} unique)",
                "detail": "Skills used: " + ", ".join(unique_skills[:10]),
                "icon": "tool",
            }
        )

    for step in planning_trace or []:
        action = str(step.get("action", "")).replace("dispatch_", "").replace("_", " ").title()
        summaries.append(
            {
                "type": "planning",
                "title": f"Step {step.get('step')}: {action}",
                "detail": step.get("reasoning", ""),
                "mode": step.get("planner_mode", ""),
                "confidence": step.get("confidence_after", {}) or {},
                "icon": "brain",
            }
        )

    return summaries


def _activity_feed(runs: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    bundles = runs if runs is not None else _all_run_bundles()
    events = []
    for bundle in bundles:
        for item in bundle.get("timeline", []):
            events.append(_activity_event_from_timeline(item))
        events.extend(_planning_events_for_bundle(bundle))
        events.extend(_file_events_for_bundle(bundle))
    events.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return events


def _recent_runs(limit: int = 6) -> List[Dict[str, Any]]:
    return _all_run_bundles()[:limit]


def _system_snapshot(runs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    bundles = runs if runs is not None else _all_run_bundles()
    feed = _activity_feed(bundles)
    docs = _documents_inventory(bundles)
    files = _build_file_workspace()
    capabilities = _agentic_capabilities()
    review_queue = sum(bundle["snapshot"]["review_queue_count"] for bundle in bundles)
    attention = sum(bundle["snapshot"]["attention_count"] for bundle in bundles)
    agents = sorted(
        {
            _humanize(item["source"])
            for item in feed
            if item.get("source")
            and item.get("source") not in {"bus", "broadcast", "filesystem", "system"}
            and not str(item.get("source")).startswith("skill:")
        }
    )
    spawned_sub_agents = sum(
        len(bundle.get("meta", {}).get("agentic_metadata", {}).get("sub_agents_spawned", []))
        for bundle in bundles
    )
    return {
        "case_count": len(bundles),
        "document_count": len(docs["all_documents"]),
        "area_count": len(_scenario_catalog()),
        "managed_file_count": files["file_count"],
        "file_root_count": files["root_count"],
        "activity_count": len(feed),
        "review_queue_count": review_queue,
        "attention_count": attention,
        "agent_count": len(agents),
        "agent_labels": agents,
        "registered_agent_count": capabilities["agent_count"],
        "skill_count": capabilities["skill_count"],
        "sub_agent_count": spawned_sub_agents,
        "top_areas": [{"name": key, "count": 1} for key in list(_scenario_catalog().keys())[:6]],
    }


def _activity_stats(feed: List[Dict[str, Any]]) -> Dict[str, Any]:
    agents = sorted(
        {
            _humanize(item["source"])
            for item in feed
            if item.get("source")
            and item.get("source") not in {"bus", "broadcast", "filesystem", "system"}
            and not str(item.get("source")).startswith("skill:")
        }
    )
    runs = sorted({item["run_title"] for item in feed if item.get("run_title")})
    errors = sum(1 for item in feed if item.get("event_type") == "error")
    return {
        "activity_count": len(feed),
        "agent_count": len(agents),
        "case_count": len(runs),
        "error_count": errors,
    }


def get_notification_context(contracts: List[Dict[str, Any]], run_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    notifications = generate_notifications(contracts, run_summaries)
    critical_notifications = [item for item in notifications if item.get("severity") == "critical"]
    return {
        "notifications": notifications,
        "notification_count": len(notifications),
        "critical_count": len(critical_notifications),
        "critical_notifications": critical_notifications,
    }


def _base_context(
    request: Request,
    *,
    page_title: str,
    hero_title: str,
    hero_subtitle: str,
    active_nav: str,
) -> Dict[str, Any]:
    runs = _all_run_bundles()
    run_summaries = build_run_summaries(runs)
    from compliance_agent.contracts.tracker import enrich_with_run_data, get_all_contracts

    contracts = enrich_with_run_data(get_all_contracts(), run_summaries)
    notification_context = get_notification_context(contracts, run_summaries)
    return {
        "request": request,
        "page_title": page_title,
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        "show_page_header": True,
        "active_nav": active_nav,
        "active_page": active_nav,
        "system_snapshot": _system_snapshot(runs),
        "recent_runs": runs[:6],
        "latest_run": runs[0] if runs else None,
        "run_summaries": run_summaries,
        **notification_context,
    }


def _build_agentic_metadata(audit_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    static_agents = set(_agentic_capabilities()["agent_ids"])
    active_entries = [entry for entry in audit_log if entry.get("type") not in {"spawn", "terminate"}]
    agents_used = sorted(
        {
            entry.get("sender")
            for entry in active_entries
            if entry.get("sender")
            and entry.get("sender") not in {"bus", "broadcast"}
            and not str(entry.get("sender")).startswith("skill:")
        }
    )
    message_types = sorted({entry.get("type", "unknown") for entry in audit_log})
    skill_invocations = [
        entry.get("recipient", "").replace("skill:", "")
        for entry in audit_log
        if entry.get("type") == "tool_call" and str(entry.get("recipient", "")).startswith("skill:")
    ]
    sub_agents_spawned = [
        entry.get("recipient")
        for entry in audit_log
        if entry.get("type") == "spawn"
        and entry.get("recipient")
        and entry.get("recipient") not in static_agents
    ]
    return {
        "agents_used": agents_used,
        "message_count": len(audit_log),
        "message_types": message_types,
        "skills_invoked": skill_invocations,
        "skills_used": sorted(set(skill_invocations)),
        "sub_agents_spawned": sub_agents_spawned,
    }


def _document_payloads_from_linear_inputs(
    *,
    policy_path: str,
    response_path: str,
    glossary_path: Optional[str] = None,
    context_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    documents = [
        {
            "path": policy_path,
            "role": "solicitation_or_requirement_source",
            "label": "Source document",
        },
        {
            "path": response_path,
            "role": "response_or_proposal",
            "label": "Response document",
        },
    ]
    if glossary_path:
        documents.append(
            {
                "path": glossary_path,
                "role": "glossary",
                "label": "Glossary",
            }
        )
    for index, path in enumerate(context_paths or [], start=1):
        documents.append(
            {
                "path": path,
                "role": "prior_contract",
                "label": f"Prior context {index}",
            }
        )
    return documents


def _execute_mcp_review(
    *,
    title: str,
    documents: List[Any],
    output_dir: Path,
    run_id: str,
    workflow_type: str = "compliance_review",
    ground_truth_path: Optional[str] = None,
    stage_callback=None,
) -> Dict[str, Any]:
    """Execute a compliance review through the MCP pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_documents = _normalize_agentic_documents(documents)
    goal = {
        "task": workflow_type,
        "workflow_type": workflow_type,
        "documents": normalized_documents,
        "output_dir": str(output_dir.parent),
        "run_id": run_id,
    }

    result = asyncio.run(mcp_run(goal, stage_callback=stage_callback))
    run_dir = Path(result.get("run_dir", str(output_dir)))
    audit_log = result.get("audit_log", [])

    evaluation_bundle = None
    results_json = run_dir / "compliance_results.json"
    if ground_truth_path and results_json.exists():
        evaluation_bundle = evaluate_scenario_run(
            ground_truth_path=str(ground_truth_path),
            system_output_path=str(results_json),
            output_dir=str(run_dir),
        )

    meta = {
        "title": title,
        "run_id": run_id,
        "mode": "mcp",
        "created_at": datetime.now().isoformat(),
        "documents": normalized_documents,
        "ground_truth_path": str(ground_truth_path) if ground_truth_path else None,
        "review_queue": result.get("outputs", {}).get("review_queue", []),
        "workflow": result.get("workflow", workflow_type),
        "steps_completed": [step[0] for step in result.get("steps", [])],
        "document_manifest": result.get("outputs", {}).get("document_manifest"),
        "artifacts": result.get("artifacts", {}),
        "evaluation": evaluation_bundle,
        "agentic_metadata": _build_agentic_metadata(audit_log),
    }
    _write_json(_meta_path(run_dir), meta)
    return meta


def _execute_review(
    *,
    title: str,
    output_dir: Path,
    run_id: str,
    workflow_type: str = "compliance_review",
    documents: Optional[List[Any]] = None,
    ground_truth_path: Optional[str] = None,
    policy_path: Optional[str] = None,
    response_path: Optional[str] = None,
    glossary_path: Optional[str] = None,
    context_paths: Optional[List[str]] = None,
    stage_callback=None,
) -> Dict[str, Any]:
    mcp_documents = documents or _document_payloads_from_linear_inputs(
        policy_path=policy_path or "",
        response_path=response_path or "",
        glossary_path=glossary_path,
        context_paths=context_paths,
    )
    return _execute_mcp_review(
        title=title,
        documents=mcp_documents,
        output_dir=output_dir,
        run_id=run_id,
        workflow_type=workflow_type,
        ground_truth_path=ground_truth_path,
        stage_callback=stage_callback,
    )


def _run_default_demo_case() -> Dict[str, Any]:
    scenario = load_scenario(DEFAULT_SCENARIO_DIR)
    output_dir = scenario_output_dir(scenario)
    ground_truth = scenario_ground_truth_path(scenario, DEFAULT_SCENARIO_DIR)
    documents = [
        {
            "path": document.path,
            "role": document.role,
            "label": document.label or _role_label(document.role),
            "confidence": document.confidence,
            "metadata": document.metadata,
        }
        for document in scenario.documents
    ]
    inputs = extract_linear_inputs(scenario.documents)
    return _execute_review(
        title="Stakeholder demo case",
        documents=documents,
        policy_path=inputs["policy"],
        response_path=inputs["response"],
        glossary_path=inputs["glossary"],
        context_paths=inputs["context"],
        output_dir=output_dir,
        run_id=scenario.effective_output_subdir,
        ground_truth_path=ground_truth,
    )


def _save_upload(upload: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(upload.filename or "upload.bin").name
    destination = target_dir / filename
    if destination.exists():
        destination = target_dir / f"{destination.stem}_{uuid4().hex[:6]}{destination.suffix}"
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return destination


def _phase_label_for_agent(agent_id: str) -> str:
    labels = {
        "intake_agent": "Intake",
        "extraction_agent": "Extraction",
        "comparison_agent": "Comparison",
        "retrieval_agent": "Retrieval",
        "compliance_agent": "Compliance",
        "reanalysis": "Reanalysis",
        "qa_agent": "QA",
        "drafting_agent": "Drafting",
    }
    if agent_id.startswith("reanalysis_sub_"):
        return "Reanalysis"
    return labels.get(agent_id, _humanize(agent_id))


def _build_workflow_visualization(audit_log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Transform an MCP audit log into swim-lane friendly workflow data."""
    agents = []
    seen_agents = set()
    for entry in audit_log:
        if entry.get("type") in {"spawn", "terminate"} and entry.get("sender") == "bus":
            continue
        for field in ("sender", "recipient"):
            name = entry.get(field, "")
            if name and name not in {"bus", "broadcast"} and not str(name).startswith("skill:") and name not in seen_agents:
                seen_agents.add(name)
                agents.append(name)

    skills = sorted(
        {
            entry.get("recipient", "").replace("skill:", "")
            for entry in audit_log
            if entry.get("type") == "tool_call" and str(entry.get("recipient", "")).startswith("skill:")
        }
    )

    phases = []
    current_phase_agent = None
    phase_entries: List[Dict[str, Any]] = []
    for entry in audit_log:
        if entry.get("type") == "goal" and entry.get("sender") == "orchestrator":
            if current_phase_agent and phase_entries:
                phases.append(
                    {
                        "agent": current_phase_agent,
                        "label": _phase_label_for_agent(current_phase_agent),
                        "entries": phase_entries,
                        "message_count": len(phase_entries),
                    }
                )
            current_phase_agent = entry.get("recipient", "unknown")
            phase_entries = [entry]
        else:
            phase_entries.append(entry)
    if current_phase_agent and phase_entries:
        phases.append(
            {
                "agent": current_phase_agent,
                "label": _phase_label_for_agent(current_phase_agent),
                "entries": phase_entries,
                "message_count": len(phase_entries),
            }
        )

    messages = []
    active_phase = "System Setup"
    for index, entry in enumerate(audit_log):
        if entry.get("type") == "goal" and entry.get("sender") == "orchestrator":
            active_phase = _phase_label_for_agent(entry.get("recipient", "unknown"))
        messages.append(
            {
                "index": index,
                "type": entry.get("type", "unknown"),
                "sender": entry.get("sender", ""),
                "recipient": entry.get("recipient", ""),
                "timestamp": entry.get("timestamp", ""),
                "payload_keys": entry.get("payload_keys", []),
                "correlation_id": entry.get("correlation_id"),
                "phase": active_phase,
                "display": _agentic_event_display(
                    entry.get("type", ""),
                    entry.get("sender", ""),
                    entry.get("recipient", ""),
                    entry.get("payload_keys", []),
                ),
            }
        )

    stats = {
        "total_messages": len(audit_log),
        "agent_count": len(agents),
        "skill_count": len(skills),
        "phase_count": len(phases),
        "message_type_counts": {},
    }
    for entry in audit_log:
        msg_type = entry.get("type", "unknown")
        stats["message_type_counts"][msg_type] = stats["message_type_counts"].get(msg_type, 0) + 1

    return {
        "agents": agents,
        "skills": skills,
        "phases": phases,
        "messages": messages,
        "stats": stats,
    }


WORKSPACE_DOWNLOAD_ROOTS = {
    "output": BASE_DIR / "output",
    "data": BASE_DIR / "data",
    "scenarios": BASE_DIR / "examples" / "scenarios",
    "uploads": UPLOADS_DIR,
}


def _is_within(parent: Path, child: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return child_resolved == parent_resolved or parent_resolved in child_resolved.parents


def _resolve_workspace_path(root_key: str, relative_path: str) -> Path:
    root = WORKSPACE_DOWNLOAD_ROOTS.get(root_key)
    if not root:
        raise HTTPException(status_code=404, detail="Workspace root not found.")
    target = (root / relative_path).resolve()
    if not _is_within(root, target):
        raise HTTPException(status_code=404, detail="Invalid workspace path.")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return target


def build_file_tree(root_dirs: list[str]) -> list[dict]:
    """Build nested file tree structure for the template."""

    def scan_dir(path: Path) -> dict:
        node = {
            "name": path.name,
            "path": str(path),
            "is_dir": path.is_dir(),
            "children": [],
            "size": None,
        }
        if path.is_dir():
            try:
                children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            except PermissionError:
                children = []
            for child in children:
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                node["children"].append(scan_dir(child))
        else:
            size = path.stat().st_size
            if size < 1024:
                node["size"] = f"{size} B"
            elif size < 1024 * 1024:
                node["size"] = f"{size // 1024} KB"
            else:
                node["size"] = f"{size // (1024 * 1024)} MB"
        return node

    trees: list[dict] = []
    for root in root_dirs:
        p = Path(root)
        if p.exists():
            trees.append(scan_dir(p))
    return trees


def _build_tree_nodes(root_key: str, base_path: Path, path: Path, depth: int = 0) -> Dict[str, Any]:
    if path.is_file():
        rel = path.resolve().relative_to(base_path.resolve()).as_posix()
        stat = path.stat()
        can_delete = _is_within(BASE_DIR / "output", path) or _is_within(UPLOADS_DIR, path)
        preview_prefix = {
            "output": "output",
            "data": "data",
            "scenarios": "examples/scenarios",
        }.get(root_key, root_key)
        return {
            "type": "file",
            "name": path.name,
            "relative_path": rel,
            "size_label": _size_label(stat.st_size),
            "preview_path": f"{preview_prefix}/{rel}",
            "preview_url": f"/workspace-files/view/{root_key}/{rel}",
            "download_url": f"/workspace-files/download/{root_key}/{rel}",
            "delete_url": f"/workspace-files/delete/{root_key}/{rel}",
            "can_delete": can_delete,
        }

    children = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        entries = []
    for entry in entries:
        children.append(_build_tree_nodes(root_key, base_path, entry, depth + 1))
    rel_dir = "" if path == base_path else path.resolve().relative_to(base_path.resolve()).as_posix()
    return {
        "type": "directory",
        "name": path.name,
        "relative_path": rel_dir,
        "children": children,
    }


def _workspace_tree() -> Dict[str, Any]:
    roots = [
        {"key": "output", "label": "output/", "path": BASE_DIR / "output"},
        {"key": "data", "label": "data/", "path": BASE_DIR / "data"},
        {"key": "scenarios", "label": "examples/scenarios/", "path": BASE_DIR / "examples" / "scenarios"},
    ]
    tree_roots = []
    for root in roots:
        path = root["path"]
        if not path.exists():
            continue
        tree_roots.append(
            {
                "key": root["key"],
                "label": root["label"],
                "tree": _build_tree_nodes(root["key"], path, path),
            }
        )

    run_downloads = [
        {
            "scope": bundle["scope"],
            "run_id": bundle["run_id"],
            "title": bundle["title"],
            "download_url": f"/runs/{bundle['scope']}/download",
        }
        for bundle in _all_run_bundles()
    ]
    return {"roots": tree_roots, "run_downloads": run_downloads}


def _file_preview_payload(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            payload = _read_json(path)
            return {"kind": "json", "text": json.dumps(payload, indent=2)}
        except Exception:
            return {"kind": "text", "text": path.read_text(encoding="utf-8", errors="ignore")}
    if suffix == ".csv":
        rows = []
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                rows = list(reader)
        except Exception:
            return {"kind": "text", "text": "Preview unavailable."}
        headers = rows[0] if rows else []
        body = rows[1:101] if len(rows) > 1 else []
        return {"kind": "csv", "headers": headers, "rows": body}
    if suffix in {".md", ".txt", ".log", ".yaml", ".yml"}:
        return {"kind": "text", "text": path.read_text(encoding="utf-8", errors="ignore")[:20000]}
    return {"kind": "text", "text": "Preview unavailable for this file type."}


def _preview_path_from_query(path_value: str) -> Path:
    requested = Path(path_value)
    target = requested if requested.is_absolute() else (BASE_DIR / requested)
    return target.resolve()


def _allowed_preview_roots() -> List[Path]:
    return [
        (BASE_DIR / "output").resolve(),
        (BASE_DIR / "data").resolve(),
        (BASE_DIR / "examples").resolve(),
    ]


def _simple_markdown_to_html(markdown_text: str) -> str:
    lines = markdown_text.replace("\r\n", "\n").split("\n")
    html_lines: List[str] = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
            continue
        if stripped.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
            continue
        if stripped.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
            continue
        if stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
            continue
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        if not stripped:
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{stripped}</p>")

    if in_list:
        html_lines.append("</ul>")

    html = "\n".join(html_lines)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    return html


def _requirement_detail_rows(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    requirements = [dict(item) for item in (bundle.get("requirements") or [])]
    artifacts = bundle.get("artifacts", {}) or {}

    decisions_by_id: Dict[str, Dict[str, Any]] = {}
    if artifacts.get("compliance_decisions"):
        try:
            for decision in _read_json(Path(artifacts["compliance_decisions"])):
                req_id = decision.get("requirement_id")
                if req_id:
                    decisions_by_id[str(req_id)] = decision
        except Exception:
            decisions_by_id = {}

    evidence_map_payload: Dict[str, Any] = {}
    if artifacts.get("evidence_map"):
        try:
            loaded = _read_json(Path(artifacts["evidence_map"]))
            if isinstance(loaded, dict):
                evidence_map_payload = loaded
        except Exception:
            evidence_map_payload = {}

    detailed_rows: List[Dict[str, Any]] = []
    for index, row in enumerate(requirements, start=1):
        req_id = str(row.get("id") or row.get("requirement_id") or f"REQ_{index:04d}")
        decision = decisions_by_id.get(req_id, {})
        requirement_text = row.get("text") or row.get("requirement_text") or decision.get("requirement_text") or ""

        raw_chunks = row.get("evidence") or row.get("evidence_chunks") or evidence_map_payload.get(req_id, [])
        if isinstance(raw_chunks, dict):
            raw_chunks = raw_chunks.get("results", [])

        evidence_chunks = []
        for chunk in raw_chunks or []:
            source_citation = (
                chunk.get("source_citation")
                or chunk.get("evidence_citation")
                or chunk.get("section_title")
                or chunk.get("page_range")
                or "Unknown source"
            )
            retrieval_score = chunk.get("retrieval_score", chunk.get("hybrid_score", 0.0))
            evidence_chunks.append(
                {
                    "evidence_chunk_id": chunk.get("evidence_chunk_id", chunk.get("chunk_id", "")),
                    "evidence_text": chunk.get("evidence_text", chunk.get("text", "")),
                    "source_citation": source_citation,
                    "evidence_citation": chunk.get("evidence_citation", source_citation),
                    "retrieval_score": retrieval_score if retrieval_score is not None else 0.0,
                }
            )

        suggested_edits = _normalize_suggested_edits(
            row.get("suggested_edits") if row.get("suggested_edits") is not None else decision.get("suggested_edits")
        )
        detailed = {
            **row,
            "requirement_id": req_id,
            "detail_dom_id": re.sub(r"[^a-zA-Z0-9_-]+", "_", req_id),
            "requirement_text": requirement_text,
            "label": row.get("status", decision.get("label", "not_addressed")),
            "explanation": row.get("explanation", decision.get("explanation", "")),
            "evidence_chunks": evidence_chunks,
            "evidence_chunk_ids": [chunk.get("evidence_chunk_id") for chunk in evidence_chunks if chunk.get("evidence_chunk_id")],
            "execution_mode": row.get("execution_mode") or decision.get("execution_mode") or "fallback",
            "suggested_edits": suggested_edits,
            "citation_coverage": row.get("citation_coverage", decision.get("citation_coverage")),
            "citation_penalty": row.get("citation_penalty", decision.get("citation_penalty")),
            "citation_validation_status": row.get("citation_validation_status", decision.get("citation_validation_status")),
            "invalid_citation_ids": row.get("invalid_citation_ids", decision.get("invalid_citation_ids", [])) or [],
        }
        detailed_rows.append(detailed)
    return detailed_rows


@lru_cache(maxsize=1)
def _agent_skill_map_from_source() -> Dict[str, List[str]]:
    agents_dir = BASE_DIR / "compliance_agent" / "agents"
    mapping: Dict[str, List[str]] = {}
    for file_path in agents_dir.glob("*_agent.py"):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        agent_ids = re.findall(r'agent_id:\s*str\s*=\s*"([^"]+)"', text)
        if not agent_ids:
            continue
        skills = sorted(set(re.findall(r'use_skill\("([^"]+)"', text)))
        mapping[agent_ids[0]] = skills
    return mapping


def _latest_agentic_bundle() -> Optional[Dict[str, Any]]:
    for bundle in _all_run_bundles():
        if bundle.get("artifacts", {}).get("audit_log"):
            return bundle
    return None


def _agent_registry_data() -> Dict[str, Any]:
    bundle = _latest_agentic_bundle()
    if not bundle:
        base_agents = _agentic_capabilities()["agent_ids"]
        declared_skill_map = _agent_skill_map_from_source()
        agents = []
        for agent_id in base_agents:
            profile = AGENT_DESCRIPTIONS.get(agent_id, {})
            agents.append(
                {
                    "agent_id": agent_id,
                    "name": profile.get("title", _humanize(agent_id)),
                    "role": profile.get("role", "Specialized role"),
                    "description": profile.get("description", "No description available."),
                    "analogy": profile.get("analogy", ""),
                    "skills": sorted(declared_skill_map.get(agent_id, [])),
                    "status": "registered",
                    "messages_sent": 0,
                    "messages_received": 0,
                    "message_count": 0,
                }
            )
        return {
            "agents": agents,
            "matrix": [],
            "matrix_agents": base_agents,
            "skills": [],
            "skill_groups": [],
            "latest_run": None,
        }

    audit_log = _read_json(Path(bundle["artifacts"]["audit_log"]))
    base_agents = _agentic_capabilities()["agent_ids"]
    declared_skill_map = _agent_skill_map_from_source()
    run_skill_map: Dict[str, set[str]] = {agent: set(declared_skill_map.get(agent, [])) for agent in base_agents}

    active_agents = {
        entry.get("sender")
        for entry in audit_log
        if entry.get("sender") in base_agents and entry.get("type") not in {"spawn", "terminate"}
    } | {
        entry.get("recipient")
        for entry in audit_log
        if entry.get("recipient") in base_agents and entry.get("type") not in {"spawn", "terminate"}
    }

    for entry in audit_log:
        if entry.get("type") == "tool_call" and str(entry.get("recipient", "")).startswith("skill:"):
            sender = entry.get("sender")
            skill_name = str(entry.get("recipient")).replace("skill:", "")
            if sender in run_skill_map:
                run_skill_map[sender].add(skill_name)

    agents = []
    for agent_id in base_agents:
        sent = sum(1 for entry in audit_log if entry.get("sender") == agent_id)
        received = sum(1 for entry in audit_log if entry.get("recipient") == agent_id)
        profile = AGENT_DESCRIPTIONS.get(agent_id, {})
        agents.append(
            {
                "agent_id": agent_id,
                "name": profile.get("title", _humanize(agent_id)),
                "role": profile.get("role", "Specialized role"),
                "description": profile.get("description", "No description available."),
                "analogy": profile.get("analogy", ""),
                "skills": sorted(run_skill_map.get(agent_id, set())),
                "status": "active" if agent_id in active_agents else "registered",
                "messages_sent": sent,
                "messages_received": received,
                "message_count": sent + received,
            }
        )

    matrix_agents = list(base_agents)
    matrix_counts: Dict[str, Dict[str, int]] = {
        src: {dst: 0 for dst in matrix_agents}
        for src in matrix_agents
    }
    for entry in audit_log:
        src = entry.get("sender")
        dst = entry.get("recipient")
        if src in matrix_agents and dst in matrix_agents:
            matrix_counts[src][dst] += 1

    matrix = []
    for src in matrix_agents:
        row = {"agent": src, "counts": [matrix_counts[src][dst] if src != dst else None for dst in matrix_agents]}
        matrix.append(row)

    registry = SkillRegistry()
    for module in [
        parsing,
        chunking,
        extraction,
        classification,
        retrieval,
        reasoning,
        scoring,
        comparison,
        drafting,
        qa,
    ]:
        module.register_skills(registry)

    skills_table = []
    for name in sorted(registry.list_all()):
        skill = registry.get(name)
        if not skill:
            continue
        users = sorted([agent for agent, skills in run_skill_map.items() if name in skills])
        skills_table.append(
            {
                "name": name,
                "tags": ", ".join(skill.tags) if skill.tags else "—",
                "llm_tier": skill.llm_tier,
                "agents": ", ".join(_humanize(agent) for agent in users) if users else "—",
            }
        )

    available_skills = set(registry.list_all())
    skill_groups = []
    for group in SKILL_GROUP_DEFINITIONS:
        grouped = [skill for skill in group["skills"] if skill in available_skills]
        if not grouped:
            continue
        skill_groups.append(
            {
                "label": group["label"],
                "skills": grouped,
                "used_by": group["used_by"],
            }
        )

    return {
        "agents": agents,
        "matrix": matrix,
        "matrix_agents": matrix_agents,
        "skills": skills_table,
        "skill_groups": skill_groups,
        "latest_run": bundle,
    }


@app.get("/health")
def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat_endpoint(request: Request) -> Dict[str, str]:
    """Handle chat assistant queries."""
    from compliance_agent.agents.chat_agent import answer_question
    from compliance_agent.contracts.tracker import enrich_with_run_data, get_all_contracts

    body = await request.json()
    question = body.get("question", "")
    if not str(question).strip():
        return {"answer": "Please ask a question about your contracts or compliance reviews."}

    contracts = get_all_contracts()
    run_summaries = build_run_summaries()
    contracts = enrich_with_run_data(contracts, run_summaries)
    notifications = generate_notifications(contracts, run_summaries)

    answer = await answer_question(str(question), contracts, run_summaries, notifications)
    return {"answer": answer}


@app.get("/", response_class=HTMLResponse)
def dashboard_home(request: Request) -> HTMLResponse:
    from compliance_agent.contracts.tracker import (
        STAGES,
        enrich_with_run_data,
        get_all_contracts,
        get_pipeline_summary,
    )

    context = _base_context(
        request,
        page_title="Contracts",
        hero_title="Contracts",
        hero_subtitle="Track each contract from forecast through delivery and open AI analysis where available.",
        active_nav="contracts",
    )

    contracts = get_all_contracts()
    pipeline = get_pipeline_summary()
    run_summaries = build_run_summaries()
    contracts = enrich_with_run_data(contracts, run_summaries)
    context.update(
        {
            "contracts": contracts,
            "pipeline": pipeline,
            "stages": STAGES,
            "stage_explanations": STAGE_EXPLANATIONS,
        }
    )
    return templates.TemplateResponse("index.html", context)


@app.get("/documents", response_class=HTMLResponse)
def documents_page(request: Request) -> HTMLResponse:
    context = _base_context(
        request,
        page_title="Document Library",
        hero_title="Document Library",
        hero_subtitle="Company documents organized for compliance review and proposal drafting support.",
        active_nav="library",
    )
    inventory = _documents_inventory(_all_run_bundles())
    context["inventory"] = inventory
    return templates.TemplateResponse("documents.html", context)


@app.get("/library", response_class=HTMLResponse)
def library_page(request: Request) -> HTMLResponse:
    return documents_page(request)


@app.post("/documents/upload")
def upload_documents(files: List[UploadFile] = File(...)) -> RedirectResponse:
    upload_dir = UPLOADS_DIR / f"uploads-{_now_stamp()}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for upload in files:
        if upload and upload.filename:
            _save_upload(upload, upload_dir)
    return RedirectResponse(url="/library", status_code=303)


@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request) -> HTMLResponse:
    context = _base_context(
        request,
        page_title="Reviews & Analysis",
        hero_title="Reviews & Analysis",
        hero_subtitle="Each review below is a complete AI compliance analysis with confidence and action guidance.",
        active_nav="reviews",
    )
    context["run_rows"] = build_run_summaries(_all_run_bundles())
    return templates.TemplateResponse("runs.html", context)


@app.get("/compliance-runs", response_class=HTMLResponse)
def compliance_runs_page(request: Request) -> HTMLResponse:
    return runs_page(request)


@app.get("/reviews", response_class=HTMLResponse)
def reviews_page(request: Request) -> HTMLResponse:
    return runs_page(request)


@app.get("/files", response_class=HTMLResponse)
def files_page(request: Request) -> HTMLResponse:
    return documents_page(request)


@app.get("/files/preview")
def file_preview(path: str) -> JSONResponse:
    try:
        file_path = _preview_path_from_query(path)
    except Exception:
        return JSONResponse(content={"error": "Invalid path", "content": "", "type": "text"}, status_code=400)

    if not any(_is_within(root, file_path) for root in _allowed_preview_roots()):
        return JSONResponse(content={"error": "Access denied", "content": "", "type": "text"}, status_code=403)
    if not file_path.exists() or not file_path.is_file():
        return JSONResponse(content={"error": "File not found", "content": "", "type": "text"}, status_code=404)

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return JSONResponse(content={"error": str(exc), "content": "", "type": "text"}, status_code=500)

    extension = file_path.suffix.lower()
    payload: Dict[str, Any] = {
        "path": str(file_path.resolve().relative_to(BASE_DIR.resolve())),
        "size": len(content),
    }

    if extension == ".json":
        try:
            parsed = json.loads(content)
            payload.update({"type": "json", "content": json.dumps(parsed, indent=2)})
        except json.JSONDecodeError:
            payload.update({"type": "text", "content": content})
        return JSONResponse(content=payload)
    if extension == ".csv":
        payload.update({"type": "csv", "content": content})
        return JSONResponse(content=payload)
    if extension == ".md":
        payload.update({"type": "markdown", "content": content, "html": _simple_markdown_to_html(content)})
        return JSONResponse(content=payload)

    payload.update({"type": "text", "content": content})
    return JSONResponse(content=payload)


@app.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request) -> HTMLResponse:
    bundles = _all_run_bundles()
    run_rows = build_run_summaries(bundles)
    selected_scope = request.query_params.get("run")
    if not selected_scope and run_rows:
        selected_scope = run_rows[0]["scope"]

    selected_bundle = next((bundle for bundle in bundles if bundle.get("scope") == selected_scope), None)
    selected_run_activity: List[Dict[str, Any]] = []
    raw_activity_events: List[Dict[str, Any]] = []
    selected_run_title = None
    if selected_bundle:
        selected_run_title = _readable_run_title(selected_bundle.get("run_id", ""), selected_bundle.get("title", ""))
        audit_path = selected_bundle.get("artifacts", {}).get("audit_log")
        audit_log = _read_json(Path(audit_path)) if audit_path else []
        if not isinstance(audit_log, list):
            audit_log = []
        selected_run_activity = summarize_activity(audit_log, selected_bundle.get("planning_trace", []))
        raw_activity_events = _activity_feed([selected_bundle])

    context = _base_context(
        request,
        page_title="System Activity",
        hero_title="System Activity",
        hero_subtitle="A plain-language record of what the AI agent team did across compliance reviews.",
        active_nav="activity",
    )
    feed = _activity_feed(bundles)
    context["activity_feed"] = feed
    context["activity_stats"] = _activity_stats(feed)
    context["runs"] = run_rows
    context["selected_run"] = selected_scope
    context["selected_run_title"] = selected_run_title
    context["selected_run_activity"] = selected_run_activity
    context["raw_activity_events"] = raw_activity_events
    return templates.TemplateResponse("activity.html", context)


@app.get("/activity/{scope}/{event_index}", response_class=HTMLResponse)
def activity_detail_page(scope: str, event_index: int, request: Request) -> HTMLResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if event_index < 0 or event_index >= len(bundle["timeline"]):
        raise HTTPException(status_code=404, detail="Activity item not found.")

    event = bundle["timeline"][event_index]
    requirement = bundle["requirement_map"].get(event.get("requirement_id", ""))
    context = _base_context(
        request,
        page_title=event["title"],
        hero_title=event["title"],
        hero_subtitle=event["comment"],
        active_nav="activity",
    )
    context.update(
        {
            "run": bundle,
            "event": event,
            "related_requirement": requirement,
        }
    )
    return templates.TemplateResponse("activity_detail.html", context)


@app.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request) -> HTMLResponse:
    context = _base_context(
        request,
        page_title="Agent Team",
        hero_title="Agent Team",
        hero_subtitle="Meet the specialized AI agents and how they coordinate during document analysis.",
        active_nav="agents",
    )
    context["registry"] = _agent_registry_data()
    return templates.TemplateResponse("agents.html", context)


@app.get("/contracts/{contract_id}", response_class=HTMLResponse)
def contract_detail_page(request: Request, contract_id: str) -> HTMLResponse:
    from compliance_agent.contracts.tracker import STAGE_MAP, get_contract

    contract = get_contract(contract_id)
    if not contract:
        context = _base_context(
            request,
            page_title="Not Found",
            hero_title="Error",
            hero_subtitle="Requested contract could not be located.",
            active_nav="contracts",
        )
        context["message"] = "Contract not found"
        return templates.TemplateResponse("error.html", context, status_code=404)

    stage_info = STAGE_MAP.get(contract["stage"], {})
    run_bundle = None
    run_payload = None
    run_id = contract.get("run_id")
    if run_id:
        run_bundle = _load_bundle_for_scope(run_id)
        if run_bundle:
            run_bundle["requirements"] = _requirement_detail_rows(run_bundle)

        run_dir = Path("output/demo_cases") / run_id
        if not run_dir.exists() and run_bundle:
            run_dir = Path(run_bundle.get("output_dir", ""))
        if run_dir.exists():
            loaded_payload: Dict[str, Any] = {}
            for filename in [
                "compliance_decisions.json",
                "workflow_result.json",
                "qa_report.json",
                "compliance_report.md",
                "evidence_map.json",
            ]:
                file_path = run_dir / filename
                if not file_path.exists():
                    continue
                if file_path.suffix.lower() == ".json":
                    loaded_payload[file_path.stem] = _read_json(file_path)
                else:
                    loaded_payload[file_path.stem] = file_path.read_text(encoding="utf-8", errors="ignore")
            run_payload = loaded_payload or None

    context = _base_context(
        request,
        page_title=f"{contract['id']} — {contract['title']}",
        hero_title=contract["title"],
        hero_subtitle="Contract profile with stage history, status, and associated AI analysis.",
        active_nav="contracts",
    )
    context.update(
        {
            "contract": contract,
            "stage": stage_info,
            "run": run_payload,
            "run_bundle": run_bundle,
        }
    )
    return templates.TemplateResponse("contract_detail.html", context)


@app.get("/runs/{scope}", response_class=HTMLResponse)
def run_detail_page(scope: str, request: Request) -> HTMLResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run_dir = Path(bundle["output_dir"])
    requirements = _requirement_detail_rows(bundle)
    bundle["requirements"] = requirements

    confusion = {"labels": [], "rows": []}
    evaluation = bundle.get("evaluation") or {}
    confusion_matrix = evaluation.get("confusion_matrix", {}) if isinstance(evaluation, dict) else {}
    if confusion_matrix:
        labels = sorted(
            {
                *confusion_matrix.keys(),
                *{col for row in confusion_matrix.values() if isinstance(row, dict) for col in row.keys()},
            }
        )
        confusion["labels"] = labels
        confusion["rows"] = [
            {
                "label": row_label,
                "cells": [int(confusion_matrix.get(row_label, {}).get(col_label, 0)) for col_label in labels],
            }
            for row_label in labels
        ]

    context = _base_context(
        request,
        page_title=bundle["title"],
        hero_title=bundle["title"],
        hero_subtitle="A narrative view of what the AI team reviewed, what it found, and what needs attention.",
        active_nav="reviews",
    )
    review_flags_file = run_dir / "review_flags.json"
    review_flags = _read_json(review_flags_file) if review_flags_file.exists() else []
    if isinstance(review_flags, dict):
        review_flags = review_flags.get("flags", [])
    if not isinstance(review_flags, list):
        review_flags = []

    notes_file = run_dir / "stakeholder_notes.json"
    stakeholder_notes = _read_json(notes_file) if notes_file.exists() else []
    if not isinstance(stakeholder_notes, list):
        stakeholder_notes = []

    context["run"] = bundle
    context["confusion"] = confusion
    context["review_flags"] = review_flags[-8:]
    context["stakeholder_notes"] = stakeholder_notes[-12:]
    context["report_download_url"] = "/downloads/{}/compliance_report".format(bundle["scope"]) if "compliance_report" in bundle.get("artifacts", {}) else None
    context["matrix_download_url"] = "/downloads/{}/compliance_matrix".format(bundle["scope"]) if "compliance_matrix" in bundle.get("artifacts", {}) else None
    context["download_all_url"] = f"/runs/{bundle['scope']}/download-all"
    attention_items = [
        decision
        for decision in bundle["requirements"]
        if decision.get("label") in {"partial", "not_addressed", "not_compliant"}
    ]
    compliant_items = [decision for decision in bundle["requirements"] if decision.get("label") == "compliant"]
    context["attention_items"] = attention_items
    context["compliant_items"] = compliant_items
    context["attention_count"] = len(attention_items)
    context["compliant_count"] = len(compliant_items)
    context["partial_count"] = bundle.get("summary_cards", {}).get("partial", 0)
    context["not_addressed_count"] = bundle.get("summary_cards", {}).get("not_addressed", 0) + bundle.get("summary_cards", {}).get("not_compliant", 0)
    context["avg_confidence"] = bundle.get("summary_cards", {}).get("avg_confidence", 0.0)
    return templates.TemplateResponse("run_detail.html", context)


@app.get("/runs/{scope}/workflow", response_class=HTMLResponse)
def run_workflow_page(scope: str, request: Request) -> HTMLResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    audit_log = []
    if "audit_log" in bundle.get("artifacts", {}):
        audit_log = _read_json(Path(bundle["artifacts"]["audit_log"]))

    trimmed_audit_log = trim_audit_for_embed(audit_log)
    workflow_data = _build_workflow_visualization(trimmed_audit_log)
    context = _base_context(
        request,
        page_title=f"Agent Workflow — {bundle['title']}",
        hero_title="Agent Workflow",
        hero_subtitle="See how the orchestrator delegated work and how agents coordinated this review.",
        active_nav="reviews",
    )
    context["run"] = bundle
    context["workflow_data"] = workflow_data
    context["workflow_data_json"] = json.dumps(workflow_data, default=str)
    return templates.TemplateResponse("agent_workflow.html", context)


@app.get("/runs/{scope}/live", response_class=HTMLResponse)
def run_live_page(scope: str, request: Request) -> HTMLResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    context = _base_context(
        request,
        page_title=f"Run Replay — {bundle['title']}",
        hero_title=f"Run Replay: {bundle['run_id']}",
        hero_subtitle="Watch the digital team coordinate in sequence: planning decisions, delegation, skill usage, and results.",
        active_nav="reviews",
    )
    context["run"] = bundle
    context["scope"] = scope
    return templates.TemplateResponse("run_live.html", context)


@app.get("/run-live/{scope}")
def run_live_compat(scope: str) -> RedirectResponse:
    return RedirectResponse(url=f"/runs/{scope}/live", status_code=307)


@app.get("/runs/{scope}/events")
def get_run_events(scope: str) -> JSONResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    events: List[Dict[str, Any]] = []
    planning_trace = bundle.get("planning_trace", []) or []
    for step in planning_trace:
        action = str(step.get("action", "")).replace("dispatch_", "").replace("_", " ").title()
        if not action:
            action = _step_label(step.get("action", ""))
        events.append(
            {
                "type": "planning",
                "step": step.get("step"),
                "action": action,
                "reasoning": step.get("reasoning", ""),
                "planner_mode": step.get("planner_mode", "unknown"),
                "confidence": step.get("confidence_after", {}),
                "target_requirements": step.get("target_requirements", []),
                "timestamp": step.get("timestamp"),
            }
        )

    audit_path = bundle.get("artifacts", {}).get("audit_log")
    audit_log = _read_json(Path(audit_path)) if audit_path else []
    if not isinstance(audit_log, list):
        audit_log = []
    for entry in audit_log:
        msg_type = entry.get("type", "")
        sender = entry.get("sender", "")
        recipient = entry.get("recipient", "")
        payload = entry.get("payload", {}) or {}
        timestamp = entry.get("timestamp")

        if msg_type == "spawn":
            agent_id = payload.get("agent_id", recipient)
            events.append(
                {
                    "type": "agent_lifecycle",
                    "action": "spawn",
                    "agent": agent_id,
                    "role": payload.get("role", ""),
                    "description": f"Agent {agent_id} ({payload.get('role', 'worker')}) joined the team",
                    "timestamp": timestamp,
                }
            )
        elif msg_type == "terminate":
            agent_id = payload.get("agent_id", recipient)
            events.append(
                {
                    "type": "agent_lifecycle",
                    "action": "terminate",
                    "agent": agent_id,
                    "description": f"Agent {agent_id} completed and left",
                    "timestamp": timestamp,
                }
            )
        elif msg_type == "goal":
            events.append(
                {
                    "type": "delegation",
                    "sender": sender,
                    "recipient": recipient,
                    "description": f"{_humanize(sender)} delegated work to {_humanize(recipient)}",
                    "detail": str(payload.get("task", payload.get("goal", "")))[:240],
                    "timestamp": timestamp,
                }
            )
        elif msg_type == "result":
            detail = json.dumps(payload)[:240] if isinstance(payload, dict) else str(payload)[:240]
            events.append(
                {
                    "type": "result",
                    "sender": sender,
                    "recipient": recipient,
                    "description": f"{_humanize(sender)} reported results to {_humanize(recipient)}",
                    "detail": detail,
                    "timestamp": timestamp,
                }
            )
        elif msg_type == "tool_call":
            skill_name = payload.get("tool", payload.get("skill", recipient))
            events.append(
                {
                    "type": "skill_use",
                    "agent": sender,
                    "skill": skill_name,
                    "description": f"{_humanize(sender)} used skill: {skill_name}",
                    "timestamp": timestamp,
                }
            )
        elif msg_type == "tool_result":
            events.append(
                {
                    "type": "skill_result",
                    "agent": recipient,
                    "description": f"Skill completed for {_humanize(recipient)}",
                    "timestamp": timestamp,
                }
            )

    return JSONResponse(content={"events": events})


@app.post("/runs/{scope}/archive")
def archive_run(scope: str) -> RedirectResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    source = Path(bundle["output_dir"]).resolve()
    if not source.exists() or not source.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found.")
    if not _is_archivable_run_dir(source):
        raise HTTPException(status_code=400, detail="Only demo case runs can be archived.")

    archive_dir = source.parent / "_archived"
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / source.name
    if target.exists():
        target = archive_dir / f"{source.name}-{_now_stamp()}"
    shutil.move(str(source), str(target))
    return RedirectResponse(url="/", status_code=303)


@app.get("/runs/{scope}/download")
def download_run_zip(scope: str):
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run_dir = Path(bundle["output_dir"])
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory not found.")
    archive_base = Path(tempfile.gettempdir()) / f"{bundle['run_id']}-{uuid4().hex[:8]}"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=str(run_dir))
    return FileResponse(Path(archive_path), filename=f"{bundle['run_id']}.zip")


@app.get("/runs/{scope}/download-all")
def download_all_artifacts(scope: str):
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run_dir = Path(bundle["output_dir"])
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run directory not found.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(run_dir))
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={scope}_artifacts.zip"},
    )


@app.get("/runs/{scope}/audit-log")
def run_audit_log(scope: str) -> JSONResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    artifact_path = bundle.get("artifacts", {}).get("audit_log")
    if not artifact_path:
        raise HTTPException(status_code=404, detail="Audit log not found for this run.")
    return JSONResponse(content=_read_json(Path(artifact_path)))


@app.get("/workspace-files/view/{root_key}/{relative_path:path}", response_class=HTMLResponse)
def workspace_file_detail_page(root_key: str, relative_path: str, request: Request) -> HTMLResponse:
    file_path = _resolve_workspace_path(root_key, relative_path)
    preview = _file_preview_payload(file_path)
    context = _base_context(
        request,
        page_title=file_path.name,
        hero_title=file_path.name,
        hero_subtitle=str(file_path.resolve().relative_to(BASE_DIR.resolve())),
        active_nav="library",
    )
    context["workspace_file"] = {
        "name": file_path.name,
        "path": str(file_path),
        "relative_path": str(file_path.resolve().relative_to(BASE_DIR.resolve())),
        "root_key": root_key,
        "download_url": f"/workspace-files/download/{root_key}/{relative_path}",
        "can_delete": _is_within(BASE_DIR / "output", file_path) or _is_within(UPLOADS_DIR, file_path),
        "delete_url": f"/workspace-files/delete/{root_key}/{relative_path}",
    }
    context["preview"] = preview
    return templates.TemplateResponse("workspace_file_detail.html", context)


@app.get("/workspace-files/download/{root_key}/{relative_path:path}")
def workspace_file_download(root_key: str, relative_path: str):
    file_path = _resolve_workspace_path(root_key, relative_path)
    return FileResponse(file_path, filename=file_path.name)


@app.post("/workspace-files/delete/{root_key}/{relative_path:path}")
def workspace_file_delete(root_key: str, relative_path: str):
    file_path = _resolve_workspace_path(root_key, relative_path)
    if not (_is_within(BASE_DIR / "output", file_path) or _is_within(UPLOADS_DIR, file_path)):
        raise HTTPException(status_code=403, detail="Delete is only allowed in output/ and data/uploads/.")
    file_path.unlink(missing_ok=True)
    return RedirectResponse(url="/files", status_code=303)


@app.post("/files/clear-runs")
def clear_all_runs() -> RedirectResponse:
    for root in [config.DEMO_CASES_DIR, CUSTOM_RUNS_DIR]:
        if not root.exists():
            continue
        for directory in root.iterdir():
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)
    return RedirectResponse(url="/files", status_code=303)


@app.get("/files/view/{root_key}/{relative_path:path}", response_class=HTMLResponse)
def file_detail_page(root_key: str, relative_path: str, request: Request) -> HTMLResponse:
    file_path = _resolve_managed_path(root_key, relative_path)
    root_info = MANAGED_ROOTS[root_key]
    entry = _build_managed_file_entry(root_key, root_info, file_path)
    context = _base_context(
        request,
        page_title=entry["title"],
        hero_title=entry["title"],
        hero_subtitle=f"{entry['root_label']} · {entry['path_label']}",
        active_nav="library",
    )
    context["file_entry"] = entry
    return templates.TemplateResponse("file_detail.html", context)


@app.get("/files/download/{root_key}/{relative_path:path}")
def download_managed_file(root_key: str, relative_path: str):
    file_path = _resolve_managed_path(root_key, relative_path)
    return FileResponse(file_path, filename=file_path.name)


def _run_upload_context(request: Request, *, error: Optional[str] = None) -> Dict[str, Any]:
    from compliance_agent.contracts.library import CATEGORIES, get_library_tree, get_selectable_documents
    from compliance_agent.contracts.tracker import get_all_contracts

    documents = get_selectable_documents()
    company_categories = tuple(category for category in CATEGORIES if category != "opportunities")
    company_docs = [doc for doc in documents if doc["category"] in company_categories]
    opportunity_docs = [doc for doc in documents if doc["category"] == "opportunities"]

    default_selected: List[str] = []
    for document in company_docs:
        name = document["name"].lower()
        if any(
            term in name
            for term in [
                "capability_statement",
                "past_perf",
                "cpars",
                "resume",
                "certifications_matrix",
                "fedramp",
                "company_overview",
            ]
        ):
            default_selected.append(document["path"])

    context = _base_context(
        request,
        page_title="New Compliance Run",
        hero_title="Start Review",
        hero_subtitle="Upload the government solicitation, optionally attach your draft response, and select company context from the library.",
        active_nav="reviews",
    )
    context.update(
        {
            "company_docs": company_docs,
            "opportunity_docs": opportunity_docs,
            "default_selected": default_selected,
            "contracts": get_all_contracts(),
            "library_tree": get_library_tree(),
        }
    )
    if error:
        context["error"] = error
    return context


@app.get("/run-upload", response_class=HTMLResponse)
async def run_upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("run_upload.html", _run_upload_context(request))


@app.post("/run-demo")
def run_demo_case() -> RedirectResponse:
    meta = _run_default_demo_case()
    return RedirectResponse(url=f"/runs/{meta['run_id']}", status_code=303)


@app.post("/run-upload")
async def run_upload_submit(request: Request):
    from compliance_agent.contracts.library import upload_to_library

    form = await request.form()
    run_name = str(form.get("run_name", "")).strip()
    workflow_type = str(form.get("workflow_type", "compliance_review")).strip()
    contract_id = str(form.get("contract_id", "")).strip()

    source_path: Optional[str] = None
    response_path: Optional[str] = None
    context_paths: List[str] = []

    source_file = form.get("source_file") or form.get("source_document") or form.get("policy")
    source_library = str(form.get("source_library", "")).strip()

    if source_file and hasattr(source_file, "read") and getattr(source_file, "filename", ""):
        content = await source_file.read()
        saved = upload_to_library(content, source_file.filename, "opportunities", run_name or "uploads")
        source_path = str(saved)
    elif source_library and Path(source_library).exists():
        source_path = str(Path(source_library).resolve())

    response_file = form.get("response_file") or form.get("response_document") or form.get("response")
    response_library = str(form.get("response_library", "")).strip()

    if response_file and hasattr(response_file, "read") and getattr(response_file, "filename", ""):
        content = await response_file.read()
        saved = upload_to_library(content, response_file.filename, "opportunities", run_name or "uploads")
        response_path = str(saved)
    elif response_library and Path(response_library).exists():
        response_path = str(Path(response_library).resolve())

    for selected in form.getlist("context_docs"):
        selected_path = Path(str(selected))
        if selected_path.exists():
            resolved = str(selected_path.resolve())
            context_paths.append(resolved)

    if not source_path:
        return templates.TemplateResponse(
            "run_upload.html",
            _run_upload_context(request, error="Please upload or select a solicitation document."),
            status_code=400,
        )

    if not run_name:
        run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    run_id = slugify(run_name)
    output_dir = CUSTOM_RUNS_DIR / run_id
    if output_dir.exists():
        run_id = f"{run_id}-{uuid4().hex[:6]}"
        output_dir = CUSTOM_RUNS_DIR / run_id

    normalized_workflow = "proposal_drafting" if "draft" in workflow_type.lower() else "compliance_review"
    documents: List[Dict[str, Any]] = [
        {
            "path": source_path,
            "role": "solicitation_or_requirement_source",
            "label": "Source document",
        }
    ]
    if response_path:
        documents.append(
            {
                "path": response_path,
                "role": "response_or_proposal",
                "label": "Response document",
            }
        )
    for index, path in enumerate(context_paths, start=1):
        documents.append(
            {
                "path": path,
                "role": "prior_contract",
                "label": f"Context document {index}",
            }
        )

    title = run_name
    if contract_id:
        title = f"{run_name} ({contract_id})"

    _execute_run_in_background(
        run_id=run_id,
        title=title,
        workflow_type=normalized_workflow,
        documents=documents,
        output_dir=output_dir,
    )
    return RedirectResponse(url=f"/runs/{run_id}/progress", status_code=303)


@app.get("/runs/{scope}/progress", response_class=HTMLResponse)
async def run_progress_page(request: Request, scope: str):
    status = _get_run_status(scope)
    if status.get("status") == "complete":
        return RedirectResponse(url=f"/runs/{scope}", status_code=303)
    if status.get("status") == "not_found" and _load_bundle_for_scope(scope) is not None:
        return RedirectResponse(url=f"/runs/{scope}", status_code=303)

    context = _base_context(
        request,
        page_title=f"Run Progress · {scope}",
        hero_title="Run In Progress",
        hero_subtitle="Live stage updates from the agent team.",
        active_nav="reviews",
    )
    context.update(
        {
            "run_id": scope,
            "run_status": status,
        }
    )
    return templates.TemplateResponse("run_progress.html", context)


@app.get("/api/run-status/{scope}")
async def run_status_api(scope: str):
    status = _get_run_status(scope)
    if status.get("status") == "not_found" and _load_bundle_for_scope(scope) is not None:
        return {
            "status": "complete",
            "stage": "Done",
            "stages_completed": [
                "dispatch_intake",
                "dispatch_extraction",
                "dispatch_retrieval",
                "dispatch_compliance",
                "dispatch_qa",
                "finalize",
            ],
        }
    return status


@app.post("/runs/{scope}/notes")
async def add_stakeholder_note(request: Request, scope: str) -> RedirectResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    form = await request.form()
    note_text = str(form.get("note", "")).strip()
    if not note_text:
        return RedirectResponse(url=f"/runs/{scope}", status_code=303)

    run_dir = Path(bundle["output_dir"])
    notes_file = run_dir / "stakeholder_notes.json"
    notes = _read_json(notes_file) if notes_file.exists() else []
    if not isinstance(notes, list):
        notes = []
    notes.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "note": note_text,
        }
    )
    _write_json(notes_file, notes)
    return RedirectResponse(url=f"/runs/{scope}", status_code=303)


@app.post("/runs/{scope}/flag-review")
async def flag_requirements_for_review(request: Request, scope: str) -> RedirectResponse:
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    form = await request.form()
    requirement_ids = sorted({str(value) for value in form.getlist("requirement_ids") if str(value).strip()})
    if not requirement_ids:
        return RedirectResponse(url=f"/runs/{scope}", status_code=303)

    run_dir = Path(bundle["output_dir"])
    flags_file = run_dir / "review_flags.json"
    flags = _read_json(flags_file) if flags_file.exists() else []
    if isinstance(flags, dict):
        flags = flags.get("flags", [])
    if not isinstance(flags, list):
        flags = []
    flags.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "requirement_ids": requirement_ids,
        }
    )
    _write_json(flags_file, flags)
    return RedirectResponse(url=f"/runs/{scope}", status_code=303)


@app.get("/downloads/{scope}/{artifact}")
def download_artifact(scope: str, artifact: str):
    bundle = _load_bundle_for_scope(scope)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    path_str = bundle["artifacts"].get(artifact)
    if not path_str:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    path = Path(path_str)
    return FileResponse(path, filename=path.name)
