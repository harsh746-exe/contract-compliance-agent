"""Persistent storage for requirements, evidence, and compliance decisions."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Requirement:
    """Represents an extracted requirement."""
    req_id: str
    requirement_text: str
    source_citation: str  # page, section
    conditions: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None


@dataclass
class Evidence:
    """Represents evidence retrieved for a requirement."""
    evidence_chunk_id: str
    evidence_text: str
    evidence_citation: str  # section, page
    retrieval_score: float
    requirement_id: str


@dataclass
class ComplianceDecision:
    """Represents a compliance decision for a requirement."""
    requirement_id: str
    label: str  # compliant, partial, not_compliant, not_addressed
    confidence: float
    explanation: str
    evidence_chunk_ids: List[str]
    suggested_edits: Optional[List[str]] = None
    timestamp: Optional[str] = None


class PersistentStore:
    """Manages persistent storage of requirements, evidence, and decisions."""
    
    def __init__(self, storage_path: Path = None):
        if storage_path is None:
            storage_path = Path("data/persistent_store")
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.requirements_file = self.storage_path / "requirements.json"
        self.evidence_file = self.storage_path / "evidence.json"
        self.decisions_file = self.storage_path / "decisions.json"
        
        # Initialize files if they don't exist
        self._initialize_files()
    
    def _initialize_files(self):
        """Create empty JSON files if they don't exist."""
        for file in [self.requirements_file, self.evidence_file, self.decisions_file]:
            if not file.exists():
                file.write_text(json.dumps([], indent=2))
    
    def save_requirement(self, requirement: Requirement):
        """Save a requirement."""
        requirements = self.load_requirements()
        requirements.append(asdict(requirement))
        self.requirements_file.write_text(json.dumps(requirements, indent=2))
    
    def save_requirements(self, requirements: List[Requirement]):
        """Save multiple requirements."""
        requirements_dict = [asdict(req) for req in requirements]
        self.requirements_file.write_text(json.dumps(requirements_dict, indent=2))
    
    def load_requirements(self) -> List[Dict]:
        """Load all requirements."""
        if not self.requirements_file.exists():
            return []
        return json.loads(self.requirements_file.read_text())
    
    def save_evidence(self, evidence: Evidence):
        """Save evidence for a requirement."""
        evidence_list = self.load_evidence()
        evidence_list.append(asdict(evidence))
        self.evidence_file.write_text(json.dumps(evidence_list, indent=2))
    
    def save_evidence_batch(self, evidence_list: List[Evidence]):
        """Save multiple evidence items."""
        evidence_dicts = [asdict(ev) for ev in evidence_list]
        self.evidence_file.write_text(json.dumps(evidence_dicts, indent=2))
    
    def load_evidence(self) -> List[Dict]:
        """Load all evidence."""
        if not self.evidence_file.exists():
            return []
        return json.loads(self.evidence_file.read_text())
    
    def get_evidence_for_requirement(self, requirement_id: str) -> List[Dict]:
        """Get all evidence for a specific requirement."""
        evidence_list = self.load_evidence()
        return [ev for ev in evidence_list if ev.get("requirement_id") == requirement_id]
    
    def save_decision(self, decision: ComplianceDecision):
        """Save a compliance decision."""
        if decision.timestamp is None:
            decision.timestamp = datetime.now().isoformat()
        
        decisions = self.load_decisions()
        decisions.append(asdict(decision))
        self.decisions_file.write_text(json.dumps(decisions, indent=2))
    
    def save_decisions(self, decisions: List[ComplianceDecision]):
        """Save multiple decisions."""
        for decision in decisions:
            if decision.timestamp is None:
                decision.timestamp = datetime.now().isoformat()
        
        decisions_dict = [asdict(dec) for dec in decisions]
        self.decisions_file.write_text(json.dumps(decisions_dict, indent=2))
    
    def load_decisions(self) -> List[Dict]:
        """Load all decisions."""
        if not self.decisions_file.exists():
            return []
        return json.loads(self.decisions_file.read_text())
    
    def get_decision_for_requirement(self, requirement_id: str) -> Optional[Dict]:
        """Get decision for a specific requirement."""
        decisions = self.load_decisions()
        for decision in decisions:
            if decision.get("requirement_id") == requirement_id:
                return decision
        return None
    
    def clear_all(self):
        """Clear all stored data (for testing/reset)."""
        for file in [self.requirements_file, self.evidence_file, self.decisions_file]:
            file.write_text(json.dumps([], indent=2))
