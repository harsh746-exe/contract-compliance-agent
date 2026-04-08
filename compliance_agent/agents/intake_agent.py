"""Document intake and routing agent."""

from __future__ import annotations

from pathlib import Path

from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class IntakeAgent(BaseAgent):
    """Parses incoming documents and routes them into workflow roles."""

    def __init__(self, agent_id: str = "intake_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="intake",
            description="Parses and routes incoming back-office documents.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="ingest_documents",
                description="Parse and route a batch of incoming documents.",
                input_schema={"documents": "list[str|dict]"},
                output_schema={"parsed_documents": "list[dict]", "all_chunks": "list[dict]"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "process_documents")
        if action not in {"process_documents", "ingest_documents", "classify_document"}:
            raise ValueError(f"Unsupported intake action: {action}")

        documents = goal.get("documents", [])
        parsed_documents = []
        all_chunks = []
        for document in documents:
            if isinstance(document, dict):
                path = document["path"]
                role = document.get("role") or self._infer_role(path)
            else:
                path = document
                role = self._infer_role(path)

            parsed = await self.use_skill("parse_document", file_path=path, doc_type=role)
            chunked = await self.use_skill("chunk_document", chunks=parsed["chunks"])
            parsed_documents.append({
                "path": path,
                "role": role,
                "chunks": chunked["chunks"],
                "metadata": parsed["metadata"],
            })
            all_chunks.extend([{**chunk, "role": role} for chunk in chunked["chunks"]])

        return {
            "parsed_documents": parsed_documents,
            "all_chunks": all_chunks,
            "document_manifest": self._build_manifest(parsed_documents),
        }

    def _infer_role(self, path: str) -> str:
        name = Path(path).name.lower()
        if any(marker in name for marker in ("rfp", "policy", "sow", "pws", "source", "requirements")):
            return "solicitation_or_requirement_source"
        if any(marker in name for marker in ("response", "proposal", "implementation")):
            return "response_or_proposal"
        if any(marker in name for marker in ("glossary", "definitions")):
            return "glossary"
        if any(marker in name for marker in ("prior", "contract", "amendment", "past_performance")):
            return "prior_contract"
        return "unknown"

    def _build_manifest(self, parsed_documents: list[dict]) -> dict:
        manifest = {
            "primary_source": None,
            "primary_response": None,
            "glossary": None,
            "prior_context": [],
            "unknown": [],
        }
        for document in parsed_documents:
            role = document["role"]
            if role == "solicitation_or_requirement_source" and manifest["primary_source"] is None:
                manifest["primary_source"] = document["path"]
            elif role == "response_or_proposal" and manifest["primary_response"] is None:
                manifest["primary_response"] = document["path"]
            elif role == "glossary" and manifest["glossary"] is None:
                manifest["glossary"] = document["path"]
            elif role in {"prior_contract", "prior_proposal", "amendment", "past_performance"}:
                manifest["prior_context"].append(document["path"])
            else:
                manifest["unknown"].append(document["path"])
        return manifest
