"""Baseline comparison for compliance system."""

from typing import Dict, List

import config
from compliance_agent.ingestion.document_parser import DocumentParser
from compliance_agent.runtime import require_langchain_llm_runtime


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


class BaselineAgent:
    """Single-agent baseline that does everything in one prompt."""

    def __init__(self, llm=None):
        self.llm = llm or _build_default_llm()

        self.baseline_prompt = _build_chat_prompt_template().from_messages([
            ("system", """You are a compliance analyst. Analyze a policy document and a response document.

For each requirement in the policy, determine if the response is:
- compliant: explicitly satisfies requirement
- partial: related but missing specifics
- not_compliant: contradicts requirement
- not_addressed: no relevant content found

Return JSON array with requirement_id, requirement_text, label, explanation, confidence."""),
            ("human", """Policy Document:
{policy_text}

Response Document:
{response_text}

Analyze compliance and return JSON array of results."""),
        ])

    def process(self, policy_path: str, response_path: str) -> List[Dict]:
        """Process documents using single-agent baseline."""
        parser = DocumentParser()

        policy_chunks = parser.parse(policy_path, doc_type="policy")
        response_chunks = parser.parse(response_path, doc_type="response")

        policy_text = "\n\n".join([chunk.text for chunk in policy_chunks])[:8000]
        response_text = "\n\n".join([chunk.text for chunk in response_chunks])[:8000]

        response = self.llm.invoke(
            self.baseline_prompt.format_messages(
                policy_text=policy_text,
                response_text=response_text,
            )
        )

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        import json

        return json.loads(content)
