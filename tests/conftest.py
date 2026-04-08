from dataclasses import asdict
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from compliance_agent.memory.persistent_store import ComplianceDecision, Evidence, Requirement


@pytest.fixture
def requirement_objects():
    return [
        Requirement(
            req_id="REQ_0001",
            requirement_text="The vendor shall provide monthly status reports.",
            source_citation="Section 1",
            conditions=None,
            category="reporting",
        ),
        Requirement(
            req_id="REQ_0002",
            requirement_text="The vendor shall encrypt customer data at rest.",
            source_citation="Section 2",
            conditions=None,
            category="data_protection",
        ),
    ]


@pytest.fixture
def evidence_objects():
    return [
        Evidence(
            evidence_chunk_id="response_chunk_1",
            evidence_text="We will provide monthly status reports with metrics and milestones.",
            evidence_citation="Response A 1-1",
            retrieval_score=0.92,
            requirement_id="REQ_0001",
        ),
        Evidence(
            evidence_chunk_id="response_chunk_2",
            evidence_text="All customer data is encrypted at rest using AES-256.",
            evidence_citation="Response B 2-2",
            retrieval_score=0.88,
            requirement_id="REQ_0002",
        ),
    ]


@pytest.fixture
def decision_objects():
    return [
        ComplianceDecision(
            requirement_id="REQ_0001",
            label="compliant",
            confidence=0.91,
            explanation="Requirement is satisfied by response_chunk_1.",
            evidence_chunk_ids=["response_chunk_1"],
            suggested_edits=[],
            timestamp="2026-03-19T00:00:00",
        ),
        ComplianceDecision(
            requirement_id="REQ_0002",
            label="partial",
            confidence=0.61,
            explanation="Evidence addresses encryption but needs implementation detail.",
            evidence_chunk_ids=["response_chunk_2"],
            suggested_edits=["Specify the storage encryption controls."],
            timestamp="2026-03-19T00:00:01",
        ),
    ]


@pytest.fixture
def requirement_dicts(requirement_objects):
    return [asdict(req) for req in requirement_objects]


@pytest.fixture
def evidence_dicts(evidence_objects):
    return [asdict(ev) for ev in evidence_objects]


@pytest.fixture
def decision_dicts(decision_objects):
    return [asdict(dec) for dec in decision_objects]


@pytest.fixture
def agentic_text_documents(tmp_path):
    source = tmp_path / "sample_rfp_source.txt"
    response = tmp_path / "sample_response.txt"
    prior = tmp_path / "prior_contract.txt"

    source.write_text(
        "1. REQUIREMENTS\n"
        "The contractor shall provide monthly status reports. "
        "The contractor must maintain weekday support coverage from 6:00 AM to 8:00 PM Central Time."
    )
    response.write_text(
        "1. RESPONSE\n"
        "We provide monthly status reports to the client. "
        "Our support team operates from 6:00 AM to 8:00 PM Central Time on weekdays."
    )
    prior.write_text(
        "1. PRIOR CONTRACT\n"
        "The prior agreement required monthly reporting and business-hours support coverage."
    )

    return {
        "source": str(source),
        "response": str(response),
        "prior": str(prior),
    }
