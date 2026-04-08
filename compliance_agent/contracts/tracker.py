"""Contract lifecycle tracker.

Manages the relationship between contracts and agent workflow runs.
In production, this would be backed by a database. For the prototype,
contracts are defined here and linked to actual agent run outputs.

Each contract represents a real-world government IT services opportunity
that moves through stages: forecast -> solicitation -> review -> drafting -> submitted -> active.
For contracts in the 'review' or 'drafting' stage, the agent team has performed
(or can perform) automated compliance analysis.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, timedelta
from typing import Optional


STAGES = [
    {"key": "forecast", "label": "Forecast", "description": "Identified opportunity, not yet solicited", "color": "#6366f1", "icon": "🔭"},
    {"key": "solicitation", "label": "Active Solicitation", "description": "RFI or RFP released, response being prepared", "color": "#3b82f6", "icon": "📋"},
    {"key": "review", "label": "Compliance Review", "description": "Agent team analyzing SOW against proposal", "color": "#f59e0b", "icon": "🔍"},
    {"key": "drafting", "label": "Proposal Drafting", "description": "Agent team drafting or refining proposal sections", "color": "#f97316", "icon": "✏️"},
    {"key": "submitted", "label": "Submitted", "description": "Proposal submitted, awaiting award decision", "color": "#64748b", "icon": "📤"},
    {"key": "active", "label": "Active Contract", "description": "Awarded and performing", "color": "#22c55e", "icon": "✅"},
    {"key": "completed", "label": "Completed", "description": "Contract complete, available as past performance", "color": "#94a3b8", "icon": "📁"},
]

STAGE_MAP = {s["key"]: s for s in STAGES}


CONTRACTS = [
    # ================================================================
    # FORECAST - Opportunities we're tracking, not yet solicited
    # ================================================================
    {
        "id": "CTR-2026-001",
        "title": "Medicare Current Beneficiary Survey (MCBS) - Cloud Modernization",
        "agency": "CMS / HHS",
        "solicitation": "HHS-CMS-RFI-2026-270043",
        "stage": "forecast",
        "value": "$45M / 5yr",
        "due_date": None,
        "naics": "541512",
        "summary": "RFI phase. CMS seeking industry input on hybrid cloud optimization across GCP and Azure environments, with emphasis on emerging tech integration for beneficiary data processing.",
        "our_status": "Monitoring - capture team assigned, white paper in development",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2026-03-10", "event": "RFI posted on SAM.gov"},
            {"date": "2026-03-15", "event": "Capture team assigned - lead: J. Morrison"},
            {"date": "2026-03-22", "event": "Industry day attended, notes captured"},
            {"date": "2026-04-01", "event": "White paper draft started"},
        ],
    },
    {
        "id": "CTR-2026-002",
        "title": "Commercial Satellite Communications (COMSATCOM) Services",
        "agency": "Space Force / DAF",
        "solicitation": "FA2541-26-003",
        "stage": "forecast",
        "value": "$120M / 7yr",
        "due_date": None,
        "naics": "517410",
        "summary": "2Q FY2026 forecast entry. Future requirements for satellite telecommunications, data processing, and ground segment modernization. Large IDIQ vehicle expected.",
        "our_status": "Tracking - teaming discussions with Northrop Grumman as potential prime",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2026-02-15", "event": "Identified in Space Force procurement forecast"},
            {"date": "2026-03-01", "event": "Teaming inquiry sent to 3 potential primes"},
            {"date": "2026-03-20", "event": "NDA signed with Northrop Grumman for teaming discussions"},
        ],
    },
    {
        "id": "CTR-2026-009",
        "title": "Hybrid Cloud Hosting Modernization",
        "agency": "CMS / HHS",
        "solicitation": "TBD",
        "stage": "forecast",
        "value": "$28M / 3yr",
        "due_date": None,
        "naics": "541519",
        "summary": "Early planning stage. CMS modernizing hosting environments to support AI-ready infrastructure by Summer 2026. Small business set-aside likely.",
        "our_status": "Capture planning - OAGM briefing scheduled May 2026",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2026-03-28", "event": "Opportunity identified through CMS industry liaison"},
            {"date": "2026-04-02", "event": "Added to capture pipeline, BD lead assigned"},
        ],
    },

    # ================================================================
    # ACTIVE SOLICITATION - RFI/RFP released, preparing response
    # ================================================================
    {
        "id": "CTR-2026-003",
        "title": "Network Operations Center (NOC) Managed Services",
        "agency": "VA / OIT",
        "solicitation": "36C10X26R0089",
        "stage": "solicitation",
        "value": "$32M / 5yr",
        "due_date": str(date.today() + timedelta(days=21)),
        "naics": "541513",
        "summary": "VA seeking 24/7 NOC monitoring, incident management, and capacity planning for nationwide health network infrastructure. Complex SOW with 22+ expected requirements covering SLA tiers, staffing, and FISMA compliance.",
        "our_status": "SOW received - compliance review kickoff scheduled",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2026-03-25", "event": "RFP posted on SAM.gov"},
            {"date": "2026-03-28", "event": "SOW downloaded and distributed to proposal team"},
            {"date": "2026-04-02", "event": "Kick-off meeting with proposal manager"},
            {"date": "2026-04-05", "event": "Compliance review agent run scheduled"},
        ],
    },

    # ================================================================
    # COMPLIANCE REVIEW - Agent team analyzing SOW against proposal
    # ================================================================
    {
        "id": "CTR-2026-004",
        "title": "Enterprise IT Support Services - OASIS+",
        "agency": "DOL / OASAM",
        "solicitation": "DOL-OASAM-26-R-0047",
        "stage": "review",
        "value": "$18M / 5yr",
        "due_date": str(date.today() + timedelta(days=12)),
        "naics": "541512",
        "summary": "Help desk (Tier 1-3), infrastructure monitoring, patch management, and SLA-driven operations support. Agent team completed full compliance review - 15 requirements analyzed across SLA, security, staffing, and transition domains.",
        "our_status": "Compliance review complete - 5 compliant, 7 partial, 3 gaps identified",
        "run_id": "it_services_compliance_02",
        "documents": [
            {"name": "sow_requirements.txt", "role": "SOW / Requirements Source"},
            {"name": "vendor_proposal.txt", "role": "Our Draft Proposal"},
        ],
        "history": [
            {"date": "2026-03-15", "event": "RFP released under OASIS+ SB Pool 1"},
            {"date": "2026-03-18", "event": "Proposal team assembled - 4 SMEs assigned"},
            {"date": "2026-03-22", "event": "SOW analysis started (manual)"},
            {"date": "2026-03-28", "event": "Draft proposal v1 completed"},
            {"date": "2026-04-02", "event": "Agent compliance review initiated - 8 agents deployed"},
            {"date": "2026-04-02", "event": "Intake agent parsed 2 documents, extraction agent identified 15 requirements"},
            {"date": "2026-04-02", "event": "Retrieval agent gathered evidence, compliance agent assessed all 15 requirements"},
            {"date": "2026-04-02", "event": "Orchestrator triggered reanalysis for low-confidence items"},
            {"date": "2026-04-02", "event": "QA agent approved - review complete in 8 planning steps"},
            {"date": "2026-04-05", "event": "Proposal team reviewing agent findings, addressing 3 gap areas"},
        ],
    },

    # ================================================================
    # PROPOSAL DRAFTING - Agent team generating/refining proposal
    # ================================================================
    {
        "id": "CTR-2026-005",
        "title": "IT Modernization Program Support",
        "agency": "Treasury / BFS",
        "solicitation": "2032H5-26-R-00015",
        "stage": "drafting",
        "value": "$22M / 4yr",
        "due_date": str(date.today() + timedelta(days=8)),
        "naics": "541512",
        "summary": "Cloud migration to AWS GovCloud, CI/CD pipeline implementation, zero-trust architecture, and staff augmentation. Agent team drafting proposal sections based on SOW requirements and prior contract performance data.",
        "our_status": "Proposal draft in progress - comparison with prior contract complete",
        "run_id": "draft_proposal_review",
        "documents": [
            {"name": "modernization_sow.txt", "role": "SOW / Requirements Source"},
            {"name": "prior_contract.txt", "role": "Prior Contract Reference"},
        ],
        "history": [
            {"date": "2026-03-10", "event": "RFP released"},
            {"date": "2026-03-15", "event": "Compliance review completed (separate run)"},
            {"date": "2026-03-20", "event": "Agent drafting workflow initiated"},
            {"date": "2026-03-20", "event": "Comparison agent analyzed prior contract for reusable content"},
            {"date": "2026-03-22", "event": "Drafting agent generated outline - 8 proposal sections"},
            {"date": "2026-03-25", "event": "QA agent reviewed draft - 2 sections flagged for revision"},
            {"date": "2026-04-01", "event": "Revised draft under human review"},
        ],
    },

    # ================================================================
    # SUBMITTED - Proposal sent, awaiting award decision
    # ================================================================
    {
        "id": "CTR-2026-006",
        "title": "Cybersecurity Operations Support",
        "agency": "DHS / CISA",
        "solicitation": "70RCSA26R00000012",
        "stage": "submitted",
        "value": "$55M / 5yr",
        "due_date": "Award expected May 2026",
        "naics": "541512",
        "summary": "SOC operations, threat hunting, vulnerability management, and FedRAMP compliance support. Agent compliance review achieved 100% accuracy against SME ground truth. Proposal submitted on time.",
        "our_status": "Submitted Mar 15 - awaiting award, debrief team on standby",
        "run_id": "compliance_review_case_01",
        "documents": [],
        "history": [
            {"date": "2026-01-20", "event": "RFP released"},
            {"date": "2026-02-01", "event": "Agent compliance review completed - 100% accuracy"},
            {"date": "2026-02-15", "event": "Proposal draft completed with agent assistance"},
            {"date": "2026-03-01", "event": "Final proposal review - color team approved"},
            {"date": "2026-03-15", "event": "Proposal submitted via eBuy"},
            {"date": "2026-03-20", "event": "Confirmation of receipt from CISA procurement"},
        ],
    },
    {
        "id": "CTR-2026-007",
        "title": "Federal Student Aid Systems O&M",
        "agency": "ED / FSA",
        "solicitation": "91990026R0003",
        "stage": "submitted",
        "value": "$42M / 5yr",
        "due_date": "Award expected June 2026",
        "naics": "541512",
        "summary": "Operations and maintenance for FAFSA processing systems. Linux/Oracle environment, FISMA High compliance, 99.9% uptime SLA. Submitted February 2026.",
        "our_status": "Submitted Feb 28 - past evaluation questions phase",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2025-11-15", "event": "RFP released"},
            {"date": "2025-12-10", "event": "Compliance review completed (manual + agent-assisted)"},
            {"date": "2026-01-20", "event": "Proposal draft completed"},
            {"date": "2026-02-28", "event": "Proposal submitted"},
            {"date": "2026-03-15", "event": "Evaluation questions received and answered"},
        ],
    },

    # ================================================================
    # ACTIVE CONTRACTS - Awarded and currently performing
    # ================================================================
    {
        "id": "CTR-2025-010",
        "title": "Enterprise Help Desk & End User Support",
        "agency": "DOI / IBC",
        "solicitation": "140D0423C0075",
        "stage": "active",
        "value": "$14M / 3yr + 2 OY",
        "due_date": "Awarded Nov 2025",
        "naics": "541512",
        "summary": "Tier 1-3 help desk operations serving 12,000+ users across DOI bureaus. ServiceNow ITSM platform, asset lifecycle management, VIP support queue, and monthly SLA reporting.",
        "our_status": "Performing - Option Year 1, all SLAs met",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2025-06-15", "event": "RFP released"},
            {"date": "2025-08-01", "event": "Agent compliance review - 12 requirements, 100% compliant"},
            {"date": "2025-09-15", "event": "Proposal submitted"},
            {"date": "2025-11-01", "event": "Award notification received"},
            {"date": "2025-11-15", "event": "Transition-in started (90-day plan)"},
            {"date": "2026-02-15", "event": "Full operational capability achieved"},
            {"date": "2026-03-31", "event": "Q1 FY2026 performance review - all metrics green"},
        ],
        "performance": {
            "sla_metrics": [
                {"name": "P1 Response Time", "target": "15 min", "actual": "11 min avg", "status": "met"},
                {"name": "P2 Response Time", "target": "1 hour", "actual": "38 min avg", "status": "met"},
                {"name": "P3 Response Time", "target": "4 hours", "actual": "2.1 hrs avg", "status": "met"},
                {"name": "First Call Resolution", "target": "70%", "actual": "78.3%", "status": "exceeded"},
                {"name": "System Availability", "target": "99.9%", "actual": "99.95%", "status": "exceeded"},
                {"name": "Customer Satisfaction", "target": "4.0/5", "actual": "4.6/5", "status": "exceeded"},
            ],
            "financials": {
                "base_value": 14000000,
                "invoiced_to_date": 5800000,
                "burn_rate": "On track",
                "option_years_exercised": 1,
                "option_years_remaining": 1,
            },
            "staffing": {
                "total_fte": 18,
                "positions_filled": 18,
                "key_personnel_stable": True,
                "turnover_rate": "5.5%",
            },
            "deliverables": {
                "monthly_reports": {"delivered": 5, "on_time": 5},
                "quarterly_reviews": {"delivered": 1, "on_time": 1},
                "incident_reports": {"delivered": 3, "on_time": 3},
            },
            "recent_highlights": [
                "Reduced P1 average response time from 14 min to 11 min through shift optimization",
                "Implemented self-service password reset - decreased Tier 1 ticket volume by 12%",
                "Achieved 99.95% ServiceNow platform uptime in Q1",
            ],
            "risks": [
                "Key personnel (Service Desk Manager) relocation planned Q3 - succession plan in progress",
            ],
        },
    },
    {
        "id": "CTR-2025-011",
        "title": "Data Center Consolidation & Cloud Migration",
        "agency": "USDA / OCIO",
        "solicitation": "12-3499-26-C-0012",
        "stage": "active",
        "value": "$38M / 5yr",
        "due_date": "Awarded Sep 2025",
        "naics": "541519",
        "summary": "Migrating 1,200 legacy workloads from 4 data centers to AWS GovCloud. FedRAMP High authorization maintained throughout. Currently in Phase 2 (migration execution).",
        "our_status": "Performing - 340/1,200 workloads migrated, Phase 2 on track",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2025-04-01", "event": "RFP released"},
            {"date": "2025-06-15", "event": "Agent compliance review - 18 requirements, 94% compliant"},
            {"date": "2025-07-01", "event": "Proposal submitted"},
            {"date": "2025-09-01", "event": "Award notification received"},
            {"date": "2025-10-01", "event": "Phase 1 (assessment & planning) started"},
            {"date": "2025-12-15", "event": "Phase 1 complete - migration runbooks for all 1,200 workloads"},
            {"date": "2026-01-15", "event": "Phase 2 (migration execution) started"},
            {"date": "2026-03-31", "event": "340 workloads migrated - on track for June milestone"},
        ],
        "performance": {
            "sla_metrics": [
                {"name": "Migration Success Rate", "target": "98%", "actual": "99.4%", "status": "exceeded"},
                {"name": "Zero-Downtime Migrations", "target": "95%", "actual": "97.1%", "status": "exceeded"},
                {"name": "Post-Migration Incidents", "target": "<5/month", "actual": "2.3/month avg", "status": "met"},
                {"name": "FedRAMP Compliance", "target": "100%", "actual": "100%", "status": "met"},
                {"name": "Customer Satisfaction", "target": "4.0/5", "actual": "4.8/5", "status": "exceeded"},
            ],
            "financials": {
                "base_value": 38000000,
                "invoiced_to_date": 12400000,
                "burn_rate": "On track",
                "option_years_exercised": 0,
                "option_years_remaining": 2,
            },
            "staffing": {
                "total_fte": 24,
                "positions_filled": 23,
                "key_personnel_stable": True,
                "turnover_rate": "4.2%",
                "open_positions": ["Senior Cloud Architect - recruiting in progress"],
            },
            "deliverables": {
                "migration_waves": {"planned": 12, "completed": 4, "on_time": 4},
                "monthly_dashboards": {"delivered": 6, "on_time": 6},
                "authorization_packages": {"delivered": 2, "on_time": 2},
            },
            "migration_progress": {
                "total_workloads": 1200,
                "migrated": 340,
                "in_progress": 85,
                "remaining": 775,
                "phases": [
                    {"name": "Phase 1: Assessment", "status": "complete", "workloads": 1200},
                    {"name": "Phase 2: Wave 1-4", "status": "complete", "workloads": 340},
                    {"name": "Phase 2: Wave 5-8", "status": "in_progress", "workloads": 360},
                    {"name": "Phase 2: Wave 9-12", "status": "planned", "workloads": 500},
                ],
            },
            "recent_highlights": [
                "Wave 4 completed ahead of schedule - 92 workloads migrated in 3 weeks",
                "Developed automated migration validation toolkit - reduced QA time by 40%",
                "Zero FedRAMP audit findings in March 2026 assessment",
            ],
            "risks": [
                "Senior Cloud Architect position open - mitigated by cross-training 2 junior engineers",
                "Wave 9 includes legacy Oracle databases requiring extended downtime windows",
            ],
        },
    },

    # ================================================================
    # COMPLETED - Past performance references
    # ================================================================
    {
        "id": "CTR-2024-005",
        "title": "IT Service Management Modernization",
        "agency": "SSA / DCBFM",
        "solicitation": "28-20-0005-SSA",
        "stage": "completed",
        "value": "$8.5M / 3yr",
        "due_date": "Completed Dec 2025",
        "naics": "541512",
        "summary": "Full ServiceNow implementation, ITIL process alignment, and automation of 45 manual workflows. Achieved Exceptional CPARS rating. Available as past performance reference for ITSM-related proposals.",
        "our_status": "Completed - Exceptional CPARS, reference available",
        "run_id": None,
        "documents": [],
        "history": [
            {"date": "2023-01-15", "event": "Contract awarded"},
            {"date": "2023-04-01", "event": "ServiceNow platform deployed"},
            {"date": "2023-09-01", "event": "Phase 1 complete - core ITSM modules live"},
            {"date": "2024-03-01", "event": "Phase 2 complete - 45 automated workflows"},
            {"date": "2024-09-01", "event": "Phase 3 complete - analytics and reporting dashboard"},
            {"date": "2025-12-15", "event": "Contract complete - Exceptional CPARS filed"},
        ],
        "performance": {
            "sla_metrics": [
                {"name": "System Availability", "target": "99.5%", "actual": "99.8%", "status": "exceeded"},
                {"name": "On-time Deliverables", "target": "95%", "actual": "100%", "status": "exceeded"},
                {"name": "Customer Satisfaction", "target": "4.0/5", "actual": "4.9/5", "status": "exceeded"},
                {"name": "Defect Rate", "target": "<2%", "actual": "0.8%", "status": "exceeded"},
            ],
            "cpars": {
                "overall": "Exceptional",
                "quality": "Exceptional",
                "schedule": "Exceptional",
                "cost_control": "Very Good",
                "management": "Exceptional",
                "small_business": "Satisfactory",
            },
            "outcomes": [
                "Reduced mean time to resolve incidents from 4.2 hours to 1.8 hours",
                "Automated 45 manual workflows - estimated $1.2M/year savings for SSA",
                "Trained 120 SSA staff on ServiceNow platform",
                "Zero unplanned outages during 3-year contract period",
            ],
        },
    },
]


def get_all_contracts() -> list[dict]:
    """Return all contracts."""
    return deepcopy(CONTRACTS)


def get_contract(contract_id: str) -> Optional[dict]:
    """Look up one contract by ID."""
    for contract in CONTRACTS:
        if contract["id"] == contract_id:
            return deepcopy(contract)
    return None


def get_contracts_by_stage(stage: str) -> list[dict]:
    """Return contracts in a specific stage."""
    return [deepcopy(contract) for contract in CONTRACTS if contract["stage"] == stage]


def get_pipeline_summary() -> dict:
    """Aggregate pipeline stats."""
    from collections import Counter

    counts = Counter(contract["stage"] for contract in CONTRACTS)
    total_value = 0.0
    for contract in CONTRACTS:
        match = re.search(r"\$(\d+(?:\.\d+)?)", contract.get("value", ""))
        if match:
            total_value += float(match.group(1))

    return {
        "total": len(CONTRACTS),
        "value_millions": round(total_value, 1),
        "by_stage": {stage["key"]: counts.get(stage["key"], 0) for stage in STAGES},
    }


def enrich_with_run_data(contracts: list[dict], run_summaries: list[dict]) -> list[dict]:
    """Attach agent run results to contracts that have a linked run_id."""
    run_map = {run["run_id"]: run for run in run_summaries}
    for contract in contracts:
        run_id = contract.get("run_id")
        contract["_run"] = run_map.get(run_id)
    return contracts
