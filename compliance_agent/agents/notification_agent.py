"""Notification agent — monitors contracts, runs, and deadlines to generate alerts.

This agent scans the current system state and produces actionable notifications.
It runs on every dashboard page load (lightweight) and generates alerts based on:
- Contract deadlines approaching
- Compliance review results needing attention
- Performance SLA breaches
- Stale contracts with no recent activity
- System events (runs completed, new documents uploaded)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


agent_id: str = "notification_agent"

# Notification severity levels
SEVERITY_CRITICAL = "critical"  # Red — immediate action needed
SEVERITY_WARNING = "warning"  # Amber — attention soon
SEVERITY_INFO = "info"  # Blue — informational
SEVERITY_SUCCESS = "success"  # Green — positive update


def generate_notifications(contracts: list[dict], run_summaries: list[dict]) -> list[dict]:
    """Generate all notifications from current system state."""
    notifications: list[dict] = []
    today = date.today()

    for contract in contracts:
        # --- Deadline alerts ---
        due = _parse_date(contract.get("due_date"))
        if due:
            days_until = (due - today).days

            if days_until < 0:
                notifications.append({
                    "severity": SEVERITY_CRITICAL,
                    "category": "deadline",
                    "title": f"Overdue: {contract['title'][:60]}",
                    "message": (
                        f"Response was due {abs(days_until)} days ago ({contract['due_date']}). "
                        "Immediate action required."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/contracts/{contract['id']}",
                    "action_label": "View contract",
                    "timestamp": datetime.now().isoformat(),
                })
            elif days_until <= 5:
                notifications.append({
                    "severity": SEVERITY_CRITICAL,
                    "category": "deadline",
                    "title": f"Due in {days_until} days: {contract['title'][:60]}",
                    "message": (
                        f"Response deadline is {contract['due_date']}. Ensure proposal is finalized "
                        "and compliance review is complete."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/contracts/{contract['id']}",
                    "action_label": "View contract",
                    "timestamp": datetime.now().isoformat(),
                })
            elif days_until <= 14:
                notifications.append({
                    "severity": SEVERITY_WARNING,
                    "category": "deadline",
                    "title": f"Due in {days_until} days: {contract['title'][:60]}",
                    "message": (
                        f"Response deadline approaching ({contract['due_date']}). "
                        "Verify compliance review status."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/contracts/{contract['id']}",
                    "action_label": "View contract",
                    "timestamp": datetime.now().isoformat(),
                })

        # --- Compliance gap alerts ---
        run_data = contract.get("_run")
        if run_data:
            not_addressed = run_data.get("not_addressed", 0) or 0
            partial = run_data.get("partial", 0) or 0
            total = run_data.get("requirements", 0) or 0

            if not_addressed > 0:
                notifications.append({
                    "severity": SEVERITY_CRITICAL,
                    "category": "compliance",
                    "title": f"{not_addressed} requirements not addressed: {contract['title'][:50]}",
                    "message": (
                        f"The compliance review found {not_addressed} requirements completely "
                        "missing from the proposal. These must be addressed before submission."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/runs/{run_data['run_id']}",
                    "action_label": "See findings",
                    "timestamp": datetime.now().isoformat(),
                })

            if total and partial > total * 0.4:
                notifications.append({
                    "severity": SEVERITY_WARNING,
                    "category": "compliance",
                    "title": f"High gap rate ({partial}/{total}): {contract['title'][:50]}",
                    "message": (
                        f"{partial} of {total} requirements are only partially addressed. "
                        "Consider a reanalysis pass or proposal revision."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/runs/{run_data['run_id']}",
                    "action_label": "See findings",
                    "timestamp": datetime.now().isoformat(),
                })

            # Low confidence alert
            if run_data.get("confidence_mean") is not None and run_data["confidence_mean"] < 0.75:
                notifications.append({
                    "severity": SEVERITY_WARNING,
                    "category": "confidence",
                    "title": f"Low analysis confidence: {contract['title'][:50]}",
                    "message": (
                        f"Average confidence is {run_data['confidence_mean']:.0%}. Consider running "
                        "a targeted reanalysis or providing additional evidence documents."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/runs/{run_data['run_id']}",
                    "action_label": "See findings",
                    "timestamp": datetime.now().isoformat(),
                })

        # --- Solicitation without review ---
        if contract["stage"] == "solicitation" and not contract.get("run_id"):
            notifications.append({
                "severity": SEVERITY_WARNING,
                "category": "action_needed",
                "title": f"No compliance review started: {contract['title'][:50]}",
                "message": (
                    "This solicitation has documents ready but no agent review has been initiated. "
                    "Start a review to identify compliance gaps early."
                ),
                "contract_id": contract["id"],
                "action_url": "/run-upload",
                "action_label": "Start review",
                "timestamp": datetime.now().isoformat(),
            })

        # --- Performance alerts (active contracts) ---
        perf = contract.get("performance")
        if perf and contract["stage"] == "active":
            sla_metrics = perf.get("sla_metrics", [])
            for metric in sla_metrics:
                status = str(metric.get("status", "")).lower()
                if status in {"below", "missed"}:
                    notifications.append({
                        "severity": SEVERITY_CRITICAL,
                        "category": "performance",
                        "title": f"SLA breach: {metric['name']}",
                        "message": (
                            f"{metric['name']} is at {metric['actual']} against target of "
                            f"{metric['target']} on {contract['title'][:50]}."
                        ),
                        "contract_id": contract["id"],
                        "action_url": f"/contracts/{contract['id']}",
                        "action_label": "View performance",
                        "timestamp": datetime.now().isoformat(),
                    })

            # Staffing gap
            staffing = perf.get("staffing", {})
            filled = staffing.get("positions_filled", 0) or 0
            total_fte = staffing.get("total_fte", 0) or 0
            if total_fte and filled < total_fte:
                gap = total_fte - filled
                notifications.append({
                    "severity": SEVERITY_WARNING,
                    "category": "staffing",
                    "title": f"{gap} open position(s): {contract['title'][:50]}",
                    "message": (
                        f"{filled}/{total_fte} positions filled. Open roles may affect "
                        "delivery capacity."
                    ),
                    "contract_id": contract["id"],
                    "action_url": f"/contracts/{contract['id']}",
                    "action_label": "View details",
                    "timestamp": datetime.now().isoformat(),
                })

    # --- Run completion notifications ---
    for run in run_summaries:
        if run.get("accuracy") is not None and run["accuracy"] >= 0.9:
            notifications.append({
                "severity": SEVERITY_SUCCESS,
                "category": "run_complete",
                "title": f"Review complete with {run['accuracy']:.0%} accuracy",
                "message": (
                    f"Compliance review {run.get('readable_title', run['run_id'])} achieved "
                    f"{run['accuracy']:.0%} accuracy against ground truth."
                ),
                "action_url": f"/runs/{run['run_id']}",
                "action_label": "See findings",
                "timestamp": datetime.now().isoformat(),
            })

    # Sort: critical first, then warning, then info, then success
    severity_order = {
        SEVERITY_CRITICAL: 0,
        SEVERITY_WARNING: 1,
        SEVERITY_INFO: 2,
        SEVERITY_SUCCESS: 3,
    }
    notifications.sort(key=lambda item: severity_order.get(item["severity"], 99))

    return notifications


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Try to parse a date string. Returns None for non-date strings."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None

