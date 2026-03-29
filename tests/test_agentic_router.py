from compliance_agent.agentic.models import DocumentInput
from compliance_agent.agentic.router import DocumentRouter


def test_router_assigns_expected_roles_from_filenames():
    router = DocumentRouter()
    manifest = router.route([
        DocumentInput(path="client_rfp_policy.pdf"),
        DocumentInput(path="team_response_proposal.docx"),
        DocumentInput(path="contract_amendment.pdf"),
        DocumentInput(path="acronym_glossary.docx"),
    ])

    assert manifest.primary_source.role == "solicitation_or_requirement_source"
    assert manifest.primary_response.role == "response_or_proposal"
    assert manifest.glossary.role == "glossary"
    assert manifest.prior_context[0].role == "amendment"
