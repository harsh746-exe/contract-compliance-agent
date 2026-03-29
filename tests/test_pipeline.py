from pathlib import Path

from compliance_agent.ingestion.document_parser import DocumentChunk
from compliance_agent.memory.persistent_store import ComplianceDecision, Evidence, PersistentStore, Requirement
from compliance_agent.orchestration.pipeline import ComplianceAgent


class FakeParser:
    def parse(self, file_path: str, doc_type: str = "policy"):
        text = "The vendor shall provide monthly status reports." if doc_type == "policy" else "We provide monthly status reports."
        return [DocumentChunk(
            chunk_id=f"{doc_type}_chunk_1",
            doc_type=doc_type,
            section_title="Section 1",
            page_range="1-1",
            text=text,
            metadata={"file": file_path},
        )]


class FakeExtractor:
    def extract(self, policy_chunks, working_memory=None):
        return [Requirement(
            req_id="REQ_0001",
            requirement_text="The vendor shall provide monthly status reports.",
            source_citation="Section 1",
        )]


class FakeClassifier:
    def classify(self, requirements, working_memory=None):
        requirements[0].category = "reporting"
        return requirements


class FakeRetriever:
    def __init__(self):
        self.built = False

    def build_index(self, response_chunks):
        self.built = True
        self.response_chunks = response_chunks

    def retrieve(self, requirement, top_k=None, working_memory=None):
        return [Evidence(
            evidence_chunk_id="response_chunk_1",
            evidence_text="We provide monthly status reports.",
            evidence_citation="Section 1 1-1",
            retrieval_score=0.95,
            requirement_id=requirement.req_id,
        )]


class FakeReasoner:
    def reason(self, requirement, evidence_list, working_memory=None):
        return ComplianceDecision(
            requirement_id=requirement.req_id,
            label="compliant",
            confidence=0.82,
            explanation="Satisfied by response_chunk_1.",
            evidence_chunk_ids=[evidence_list[0].evidence_chunk_id],
        )


class FakeScorer:
    def score(self, decision, evidence_list, working_memory=None):
        decision.confidence = 0.9
        return decision


class RecordingMatrixGenerator:
    def __init__(self):
        self.csv_calls = []
        self.json_calls = []

    def generate_csv(self, requirements, decisions, evidence_list, output_path):
        self.csv_calls.append((requirements, decisions, evidence_list, output_path))

    def generate_json(self, requirements, decisions, evidence_list, output_path):
        self.json_calls.append((requirements, decisions, evidence_list, output_path))


class RecordingReportGenerator:
    def __init__(self):
        self.report_calls = []

    def generate_report(self, requirements, decisions, evidence_list, output_path):
        self.report_calls.append((requirements, decisions, evidence_list, output_path))


class SequentialGraph:
    def __init__(self, agent):
        self.agent = agent

    def invoke(self, state):
        for step in [
            self.agent._ingest_documents,
            self.agent._extract_requirements,
            self.agent._classify_requirements,
            self.agent._build_index,
            self.agent._retrieve_evidence,
            self.agent._reason_compliance,
            self.agent._score_confidence,
        ]:
            state = step(state)
        return state


def test_mocked_pipeline_run_and_export_wiring(monkeypatch, tmp_path):
    monkeypatch.setattr("compliance_agent.orchestration.pipeline.require_orchestration_runtime", lambda: None)
    monkeypatch.setattr(ComplianceAgent, "_build_graph", lambda self: SequentialGraph(self))

    store = PersistentStore(tmp_path / "store")
    matrix_generator = RecordingMatrixGenerator()
    report_generator = RecordingReportGenerator()

    agent = ComplianceAgent(
        document_parser=FakeParser(),
        requirement_extractor=FakeExtractor(),
        requirement_classifier=FakeClassifier(),
        evidence_retriever=FakeRetriever(),
        compliance_reasoner=FakeReasoner(),
        confidence_scorer=FakeScorer(),
        persistent_store=store,
        matrix_generator=matrix_generator,
        report_generator=report_generator,
    )

    policy_path = tmp_path / "policy.docx"
    response_path = tmp_path / "response.docx"
    policy_path.write_text("policy")
    response_path.write_text("response")

    results = agent.process(str(policy_path), str(response_path), run_id="test_run")

    assert results["run_id"] == "test_run"
    assert len(results["requirements"]) == 1
    assert results["decisions"][0].label == "compliant"
    assert store.load_evidence()[0]["evidence_chunk_id"] == "response_chunk_1"

    agent.export_matrix(str(tmp_path / "matrix.csv"))
    agent.export_json(str(tmp_path / "results.json"))
    agent.export_report(str(tmp_path / "report.md"))

    assert matrix_generator.csv_calls[0][0][0]["req_id"] == "REQ_0001"
    assert matrix_generator.json_calls[0][1][0]["label"] == "compliant"
    assert report_generator.report_calls[0][2][0]["evidence_chunk_id"] == "response_chunk_1"
