"""Requirement Extraction Agent - extracts atomic requirements from policy documents."""

import re
from typing import Any, Dict, List

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


class RequirementExtractorAgent:
    """Extracts atomic requirements from policy/contract documents."""

    def __init__(self, llm=None):
        self.llm = llm or _build_default_llm()

        self.extraction_prompt = _build_chat_prompt_template().from_messages([
            ("system", """You are an expert at extracting requirements from policy and contract documents.

Your task is to identify atomic, actionable requirements from policy text.

A requirement is a statement that:
- Uses keywords like: shall, must, required, will, responsible for, ensure, provide, implement
- Specifies a concrete action or deliverable
- Can be verified independently

Rules:
1. Split compound requirements into separate atomic requirements
2. Preserve context and conditions (if, unless, within X days, etc.)
3. Extract the requirement text verbatim when possible
4. Note the source location (section, page)

Example:
Input: "The contractor shall provide monthly reports and conduct quarterly reviews"
Output:
- Requirement 1: "The contractor shall provide monthly reports"
- Requirement 2: "The contractor shall conduct quarterly reviews"

Return requirements in JSON format with fields: requirement_text, source_citation, conditions."""),
            ("human", """Extract requirements from the following policy text:

{policy_text}

Return a JSON array of requirements. Each requirement should have:
- requirement_text: the exact or paraphrased requirement
- source_citation: section/page reference
- conditions: any conditional clauses (if any)

JSON format:
[
  {{
    "requirement_text": "...",
    "source_citation": "...",
    "conditions": "..."
  }}
]"""),
        ])

    def extract(self, policy_chunks: List[Dict[str, Any]], working_memory=None) -> List[Requirement]:
        """Extract requirements from policy chunks."""
        all_requirements = []

        sections = self._group_by_section(policy_chunks)

        for section_title, chunks in sections.items():
            section_text = "\n\n".join([chunk.get("text", "") for chunk in chunks])
            citation = chunks[0].get("section_title", section_title) if chunks else section_title

            keyword_requirements = self._extract_by_keywords(section_text, citation)

            if section_text.strip():
                try:
                    llm_requirements = self._extract_with_llm(section_text, citation, working_memory)
                    all_requirements.extend(llm_requirements)
                except Exception as e:
                    if working_memory:
                        working_memory.log_error(f"LLM extraction failed for section {section_title}: {e}")
                    all_requirements.extend(keyword_requirements)
            else:
                all_requirements.extend(keyword_requirements)

        unique_requirements = self._deduplicate(all_requirements)

        for i, req in enumerate(unique_requirements):
            req.req_id = f"REQ_{i+1:04d}"

        if working_memory:
            working_memory.log_agent_action(
                agent_name="requirement_extractor",
                action="extract_requirements",
                input_data={"num_chunks": len(policy_chunks), "num_sections": len(sections)},
                output_data={"num_requirements": len(unique_requirements)},
            )

        return unique_requirements

    def _group_by_section(self, chunks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group chunks by section title."""
        sections: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in chunks:
            section = chunk.get("section_title", "Unknown")
            sections.setdefault(section, []).append(chunk)
        return sections

    def _extract_by_keywords(self, text: str, citation: str) -> List[Requirement]:
        """Extract requirements using keyword patterns."""
        requirements = []
        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if any(keyword in sentence.lower() for keyword in config.REQUIREMENT_KEYWORDS):
                conditions = None
                if re.search(r"\b(if|unless|when|within|after|before)\b", sentence, re.IGNORECASE):
                    conditions = sentence

                requirements.append(Requirement(
                    req_id="",
                    requirement_text=sentence,
                    source_citation=citation,
                    conditions=conditions,
                ))

        return requirements

    def _extract_with_llm(self, text: str, citation: str, working_memory=None) -> List[Requirement]:
        """Extract requirements using LLM."""
        max_length = 3000
        if len(text) > max_length:
            text = text[:max_length] + "..."

        try:
            response = self.llm.invoke(self.extraction_prompt.format_messages(policy_text=text))
            content = response.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json

            requirements_data = json.loads(content)

            return [
                Requirement(
                    req_id="",
                    requirement_text=req_data.get("requirement_text", ""),
                    source_citation=req_data.get("source_citation", citation),
                    conditions=req_data.get("conditions"),
                )
                for req_data in requirements_data
            ]
        except Exception as e:
            if working_memory:
                working_memory.log_error(f"LLM extraction error: {e}")
            return []

    def _deduplicate(self, requirements: List[Requirement]) -> List[Requirement]:
        """Remove duplicate requirements."""
        seen_texts = set()
        unique = []

        for req in requirements:
            normalized = req.requirement_text.lower().strip()
            normalized = re.sub(r"\s+", " ", normalized)

            if normalized not in seen_texts and len(normalized) > 10:
                seen_texts.add(normalized)
                unique.append(req)

        return unique
