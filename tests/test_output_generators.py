import json

from compliance_agent.output.matrix_generator import MatrixGenerator
from compliance_agent.output.report_generator import ReportGenerator


def test_matrix_generator_outputs_csv_and_json(tmp_path, requirement_dicts, evidence_dicts, decision_dicts):
    generator = MatrixGenerator()
    csv_path = tmp_path / "results" / "matrix.csv"
    json_path = tmp_path / "results" / "results.json"

    generator.generate_csv(requirement_dicts, decision_dicts, evidence_dicts, str(csv_path))
    generator.generate_json(requirement_dicts, decision_dicts, evidence_dicts, str(json_path))

    csv_text = csv_path.read_text()
    json_payload = json.loads(json_path.read_text())

    assert "Requirement ID,Requirement Text,Category" in csv_text
    assert "REQ_0001" in csv_text
    assert json_payload["metadata"]["total_requirements"] == 2
    assert json_payload["requirements"][0]["decision"]["label"] in {"compliant", "partial"}


def test_report_generator_outputs_markdown(tmp_path, requirement_dicts, evidence_dicts, decision_dicts):
    generator = ReportGenerator()
    report_path = tmp_path / "results" / "report.md"

    generator.generate_report(requirement_dicts, decision_dicts, evidence_dicts, str(report_path))
    report_text = report_path.read_text()

    assert "# Compliance Report" in report_text
    assert "## Executive Summary" in report_text
    assert "#### ✅ Requirement REQ_0001" in report_text
    assert "## Items Requiring Review" in report_text
