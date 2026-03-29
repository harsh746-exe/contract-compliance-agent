"""Scenario helpers for reproducible demo and evaluation runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import config
from .agentic import DOCUMENT_ROLES, DocumentInput


class DemoScenario(BaseModel):
    """Validated scenario manifest for demo-ready runs."""

    model_config = ConfigDict(extra="forbid")

    name: str
    mode: str
    goal: str
    output_subdir: Optional[str] = None
    evaluate_after_run: bool = False
    ground_truth_path: Optional[str] = None
    documents: List[DocumentInput] = Field(default_factory=list)

    @property
    def effective_output_subdir(self) -> str:
        return self.output_subdir or self.name


def load_scenario(scenario_dir: Path | str) -> DemoScenario:
    """Load and validate a scenario manifest plus its referenced files."""
    scenario_path = Path(scenario_dir)
    manifest_path = scenario_path / "scenario.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Scenario manifest not found: {manifest_path}")

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenario = DemoScenario.model_validate(payload)

    if scenario.mode not in {"linear", "agentic"}:
        raise ValueError(f"Unsupported scenario mode: {scenario.mode}")
    if not scenario.documents:
        raise ValueError("Scenario must define at least one document.")

    resolved_documents = []
    for document in scenario.documents:
        if document.role not in DOCUMENT_ROLES:
            raise ValueError(f"Unsupported document role in scenario: {document.role}")

        resolved_path = scenario_path / document.path
        if not resolved_path.exists():
            raise FileNotFoundError(f"Scenario document not found: {resolved_path}")

        resolved_documents.append(document.model_copy(update={"path": str(resolved_path.resolve())}))

    scenario = scenario.model_copy(update={"documents": resolved_documents})

    if _count_role(scenario.documents, "solicitation_or_requirement_source") != 1:
        raise ValueError("Scenario must include exactly one primary source document.")
    if _count_role(scenario.documents, "response_or_proposal") != 1:
        raise ValueError("Scenario must include exactly one primary response document.")

    if scenario.ground_truth_path:
        ground_truth = scenario_path / scenario.ground_truth_path
        if not ground_truth.exists():
            raise FileNotFoundError(f"Scenario ground truth not found: {ground_truth}")

    return scenario


def scenario_output_dir(scenario: DemoScenario, explicit_output_dir: Optional[str] = None) -> Path:
    """Resolve the stable output directory for a scenario run."""
    if explicit_output_dir:
        return Path(explicit_output_dir)
    return config.DEMO_CASES_DIR / scenario.effective_output_subdir


def scenario_ground_truth_path(scenario: DemoScenario, scenario_dir: Path | str) -> Optional[Path]:
    """Resolve the ground-truth path for a scenario when configured."""
    if not scenario.ground_truth_path:
        return None
    return Path(scenario_dir) / scenario.ground_truth_path


def extract_linear_inputs(documents: List[DocumentInput]) -> Dict[str, Optional[str]]:
    """Map scenario documents to the linear pipeline's path-based inputs."""
    policy = _first_path(documents, "solicitation_or_requirement_source")
    response = _first_path(documents, "response_or_proposal")
    glossary = _first_path(documents, "glossary")
    context = [
        document.path
        for document in documents
        if document.role in {"prior_proposal", "prior_contract", "amendment", "past_performance"}
    ]

    return {
        "policy": policy,
        "response": response,
        "glossary": glossary,
        "context": context,
    }


def materialize_agentic_artifacts(artifacts: Dict[str, str], output_dir: Path) -> Dict[str, str]:
    """Copy agentic artifacts into the stable scenario output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    materialized = {}

    for label, path_str in artifacts.items():
        source = Path(path_str)
        if not source.exists():
            continue
        destination = output_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        materialized[label] = str(destination)

    return materialized


def find_results_json(output_dir: Path, run_id: str) -> Path:
    """Locate the results JSON for evaluation within a scenario output directory."""
    exact = output_dir / f"{run_id}_results.json"
    if exact.exists():
        return exact

    matches = sorted(output_dir.glob("*_results.json"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"No results JSON found in scenario output directory: {output_dir}")


def _first_path(documents: List[DocumentInput], role: str) -> Optional[str]:
    for document in documents:
        if document.role == role:
            return document.path
    return None


def _count_role(documents: List[DocumentInput], role: str) -> int:
    return sum(1 for document in documents if document.role == role)
