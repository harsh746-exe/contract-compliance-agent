"""Chat assistant agent — answers stakeholder questions about contracts and analysis results.

Uses the LLM provider to answer questions grounded in the system's data.
The agent receives a question plus a context summary of current system state,
and produces a concise, helpful answer.
"""

from __future__ import annotations

import logging

from compliance_agent.llm import get_provider, provider_model_for_tier
from compliance_agent.llm.provider import LLMRequest

logger = logging.getLogger(__name__)

agent_id: str = "chat_agent"

SYSTEM_PROMPT = """You are an AI assistant embedded in a contract compliance management system for an IT services company. You help stakeholders understand:

- Contract pipeline status (what opportunities we're tracking, deadlines, stages)
- Compliance review results (which requirements are met, which have gaps, what to fix)
- Agent team activity (how the AI agents analyzed documents, what they found)
- Past performance records
- Document library contents

Answer questions concisely and helpfully. Reference specific contract IDs, requirement IDs, and numbers when relevant. If you don't have enough information to answer, say so clearly.

You are speaking to a government contracting professional who understands IT services, SOWs, SLAs, and proposal processes. Don't over-explain basic concepts.

Keep answers to 2-4 sentences unless the question requires more detail."""


def build_context_summary(contracts: list[dict], run_summaries: list[dict], notifications: list[dict]) -> str:
    """Build a concise text summary of current system state for the LLM context."""
    lines = ["CURRENT SYSTEM STATE\n"]

    lines.append(f"Total contracts: {len(contracts)}")
    by_stage: dict[str, list[dict]] = {}
    for contract in contracts:
        by_stage.setdefault(contract["stage"], []).append(contract)

    for stage, stage_contracts in by_stage.items():
        lines.append(f"\n{stage.upper()} ({len(stage_contracts)}):")
        for contract in stage_contracts:
            line = (
                f"  - {contract['id']}: {contract['title']} "
                f"({contract['agency']}, {contract['value']})"
            )
            if contract.get("due_date"):
                line += f" — due {contract['due_date']}"
            if contract.get("our_status"):
                line += f" — {contract['our_status']}"
            lines.append(line)

            run = contract.get("_run")
            if run:
                lines.append(
                    f"    Agent review: {run.get('requirements', '?')} requirements, "
                    f"{run.get('compliant', 0)} met, {run.get('partial', 0)} gaps, "
                    f"{run.get('not_addressed', 0)} missing. "
                    f"Confidence {run.get('confidence_min', '?')}–{run.get('confidence_max', '?')}."
                )

            perf = contract.get("performance")
            if perf and perf.get("sla_metrics"):
                metrics_summary = ", ".join(
                    f"{metric['name']}: {metric['actual']}" for metric in perf["sla_metrics"][:3]
                )
                lines.append(f"    Performance: {metrics_summary}")

    if run_summaries:
        lines.append(f"\nRECENT REVIEWS ({len(run_summaries)}):")
        for run in run_summaries[:5]:
            lines.append(
                f"  - {run.get('run_id')}: {run.get('requirements', 0)} requirements, "
                f"{run.get('compliant', 0)} compliant, {run.get('partial', 0)} partial, "
                f"{run.get('not_addressed', 0)} not addressed."
            )

    if notifications:
        lines.append(f"\nACTIVE NOTIFICATIONS ({len(notifications)}):")
        for notification in notifications[:5]:
            lines.append(
                f"  [{notification['severity']}] {notification['title']}: "
                f"{notification['message'][:100]}"
            )

    return "\n".join(lines)


async def answer_question(
    question: str,
    contracts: list[dict],
    run_summaries: list[dict],
    notifications: list[dict],
) -> str:
    """Answer a stakeholder question using LLM with system context."""
    context = build_context_summary(contracts, run_summaries, notifications)
    provider = get_provider()
    if not provider.is_available():
        return _fallback_answer(question, contracts, notifications)

    request = LLMRequest(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}\n\nQUESTION: {question}"},
        ],
        model=provider_model_for_tier("standard"),
        temperature=0.3,
        max_tokens=500,
    )

    try:
        response = await provider.complete(request)
        return response.content
    except Exception as exc:
        logger.error("Chat agent LLM failed: %s", exc)
        return _fallback_answer(question, contracts, notifications)


def _fallback_answer(question: str, contracts: list[dict], notifications: list[dict]) -> str:
    """Rule-based fallback when LLM is unavailable."""
    q = question.lower()

    if "deadline" in q or "due" in q or "upcoming" in q:
        upcoming = [
            contract
            for contract in contracts
            if contract.get("due_date") and contract["stage"] in ("solicitation", "review", "drafting")
        ]
        if upcoming:
            lines = ["Upcoming deadlines:"]
            for contract in sorted(upcoming, key=lambda item: item.get("due_date", "")):
                lines.append(f"- {contract['title'][:60]}: due {contract['due_date']}")
            return "\n".join(lines)
        return "No upcoming deadlines found for active opportunities."

    if "notification" in q or "alert" in q:
        if notifications:
            critical = [item for item in notifications if item["severity"] == "critical"]
            return (
                f"There are {len(notifications)} active notifications, "
                f"{len(critical)} of which are critical. Check the notification panel for details."
            )
        return "No active notifications at this time."

    for contract in contracts:
        title_prefix = str(contract.get("title", ""))[:20].lower()
        if contract["id"].lower() in q or (title_prefix and title_prefix in q):
            return (
                f"{contract['title']} ({contract['agency']}, {contract['value']}): "
                f"Currently in {contract['stage']} stage. {contract.get('our_status', '')}."
            )

    if "how many" in q and "contract" in q:
        return f"We are currently tracking {len(contracts)} contracts across all stages."

    return (
        "I can answer questions about contracts, compliance reviews, deadlines, and system activity. "
        "Could you be more specific about what you'd like to know?"
    )

