"""Document routing for the agentic workflow."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..ingestion.document_parser import DocumentParser
from ..runtime import require_langchain_llm_runtime
from .models import DocumentInput, DocumentManifest


class DocumentRouter:
    """Assigns workflow roles to incoming documents."""

    def __init__(self, parser: Optional[DocumentParser] = None, llm=None):
        self.parser = parser or DocumentParser()
        self.llm = llm

    def route(self, documents: List[DocumentInput]) -> DocumentManifest:
        """Build a document manifest from user-supplied inputs."""
        manifest = DocumentManifest()

        for document in documents:
            routed = self._route_single_document(document)
            self._assign_to_manifest(manifest, routed)

        if not manifest.primary_source:
            manifest.ambiguous_documents.append("missing_primary_source")
            manifest.route_notes.append("Primary requirement/source document could not be inferred with confidence.")
        if not manifest.primary_response:
            manifest.ambiguous_documents.append("missing_primary_response")
            manifest.route_notes.append("Primary response/proposal document could not be inferred with confidence.")

        return manifest

    def _route_single_document(self, document: DocumentInput) -> DocumentInput:
        """Infer a role for one document."""
        if document.role != "unknown":
            return document

        guessed_role, confidence = self._heuristic_role(document.path)
        if guessed_role == "unknown":
            guessed_role, confidence = self._llm_role(document.path)

        document.role = guessed_role
        document.confidence = confidence
        document.metadata.setdefault("routed_from", "heuristic" if confidence < 0.95 else "explicit")
        return document

    def _heuristic_role(self, path_str: str) -> tuple[str, float]:
        """Use filenames and early text cues to infer the document role."""
        path = Path(path_str)
        name = path.name.lower()

        heuristic_map = {
            "glossary": ["glossary", "definitions", "acronym"],
            "amendment": ["amendment", "modification", "mod"],
            "prior_contract": ["contract", "agreement", "award"],
            "prior_proposal": ["prior_proposal", "old_proposal", "legacy_proposal"],
            "past_performance": ["past_performance", "reference", "experience"],
            "response_or_proposal": ["proposal", "response", "technical_volume", "implementation_plan"],
            "solicitation_or_requirement_source": ["solicitation", "rfp", "policy", "sow", "pws", "requirements"],
        }

        for role, markers in heuristic_map.items():
            if any(marker in name for marker in markers):
                return role, 0.9

        try:
            parsed = self.parser.parse(path_str, doc_type="policy")
            sample_text = " ".join(chunk.text[:200] for chunk in parsed[:2]).lower()
        except Exception:
            sample_text = ""

        if any(word in sample_text for word in ("shall", "must", "required", "statement of work", "solicitation")):
            return "solicitation_or_requirement_source", 0.65
        if any(word in sample_text for word in ("we will", "our approach", "proposal", "implementation")):
            return "response_or_proposal", 0.65
        if any(word in sample_text for word in ("definition", "terminology", "acronym")):
            return "glossary", 0.6

        return "unknown", 0.0

    def _llm_role(self, path_str: str) -> tuple[str, float]:
        """Use an LLM fallback for ambiguous routing when available."""
        if self.llm is None:
            return "unknown", 0.0

        require_langchain_llm_runtime()
        from langchain.prompts import ChatPromptTemplate

        try:
            parsed = self.parser.parse(path_str, doc_type="policy")
            sample_text = "\n".join(chunk.text[:300] for chunk in parsed[:2])
        except Exception:
            sample_text = ""

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Classify the document into one role:
- solicitation_or_requirement_source
- response_or_proposal
- glossary
- prior_proposal
- prior_contract
- amendment
- past_performance
- unknown

Return JSON with keys role and confidence."""),
            ("human", "Filename: {filename}\n\nText sample:\n{sample_text}"),
        ])

        try:
            response = self.llm.invoke(prompt.format_messages(
                filename=Path(path_str).name,
                sample_text=sample_text[:1500],
            ))
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json

            payload = json.loads(content)
            return payload.get("role", "unknown"), float(payload.get("confidence", 0.4))
        except Exception:
            return "unknown", 0.0

    def _assign_to_manifest(self, manifest: DocumentManifest, document: DocumentInput) -> None:
        """Place the routed document in the appropriate manifest bucket."""
        if document.role == "solicitation_or_requirement_source" and manifest.primary_source is None:
            manifest.primary_source = document
        elif document.role == "response_or_proposal" and manifest.primary_response is None:
            manifest.primary_response = document
        elif document.role == "glossary" and manifest.glossary is None:
            manifest.glossary = document
        elif document.role in {"prior_proposal", "prior_contract", "amendment", "past_performance"}:
            manifest.prior_context.append(document)
        else:
            manifest.unknown.append(document)

        if document.confidence < 0.6:
            manifest.ambiguous_documents.append(document.path)
            manifest.route_notes.append(
                f"Low-confidence routing for {Path(document.path).name}: {document.role} ({document.confidence:.2f})."
            )
