"""Main orchestration pipeline using LangGraph."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from .. import config
from ..agents.compliance_reasoner import ComplianceReasonerAgent
from ..agents.confidence_scorer import ConfidenceScorerAgent
from ..agents.evidence_retriever import EvidenceRetrieverAgent
from ..agents.requirement_classifier import RequirementClassifierAgent
from ..agents.requirement_extractor import RequirementExtractorAgent
from ..ingestion.chunking import chunk_text_by_size
from ..ingestion.document_parser import DocumentParser
from ..memory.persistent_store import ComplianceDecision, Evidence, PersistentStore, Requirement
from ..memory.working_memory import WorkingMemory
from ..output.matrix_generator import MatrixGenerator
from ..output.report_generator import ReportGenerator
from ..runtime import require_orchestration_runtime


class ComplianceState(TypedDict):
    """State object for the compliance pipeline."""

    policy_chunks: List[Dict[str, Any]]
    response_chunks: List[Dict[str, Any]]
    glossary_chunks: Optional[List[Dict[str, Any]]]
    requirements: List[Requirement]
    evidence_map: Dict[str, List[Evidence]]
    decisions: List[ComplianceDecision]
    review_queue: List[str]
    working_memory: WorkingMemory
    persistent_store: PersistentStore
    errors: List[str]
    retry_count: int
    _policy_path: str
    _response_path: str
    _glossary_path: Optional[str]
    _context_paths: List[str]


class ComplianceAgent:
    """Main compliance agent orchestrator."""

    def __init__(
        self,
        storage_path: Path = None,
        llm=None,
        vector_store_path: Path = None,
        document_parser=None,
        requirement_extractor=None,
        requirement_classifier=None,
        evidence_retriever=None,
        compliance_reasoner=None,
        confidence_scorer=None,
        persistent_store=None,
        matrix_generator=None,
        report_generator=None,
    ):
        """Initialize the compliance agent."""
        require_orchestration_runtime()

        self.document_parser = document_parser or DocumentParser()
        self.requirement_extractor = requirement_extractor or RequirementExtractorAgent(llm=llm)
        self.requirement_classifier = requirement_classifier or RequirementClassifierAgent(llm=llm)
        self.evidence_retriever = evidence_retriever or EvidenceRetrieverAgent(
            llm=llm,
            vector_store_path=vector_store_path,
        )
        self.compliance_reasoner = compliance_reasoner or ComplianceReasonerAgent(llm=llm)
        self.confidence_scorer = confidence_scorer or ConfidenceScorerAgent(llm=llm)

        self.persistent_store = persistent_store or PersistentStore(storage_path)
        self.matrix_generator = matrix_generator or MatrixGenerator()
        self.report_generator = report_generator or ReportGenerator()

        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the LangGraph pipeline."""
        from langgraph.graph import END, StateGraph

        workflow = StateGraph(ComplianceState)

        workflow.add_node("ingest_documents", self._ingest_documents)
        workflow.add_node("extract_requirements", self._extract_requirements)
        workflow.add_node("classify_requirements", self._classify_requirements)
        workflow.add_node("build_index", self._build_index)
        workflow.add_node("retrieve_evidence", self._retrieve_evidence)
        workflow.add_node("reason_compliance", self._reason_compliance)
        workflow.add_node("score_confidence", self._score_confidence)
        workflow.add_node("check_retry", self._check_retry)

        workflow.set_entry_point("ingest_documents")
        workflow.add_edge("ingest_documents", "extract_requirements")
        workflow.add_edge("extract_requirements", "classify_requirements")
        workflow.add_edge("classify_requirements", "build_index")
        workflow.add_edge("build_index", "retrieve_evidence")
        workflow.add_edge("retrieve_evidence", "reason_compliance")
        workflow.add_edge("reason_compliance", "score_confidence")
        workflow.add_conditional_edges(
            "score_confidence",
            self._should_retry,
            {"retry": "check_retry", "continue": END},
        )
        workflow.add_edge("check_retry", "retrieve_evidence")

        return workflow.compile()

    def process(
        self,
        policy_path: str,
        response_path: str,
        glossary_path: Optional[str] = None,
        context_paths: Optional[List[str]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process documents and generate a compliance matrix."""
        working_memory = WorkingMemory(run_id=run_id)

        initial_state: ComplianceState = {
            "policy_chunks": [],
            "response_chunks": [],
            "glossary_chunks": None,
            "requirements": [],
            "evidence_map": {},
            "decisions": [],
            "review_queue": [],
            "working_memory": working_memory,
            "persistent_store": self.persistent_store,
            "errors": [],
            "retry_count": 0,
        }
        initial_state["_policy_path"] = policy_path
        initial_state["_response_path"] = response_path
        initial_state["_glossary_path"] = glossary_path
        initial_state["_context_paths"] = context_paths or []

        try:
            final_state = self.graph.invoke(initial_state)
            effective_run_id = run_id or working_memory.run_id

            self.persistent_store.save_requirements(final_state["requirements"])
            all_evidence = [
                evidence
                for evidence_list in final_state["evidence_map"].values()
                for evidence in evidence_list
            ]
            self.persistent_store.save_evidence_batch(all_evidence)
            self.persistent_store.save_decisions(final_state["decisions"])

            if config.LOGS_DIR:
                working_memory.export_logs(config.LOGS_DIR / f"{effective_run_id}_logs.json")
                working_memory.export_summary(config.LOGS_DIR / f"{effective_run_id}_summary.json")

            return {
                "requirements": final_state["requirements"],
                "decisions": final_state["decisions"],
                "review_queue": final_state["review_queue"],
                "summary": working_memory.get_summary(),
                "run_id": effective_run_id,
            }
        except Exception as e:
            working_memory.log_error(f"Pipeline error: {e}")
            raise

    def _ingest_documents(self, state: ComplianceState) -> ComplianceState:
        """Ingest and chunk documents."""
        working_memory = state["working_memory"]
        start_time = time.time()

        try:
            policy_chunks = self.document_parser.parse(state["_policy_path"], doc_type="policy")
            policy_chunks_dict = [{
                "chunk_id": chunk.chunk_id,
                "doc_type": chunk.doc_type,
                "section_title": chunk.section_title,
                "page_range": chunk.page_range,
                "text": chunk.text,
                "metadata": chunk.metadata,
            } for chunk in policy_chunks]
            policy_chunks_dict = chunk_text_by_size(policy_chunks_dict)

            response_chunks = self.document_parser.parse(state["_response_path"], doc_type="response")
            response_chunks_dict = [{
                "chunk_id": chunk.chunk_id,
                "doc_type": chunk.doc_type,
                "section_title": chunk.section_title,
                "page_range": chunk.page_range,
                "text": chunk.text,
                "metadata": chunk.metadata,
            } for chunk in response_chunks]
            response_chunks_dict = chunk_text_by_size(response_chunks_dict)

            context_chunk_count = 0
            for context_path in state.get("_context_paths", []):
                context_chunks = self.document_parser.parse(context_path, doc_type="context")
                context_chunks_dict = [{
                    "chunk_id": chunk.chunk_id,
                    "doc_type": chunk.doc_type,
                    "section_title": chunk.section_title,
                    "page_range": chunk.page_range,
                    "text": chunk.text,
                    "metadata": {
                        **chunk.metadata,
                        "source_context_path": context_path,
                    },
                } for chunk in context_chunks]
                context_chunks_dict = chunk_text_by_size(context_chunks_dict)
                response_chunks_dict.extend(context_chunks_dict)
                context_chunk_count += len(context_chunks_dict)

            glossary_chunks_dict = None
            if state.get("_glossary_path"):
                glossary_chunks = self.document_parser.parse(state["_glossary_path"], doc_type="glossary")
                glossary_chunks_dict = [{
                    "chunk_id": chunk.chunk_id,
                    "doc_type": chunk.doc_type,
                    "section_title": chunk.section_title,
                    "page_range": chunk.page_range,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                } for chunk in glossary_chunks]

            duration = time.time() - start_time
            working_memory.log_agent_action(
                agent_name="ingestion",
                action="parse_documents",
                input_data={
                    "policy_path": state["_policy_path"],
                    "response_path": state["_response_path"],
                    "context_paths": state.get("_context_paths", []),
                },
                output_data={
                    "policy_chunks": len(policy_chunks_dict),
                    "response_chunks": len(response_chunks_dict),
                    "context_chunks": context_chunk_count,
                },
                duration_seconds=duration,
            )

            state["policy_chunks"] = policy_chunks_dict
            state["response_chunks"] = response_chunks_dict
            state["glossary_chunks"] = glossary_chunks_dict
        except Exception as e:
            working_memory.log_error(f"Ingestion error: {e}")
            state["errors"].append(str(e))

        return state

    def _extract_requirements(self, state: ComplianceState) -> ComplianceState:
        """Extract requirements from policy."""
        working_memory = state["working_memory"]

        try:
            state["requirements"] = self.requirement_extractor.extract(
                state["policy_chunks"],
                working_memory=working_memory,
            )
        except Exception as e:
            working_memory.log_error(f"Requirement extraction error: {e}")
            state["errors"].append(str(e))

        return state

    def _classify_requirements(self, state: ComplianceState) -> ComplianceState:
        """Classify requirements by category."""
        working_memory = state["working_memory"]

        try:
            state["requirements"] = self.requirement_classifier.classify(
                state["requirements"],
                working_memory=working_memory,
            )
        except Exception as e:
            working_memory.log_error(f"Classification error: {e}")
            state["errors"].append(str(e))

        return state

    def _build_index(self, state: ComplianceState) -> ComplianceState:
        """Build vector index from response document."""
        working_memory = state["working_memory"]
        start_time = time.time()

        try:
            self.evidence_retriever.build_index(state["response_chunks"])
            working_memory.log_agent_action(
                agent_name="evidence_retriever",
                action="build_index",
                input_data={"num_chunks": len(state["response_chunks"])},
                output_data={},
                duration_seconds=time.time() - start_time,
            )
        except Exception as e:
            working_memory.log_error(f"Index building error: {e}")
            state["errors"].append(str(e))

        return state

    def _retrieve_evidence(self, state: ComplianceState) -> ComplianceState:
        """Retrieve evidence for all requirements."""
        working_memory = state["working_memory"]
        requirements_to_process = state["requirements"]

        if state.get("retry_count", 0) > 0:
            low_confidence_reqs = [
                req for req in state["requirements"]
                if any(
                    dec.requirement_id == req.req_id and dec.confidence < config.CONFIDENCE_MEDIUM
                    for dec in state["decisions"]
                )
            ]
            if low_confidence_reqs:
                requirements_to_process = low_confidence_reqs

        evidence_map = state.get("evidence_map", {})

        for requirement in requirements_to_process:
            try:
                if state.get("retry_count", 0) > 0:
                    evidence_list = self.evidence_retriever.retrieve(
                        requirement,
                        top_k=config.TOP_K_RETRIEVAL * 2,
                        working_memory=working_memory,
                    )
                else:
                    evidence_list = self.evidence_retriever.retrieve(
                        requirement,
                        working_memory=working_memory,
                    )
                evidence_map[requirement.req_id] = evidence_list
            except Exception as e:
                working_memory.log_error(f"Evidence retrieval error for {requirement.req_id}: {e}")
                evidence_map[requirement.req_id] = []

        state["evidence_map"] = evidence_map
        return state

    def _reason_compliance(self, state: ComplianceState) -> ComplianceState:
        """Make compliance decisions."""
        working_memory = state["working_memory"]
        decisions = []

        for requirement in state["requirements"]:
            evidence_list = state["evidence_map"].get(requirement.req_id, [])
            try:
                decisions.append(self.compliance_reasoner.reason(
                    requirement,
                    evidence_list,
                    working_memory=working_memory,
                ))
            except Exception as e:
                working_memory.log_error(f"Reasoning error for {requirement.req_id}: {e}")
                decisions.append(ComplianceDecision(
                    requirement_id=requirement.req_id,
                    label="not_addressed",
                    confidence=0.0,
                    explanation=f"Error during reasoning: {e}",
                    evidence_chunk_ids=[],
                ))

        state["decisions"] = decisions
        return state

    def _score_confidence(self, state: ComplianceState) -> ComplianceState:
        """Score confidence and determine escalation."""
        working_memory = state["working_memory"]
        review_queue = []

        for decision in state["decisions"]:
            requirement = next(
                (r for r in state["requirements"] if r.req_id == decision.requirement_id),
                None,
            )
            if not requirement:
                continue

            evidence_list = state["evidence_map"].get(decision.requirement_id, [])
            try:
                scored_decision = self.confidence_scorer.score(
                    decision,
                    evidence_list,
                    working_memory=working_memory,
                )
                idx = next(
                    i for i, d in enumerate(state["decisions"])
                    if d.requirement_id == decision.requirement_id
                )
                state["decisions"][idx] = scored_decision
                if scored_decision.confidence < config.CONFIDENCE_HIGH:
                    review_queue.append(scored_decision.requirement_id)
            except Exception as e:
                working_memory.log_error(f"Confidence scoring error for {decision.requirement_id}: {e}")

        state["review_queue"] = list(set(review_queue))
        return state

    def _check_retry(self, state: ComplianceState) -> ComplianceState:
        """Check if retry is needed."""
        state["retry_count"] = state.get("retry_count", 0) + 1
        return state

    def _should_retry(self, state: ComplianceState) -> str:
        """Determine if retry is needed."""
        if state.get("retry_count", 0) >= config.MAX_RETRIES:
            return "continue"

        low_confidence = [
            dec for dec in state["decisions"]
            if dec.confidence < config.CONFIDENCE_MEDIUM
        ]

        if low_confidence and config.QUERY_EXPANSION_ENABLED:
            return "retry"

        return "continue"

    def export_matrix(self, output_path: str):
        """Export compliance matrix to CSV."""
        self.matrix_generator.generate_csv(
            self.persistent_store.load_requirements(),
            self.persistent_store.load_decisions(),
            self.persistent_store.load_evidence(),
            output_path,
        )

    def export_json(self, output_path: str):
        """Export results to JSON."""
        self.matrix_generator.generate_json(
            self.persistent_store.load_requirements(),
            self.persistent_store.load_decisions(),
            self.persistent_store.load_evidence(),
            output_path,
        )

    def export_report(self, output_path: str):
        """Export markdown report."""
        self.report_generator.generate_report(
            self.persistent_store.load_requirements(),
            self.persistent_store.load_decisions(),
            self.persistent_store.load_evidence(),
            output_path,
        )
