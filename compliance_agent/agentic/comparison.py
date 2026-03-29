"""Historical comparison worker for prior-context documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from ..ingestion.document_parser import DocumentParser
from ..runtime import require_langchain_llm_runtime


class HistoricalComparisonWorker:
    """Summarizes likely deltas and reuse opportunities across prior materials."""

    def __init__(self, parser: Optional[DocumentParser] = None, llm=None):
        self.parser = parser or DocumentParser()
        self.llm = llm

    def compare(self, primary_source_path: str, prior_context_paths: List[str]) -> Dict:
        """Compare the primary source document against prior-context materials."""
        source_text = self._load_text(primary_source_path)
        source_terms = self._important_terms(source_text)
        results = []

        for context_path in prior_context_paths:
            context_text = self._load_text(context_path)
            context_terms = self._important_terms(context_text)
            overlap = sorted(source_terms & context_terms)
            added = sorted(source_terms - context_terms)
            similarity = len(overlap) / max(len(source_terms), 1)
            results.append({
                "path": context_path,
                "similarity": round(similarity, 3),
                "reused_terms": overlap[:12],
                "new_terms": added[:12],
            })

        results.sort(key=lambda item: item["similarity"], reverse=True)
        summary = self._summarize(source_text, results)
        return {
            "documents": results,
            "summary": summary,
            "likely_impact_areas": self._impact_areas(results),
        }

    def _load_text(self, path_str: str) -> str:
        try:
            chunks = self.parser.parse(path_str, doc_type="context")
            return "\n".join(chunk.text for chunk in chunks)
        except Exception:
            return Path(path_str).read_text(encoding="utf-8", errors="ignore")

    def _important_terms(self, text: str) -> set[str]:
        words = re.findall(r"\b[a-z]{5,}\b", text.lower())
        stop_words = {"shall", "must", "therefore", "because", "which", "their", "these", "those"}
        return {word for word in words if word not in stop_words}

    def _summarize(self, source_text: str, results: List[Dict]) -> str:
        if self.llm is not None and results:
            summary = self._llm_summarize(source_text, results)
            if summary:
                return summary

        if not results:
            return "No prior-context documents were available for historical comparison."

        top = results[0]
        return (
            f"Compared the primary source against {len(results)} prior-context documents. "
            f"The closest prior match was {Path(top['path']).name} with similarity {top['similarity']:.2f}. "
            f"Likely reuse terms include {', '.join(top['reused_terms'][:5]) or 'none'}, "
            f"while likely new focus areas include {', '.join(top['new_terms'][:5]) or 'none'}."
        )

    def _llm_summarize(self, source_text: str, results: List[Dict]) -> Optional[str]:
        require_langchain_llm_runtime()
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", "Summarize the likely delta and reuse opportunities across prior context documents in 3-4 sentences."),
            ("human", "Source excerpt:\n{source}\n\nComparison results:\n{results}"),
        ])
        try:
            response = self.llm.invoke(prompt.format_messages(
                source=source_text[:1200],
                results=str(results[:3]),
            ))
            return response.content.strip()
        except Exception:
            return None

    def _impact_areas(self, results: List[Dict]) -> List[str]:
        if not results:
            return []
        impact_terms = []
        for result in results[:3]:
            impact_terms.extend(result["new_terms"][:4])
        return sorted(set(impact_terms))[:10]
