"""Evidence Retrieval Agent - retrieves relevant evidence from response documents."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import config
from ..memory.persistent_store import Evidence, Requirement
from ..runtime import require_langchain_llm_runtime, require_retrieval_runtime


class SentenceTransformerEmbeddings:
    """LangChain-compatible wrapper for local sentence-transformer embeddings."""

    def __init__(self, model_name: str):
        require_retrieval_runtime()
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(text, convert_to_numpy=True).tolist()


class EvidenceRetrieverAgent:
    """Retrieves evidence from response documents for requirements."""

    def __init__(
        self,
        llm=None,
        vector_store_path: Path = None,
        embedding_backend=None,
        vector_store_factory: Optional[Callable[..., Any]] = None,
    ):
        if llm is None:
            require_langchain_llm_runtime()
            from langchain_openai import ChatOpenAI

            self.llm = ChatOpenAI(
                model=config.OPENAI_MODEL,
                temperature=0.1,
                api_key=config.OPENAI_API_KEY,
            )
        else:
            self.llm = llm

        self.embedding_model = embedding_backend or self._build_default_embedding_backend()
        self.vector_store_factory = vector_store_factory or self._build_default_vector_store_factory()
        self.vector_store_path = vector_store_path or config.VECTOR_STORE_PATH
        self.vector_store: Optional[Any] = None
        self.response_chunks: List[Dict[str, Any]] = []

    def _build_default_embedding_backend(self):
        """Create the configured embedding backend."""
        try:
            return SentenceTransformerEmbeddings(config.EMBEDDING_MODEL)
        except Exception:
            if config.OPENAI_API_KEY:
                require_retrieval_runtime()
                from langchain_openai import OpenAIEmbeddings

                return OpenAIEmbeddings(api_key=config.OPENAI_API_KEY)
            raise ValueError("No embedding model available")

    def _build_default_vector_store_factory(self) -> Callable[..., Any]:
        """Create the default vector store factory."""
        require_retrieval_runtime()
        from langchain.vectorstores import Chroma

        def factory(documents, embedding, persist_directory):
            return Chroma.from_documents(
                documents,
                embedding=embedding,
                persist_directory=persist_directory,
            )

        return factory

    def build_index(self, response_chunks: List[Dict[str, Any]]):
        """Build vector index from response document chunks."""
        require_retrieval_runtime()
        from langchain.schema import Document

        self.response_chunks = response_chunks

        documents = []
        for chunk in response_chunks:
            documents.append(Document(
                page_content=chunk.get("text", ""),
                metadata={
                    "chunk_id": chunk.get("chunk_id", ""),
                    "section_title": chunk.get("section_title", ""),
                    "page_range": chunk.get("page_range", ""),
                    **chunk.get("metadata", {}),
                },
            ))

        self.vector_store = self.vector_store_factory(
            documents,
            self.embedding_model,
            str(self.vector_store_path),
        )

    def retrieve(
        self,
        requirement: Requirement,
        top_k: int = None,
        working_memory=None,
    ) -> List[Evidence]:
        """Retrieve evidence for a requirement."""
        if top_k is None:
            top_k = config.TOP_K_RETRIEVAL

        if self.vector_store is None:
            raise ValueError("Vector store not built. Call build_index() first.")

        query = self._build_query(requirement)

        try:
            results = self.vector_store.similarity_search_with_score(query, k=top_k)

            evidence_list = []
            for doc, score in results:
                retrieval_score = 1.0 / (1.0 + score) if score > 0 else 1.0

                evidence_list.append(Evidence(
                    evidence_chunk_id=doc.metadata.get("chunk_id", ""),
                    evidence_text=doc.page_content,
                    evidence_citation=doc.metadata.get("section_title", "") + " " + doc.metadata.get("page_range", ""),
                    retrieval_score=retrieval_score,
                    requirement_id=requirement.req_id,
                ))

            keyword_evidence = self._keyword_search(requirement, top_k)
            evidence_list = self._merge_evidence(evidence_list, keyword_evidence)

            if working_memory:
                working_memory.log_agent_action(
                    agent_name="evidence_retriever",
                    action="retrieve_evidence",
                    input_data={
                        "requirement_id": requirement.req_id,
                        "requirement_text": requirement.requirement_text[:100],
                    },
                    output_data={
                        "num_evidence": len(evidence_list),
                        "top_score": evidence_list[0].retrieval_score if evidence_list else 0.0,
                    },
                )

            return evidence_list[:top_k]
        except Exception as e:
            if working_memory:
                working_memory.log_error(f"Evidence retrieval error: {e}")
            return []

    def _build_query(self, requirement: Requirement) -> str:
        """Build search query from requirement."""
        query_parts = [requirement.requirement_text]

        if requirement.category:
            category_keywords = {
                "obligations": "obligation duty responsibility",
                "deliverables": "deliverable artifact document output",
                "reporting": "report status notification update",
                "confidentiality": "confidential secret non-disclosure",
                "data_protection": "data privacy protection retention",
                "liability": "liability warranty damages",
                "payment": "payment invoice fee",
                "audit": "audit inspect review access",
                "termination": "terminate termination notice",
            }
            if requirement.category in category_keywords:
                query_parts.append(category_keywords[requirement.category])

        return " ".join(query_parts)

    def _keyword_search(self, requirement: Requirement, top_k: int) -> List[Evidence]:
        """Keyword-based search for exact term matches."""
        evidence_list = []
        key_terms = self._extract_key_terms(requirement.requirement_text)

        for chunk in self.response_chunks:
            chunk_text = chunk.get("text", "").lower()
            score = 0.0

            for term in key_terms:
                if term in chunk_text:
                    score += 1.0

            if score > 0:
                score = score / len(key_terms) if key_terms else 0.0
                evidence_list.append(Evidence(
                    evidence_chunk_id=chunk.get("chunk_id", ""),
                    evidence_text=chunk.get("text", ""),
                    evidence_citation=chunk.get("section_title", "") + " " + chunk.get("page_range", ""),
                    retrieval_score=score,
                    requirement_id=requirement.req_id,
                ))

        evidence_list.sort(key=lambda x: x.retrieval_score, reverse=True)
        return evidence_list[:top_k]

    def _extract_key_terms(self, text: str) -> List[str]:
        """Extract key terms from requirement text."""
        import re

        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
        stop_words = {"shall", "must", "will", "the", "and", "or", "for", "with", "that", "this"}
        key_terms = [w for w in words if w not in stop_words]
        return key_terms[:10]

    def _merge_evidence(self, vector_evidence: List[Evidence], keyword_evidence: List[Evidence]) -> List[Evidence]:
        """Merge and deduplicate evidence from different sources."""
        seen_ids = set()
        merged = []

        for ev in vector_evidence:
            if ev.evidence_chunk_id not in seen_ids:
                seen_ids.add(ev.evidence_chunk_id)
                merged.append(ev)

        for ev in keyword_evidence:
            if ev.evidence_chunk_id not in seen_ids:
                seen_ids.add(ev.evidence_chunk_id)
                ev.retrieval_score = min(1.0, ev.retrieval_score * 1.1)
                merged.append(ev)

        merged.sort(key=lambda x: x.retrieval_score, reverse=True)
        return merged
