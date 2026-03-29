"""Compliance Reasoning Agent - makes compliance decisions with explanations."""

from typing import List

from .. import config
from ..memory.persistent_store import ComplianceDecision, Evidence, Requirement
from ..runtime import require_langchain_llm_runtime


def _build_chat_prompt_template():
    from langchain.prompts import ChatPromptTemplate

    return ChatPromptTemplate


def _build_default_llm():
    require_langchain_llm_runtime()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=0.1,
        api_key=config.OPENAI_API_KEY,
    )


class ComplianceReasonerAgent:
    """Makes compliance decisions based on requirements and evidence."""

    def __init__(self, llm=None):
        self.llm = llm or _build_default_llm()

        self.reasoning_prompt = _build_chat_prompt_template().from_messages([
            ("system", """You are an expert compliance analyst evaluating whether a response document satisfies policy requirements.

You must be strict and evidence-based. Do not invent compliance where it doesn't exist.

Decision Rubric:

1. **COMPLIANT**:
   - Evidence explicitly satisfies the requirement
   - All conditions are met
   - Specific details match (e.g., "monthly reports" means monthly, not quarterly)

2. **PARTIAL**:
   - Evidence is related but missing specific details
   - Some conditions met but not all
   - Vague or general statements without specifics
   - Example: Requirement asks for "monthly reports" but evidence only mentions "regular reports"

3. **NOT_ADDRESSED**:
   - No relevant evidence found
   - Evidence is completely unrelated
   - Requirement is not mentioned at all

4. **NOT_COMPLIANT**:
   - Evidence contradicts the requirement
   - Explicitly states non-compliance
   - Example: Requirement asks for encryption, evidence says "no encryption needed"

CRITICAL RULES:
- You MUST cite specific evidence chunk IDs in your explanation
- If evidence is weak or missing, mark as PARTIAL or NOT_ADDRESSED
- Do NOT mark as COMPLIANT unless evidence is explicit and complete
- Provide specific suggestions for improvement when not compliant or partial

Return JSON format with:
- label: one of compliant, partial, not_compliant, not_addressed
- explanation: detailed explanation citing evidence
- confidence: 0.0-1.0
- suggested_edits: list of specific suggestions (if not compliant or partial)"""),
            ("human", """Requirement:
{requirement_text}

Category: {category}
Conditions: {conditions}

Evidence:
{evidence_text}

Evidence Chunk IDs: {evidence_chunk_ids}

Make a compliance decision. Return JSON:
{{
  "label": "compliant|partial|not_compliant|not_addressed",
  "explanation": "Detailed explanation citing evidence chunks...",
  "confidence": 0.0-1.0,
  "suggested_edits": ["suggestion 1", "suggestion 2"]
}}"""),
        ])

    def reason(
        self,
        requirement: Requirement,
        evidence_list: List[Evidence],
        working_memory=None,
    ) -> ComplianceDecision:
        """Make a compliance decision for a requirement."""
        if not evidence_list:
            decision = ComplianceDecision(
                requirement_id=requirement.req_id,
                label="not_addressed",
                confidence=0.9,
                explanation="No evidence found in response document for this requirement.",
                evidence_chunk_ids=[],
                suggested_edits=["Add section addressing: " + requirement.requirement_text],
            )

            if working_memory:
                working_memory.log_agent_action(
                    agent_name="compliance_reasoner",
                    action="reason_compliance",
                    input_data={"requirement_id": requirement.req_id, "num_evidence": 0},
                    output_data={"label": decision.label, "confidence": decision.confidence},
                )

            return decision

        evidence_text = "\n\n---\n\n".join([
            f"[Chunk {ev.evidence_chunk_id}, Score: {ev.retrieval_score:.2f}]\n{ev.evidence_text[:500]}"
            for ev in evidence_list[:3]
        ])
        evidence_chunk_ids = [ev.evidence_chunk_id for ev in evidence_list]

        try:
            decision = self._reason_with_llm(
                requirement,
                evidence_text,
                evidence_chunk_ids,
                working_memory,
            )
        except Exception as e:
            if working_memory:
                working_memory.log_error(f"LLM reasoning error: {e}")
            decision = self._reason_with_rules(requirement, evidence_list)

        if working_memory:
            working_memory.log_agent_action(
                agent_name="compliance_reasoner",
                action="reason_compliance",
                input_data={
                    "requirement_id": requirement.req_id,
                    "num_evidence": len(evidence_list),
                },
                output_data={
                    "label": decision.label,
                    "confidence": decision.confidence,
                },
            )

        return decision

    def _reason_with_llm(
        self,
        requirement: Requirement,
        evidence_text: str,
        evidence_chunk_ids: List[str],
        working_memory=None,
    ) -> ComplianceDecision:
        """Use LLM for compliance reasoning."""
        response = self.llm.invoke(
            self.reasoning_prompt.format_messages(
                requirement_text=requirement.requirement_text,
                category=requirement.category or "unknown",
                conditions=requirement.conditions or "None",
                evidence_text=evidence_text,
                evidence_chunk_ids=", ".join(evidence_chunk_ids),
            )
        )

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        import json

        result = json.loads(content)
        label = result.get("label", "not_addressed").lower()
        if label not in config.COMPLIANCE_LABELS:
            label_mapping = {
                "compliant": "compliant",
                "partial": "partial",
                "not compliant": "not_compliant",
                "not_compliant": "not_compliant",
                "not addressed": "not_addressed",
                "not_addressed": "not_addressed",
            }
            label = label_mapping.get(label, "not_addressed")

        return ComplianceDecision(
            requirement_id=requirement.req_id,
            label=label,
            confidence=float(result.get("confidence", 0.5)),
            explanation=result.get("explanation", ""),
            evidence_chunk_ids=evidence_chunk_ids,
            suggested_edits=result.get("suggested_edits", []),
        )

    def _reason_with_rules(
        self,
        requirement: Requirement,
        evidence_list: List[Evidence],
    ) -> ComplianceDecision:
        """Fallback rule-based reasoning."""
        req_lower = requirement.requirement_text.lower()
        key_terms = set(req_lower.split())

        total_score = 0.0
        matched_chunks = []

        for ev in evidence_list:
            ev_lower = ev.evidence_text.lower()
            matches = sum(1 for term in key_terms if term in ev_lower and len(term) > 4)
            match_ratio = matches / len(key_terms) if key_terms else 0.0

            total_score += ev.retrieval_score * match_ratio
            if match_ratio > 0.3:
                matched_chunks.append(ev.evidence_chunk_id)

        avg_score = total_score / len(evidence_list) if evidence_list else 0.0

        if avg_score > 0.7 and matched_chunks:
            label = "compliant"
            confidence = min(0.8, avg_score)
        elif avg_score > 0.4:
            label = "partial"
            confidence = 0.6
        elif matched_chunks:
            label = "partial"
            confidence = 0.4
        else:
            label = "not_addressed"
            confidence = 0.7

        return ComplianceDecision(
            requirement_id=requirement.req_id,
            label=label,
            confidence=confidence,
            explanation=f"Rule-based decision. Match score: {avg_score:.2f}. Matched chunks: {matched_chunks}",
            evidence_chunk_ids=matched_chunks,
            suggested_edits=["Review evidence and provide explicit compliance statement."],
        )
