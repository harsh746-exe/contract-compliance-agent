"""Requirement Classifier Agent - tags requirements by category."""

from typing import List

from .. import config
from ..memory.persistent_store import Requirement
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


class RequirementClassifierAgent:
    """Classifies requirements into categories."""

    def __init__(self, llm=None):
        self.llm = llm or _build_default_llm()

        self.classification_prompt = _build_chat_prompt_template().from_messages([
            ("system", """You are an expert at categorizing requirements from contracts and policies. Work in a domain-agnostic way for any type of contract or policy.

Categories available (use the closest match):
- obligations: Duties, responsibilities, "shall" / "must" perform
- deliverables: Specific deliverables, artifacts, documents to produce
- reporting: Reports, status updates, notifications to provide
- confidentiality: Confidential information, non-disclosure, secrecy
- data_protection: Data handling, storage, privacy, personal data
- liability: Liability limits, warranties, disclaimers
- indemnity: Indemnification, hold harmless
- insurance: Insurance requirements, coverage
- termination: Termination rights, exit, notice periods
- dispute_resolution: Arbitration, mediation, governing law
- payment: Payment terms, invoicing
- fees: Fees, costs, charges
- audit: Audit rights, inspection, access
- documentation: Documentation to maintain or provide
- timelines: Deadlines, milestones, duration
- compliance: General compliance, regulatory adherence

Return the most relevant category (primary) and optionally a secondary category.
Return JSON format with: category, subcategory (optional), confidence."""),
            ("human", """Classify the following requirement:

{requirement_text}

Return JSON:
{{
  "category": "primary_category",
  "subcategory": "optional_subcategory",
  "confidence": 0.0-1.0
}}"""),
        ])

    def classify(self, requirements: List[Requirement], working_memory=None) -> List[Requirement]:
        """Classify requirements into categories."""
        classified = []

        for req in requirements:
            category = self._classify_single(req.requirement_text, working_memory)
            req.category = category
            classified.append(req)

        if working_memory:
            category_distribution = {}
            for req in classified:
                cat = req.category or "unknown"
                category_distribution[cat] = category_distribution.get(cat, 0) + 1

            working_memory.log_agent_action(
                agent_name="requirement_classifier",
                action="classify_requirements",
                input_data={"num_requirements": len(requirements)},
                output_data={"category_distribution": category_distribution},
            )

        return classified

    def _classify_single(self, requirement_text: str, working_memory=None) -> str:
        """Classify a single requirement."""
        category = self._classify_by_keywords(requirement_text)

        if category == "unknown" or len(requirement_text) > 200:
            try:
                category = self._classify_with_llm(requirement_text, working_memory)
            except Exception as e:
                if working_memory:
                    working_memory.log_error(f"LLM classification error: {e}")

        return category

    def _classify_by_keywords(self, text: str) -> str:
        """Quick keyword-based classification."""
        text_lower = text.lower()

        keyword_mapping = {
            "obligations": ["shall", "must", "will", "responsible", "ensure", "maintain", "provide"],
            "deliverables": ["deliverable", "deliver", "artifact", "document", "output", "work product"],
            "reporting": ["report", "notify", "notification", "status", "quarterly", "monthly", "update"],
            "confidentiality": ["confidential", "non-disclosure", "nda", "secret", "proprietary"],
            "data_protection": ["data", "privacy", "personal data", "pii", "retention", "storage", "process"],
            "liability": ["liability", "warranty", "disclaimer", "limitation", "damages"],
            "indemnity": ["indemnify", "indemnity", "hold harmless"],
            "insurance": ["insurance", "coverage", "policy", "insured"],
            "termination": ["terminate", "termination", "expire", "notice period", "cancel"],
            "dispute_resolution": ["arbitration", "mediation", "governing law", "jurisdiction", "dispute"],
            "payment": ["payment", "pay", "invoice", "remit", "due date"],
            "fees": ["fee", "fees", "cost", "charge", "price"],
            "audit": ["audit", "inspect", "inspection", "access", "review"],
            "documentation": ["documentation", "document", "record", "maintain", "manual"],
            "timelines": ["deadline", "milestone", "duration", "within", "days", "weeks", "schedule"],
            "compliance": ["compliance", "comply", "regulatory", "law", "regulation"],
        }

        for category, keywords in keyword_mapping.items():
            if any(keyword in text_lower for keyword in keywords):
                return category

        return "unknown"

    def _classify_with_llm(self, text: str, working_memory=None) -> str:
        """Classify using LLM."""
        try:
            response = self.llm.invoke(self.classification_prompt.format_messages(requirement_text=text))
            content = response.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json

            result = json.loads(content)
            return result.get("category", "unknown")
        except Exception as e:
            if working_memory:
                working_memory.log_error(f"LLM classification failed: {e}")
            return "unknown"
