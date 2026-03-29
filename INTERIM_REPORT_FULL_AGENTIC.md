# Interim Report

## Project Title

**Agentic AI Workflow for IT Services Document Processing, Compliance Review, and Proposal Drafting**

## Team

Harsh Dwivedi  
Krish Alpeshbhai Mangukiya  
Srikanth Menda  
Yash Jadhav

## Reporting Period

**Project start:** approximately the third week of January 2026  
**Interim report date:** March 20, 2026

## 1. Executive Summary

This interim report presents the current progress of our project, *Agentic AI Workflow for IT Services Document Processing, Compliance Review, and Proposal Drafting*. From the beginning, the project has been conceived as a bounded agentic workflow for IT services organizations that repeatedly work with RFPs, SOWs, PWS documents, contracts, amendments, prior proposals, past performance records, and compliance-oriented submission materials. The purpose of the system is not merely to analyze documents one by one, but to interpret a document-centered objective, identify what type of workflow is required, assemble the right context, route work to specialized agents, and return decision-ready outputs that can support actual proposal and compliance operations [1][2][3].

The architecture is based on a real distinction between a worker layer and a control layer. The worker layer performs document parsing, extraction, retrieval, reasoning, comparison, drafting, and validation tasks. The control layer plans the next step, tracks workflow state, decides when to branch, determines when bounded retries are justified, and pauses for human approval when risk or ambiguity crosses a defined threshold. This design is central to the project because it makes the system meaningfully agentic rather than a conventional rule-based automation script [1][2][20].

At the time of this interim report, we estimate that the project is approximately **70% complete**. Most of the major technical building blocks are already in place, including parsing, chunking, requirement extraction, classification, retrieval, compliance reasoning, confidence scoring, persistence, reporting, evaluation support, and the bounded control-plane concepts needed for planning, routing, and approval-aware execution. The remaining work is concentrated in final integration, workflow-level validation, and demonstration of the full end-to-end agentic loop.

## 2. Project Aim and Scope

The main aim of the project is to design and implement a bounded agentic AI workflow that supports document understanding, compliance-oriented analysis, historical document comparison, and proposal drafting assistance for an IT services organization. A central design principle from the outset has been that the system should not only interpret documents, but also plan the next action, select the correct workflow branch, preserve state across stages, and escalate uncertain outcomes to a human reviewer rather than silently guessing.

Within this scope, the system is intended to support three connected operational workflows. The first is **document intake and routing**, where incoming files are identified and assigned roles such as solicitation or requirement source, response or proposal, glossary, prior proposal, prior contract, amendment, or past performance. The second is **historical comparison and compliance-oriented analysis**, where a new document can be evaluated against relevant prior material and summarized in a form that reduces manual side-by-side review. The third is **proposal drafting support**, where extracted requirements and retrieved prior context are used to generate a first-pass outline or response draft, evaluate its quality, and revise it before handoff.

The project is therefore not limited to basic two-document comparison. It is designed as a reusable agentic workflow for IT services proposal and contract operations, with a compliance-centered first slice and bounded drafting and comparison branches built on the same architecture.

## 3. Technical Approach and System Design

From a technical standpoint, the system is implemented in Python and organized into layers for ingestion, agent modules, orchestration, memory, output generation, evaluation, and workflow state persistence. Architecturally, we view the system as having two cooperating planes. The execution plane performs concrete tasks such as document parsing, requirement extraction, retrieval, reasoning, comparison, and drafting. The control plane manages goal interpretation, bounded planning, task sequencing, evaluator-driven branching, approval checkpoints, and final handoff behavior.

The current implementation uses `LangGraph 0.0.20` to orchestrate multi-step workflow execution and `LangChain 0.1.0` with `langchain-openai 0.0.5` for LLM-backed agent behavior. The default LLM path uses `ChatOpenAI` with the configured model `gpt-4-turbo-preview`. For retrieval, the system uses `ChromaDB 0.4.22` together with `sentence-transformers 2.3.1` and the embedding model `sentence-transformers/all-MiniLM-L6-v2`. For document parsing, the implementation uses `pdfplumber 0.10.3` and `PyPDF2 3.0.1` for PDF handling, `python-docx 1.1.0` for Word documents, and `scikit-learn 1.4.0` for evaluation metrics [1][4][5][17][18].

The bounded agentic design is expressed through a fixed action vocabulary at the control layer. Instead of allowing an unconstrained planner to perform arbitrary operations, the planner selects from approved workflow actions such as `route_documents`, `prepare_context`, `run_compliance_pipeline`, `reanalyze_low_confidence`, `compare_with_prior_context`, `draft_response_outline`, `evaluate_draft`, `rewrite_draft`, `request_human_approval`, `finalize_outputs`, and `stop_with_error`. This gives the system bounded autonomy: it can plan and adapt, but only within an explicit operational envelope.

The current worker backbone is organized around a reusable pipeline of `ingest_documents`, `extract_requirements`, `classify_requirements`, `build_index`, `retrieve_evidence`, `reason_compliance`, and `score_confidence`. In the full architecture, this worker sequence operates as one branch under a higher-level coordinator that decides when compliance analysis should run, when comparison should run first, when drafting should be triggered, and when human approval is required before the workflow continues.

## 4. Work Completed to Date

The most significant progress during this reporting period has been the implementation of the project’s foundational modules and the formalization of the agentic workflow structure around them.

We completed the **document ingestion and preprocessing layer**. The system can parse both PDF and DOCX files, preserve section and page-related metadata where available, and convert documents into structured chunks suitable for downstream processing. The current configuration uses a chunk size of `600`, chunk overlap of `100`, and a maximum chunk size of `1000`. This segmentation strategy was selected to maintain enough local context for retrieval and reasoning while keeping the units manageable for model-backed processing [7].

We completed the **requirement extraction layer** using a hybrid approach. The extractor first uses requirement-oriented lexical cues such as `shall`, `must`, `required`, `ensure`, `provide`, `implement`, and `maintain`, and then uses an LLM-backed extraction pass to split compound requirements into atomic, traceable units. This combination proved more stable than either rules alone or prompting alone.

We completed the **requirement classification layer**. The current classifier uses a fast keyword-based pass followed by an LLM fallback for uncertain cases. It assigns requirements into categories such as obligations, deliverables, reporting, documentation, timelines, and compliance, which gives the workflow a structured intermediate representation for later retrieval, reasoning, and drafting stages.

We completed the **retrieval layer** using a hybrid semantic-plus-keyword strategy. Documents are embedded into a Chroma vector store, retrieved semantically with a top-k value of `5`, and then supplemented with keyword matches before reranking. This was an important design decision because real business documents often contain both semantically related passages and exact terminology that should not be lost [4][5][6][18].

We completed the **compliance reasoning and confidence-scoring backbone**. The reasoner applies an explicit four-label rubric of `compliant`, `partial`, `not_compliant`, and `not_addressed`, and it is instructed to remain evidence-based and cite evidence chunk identifiers. If the model path fails, the system falls back to a rules-based path. On top of this, a confidence scorer adjusts decisions using retrieval-score patterns, evidence count, contradiction heuristics, and explanation characteristics, then separates accepted items from those that should be reviewed or flagged.

We completed **memory, persistence, and output generation** for the workflow. Requirements, evidence, decisions, workflow state, and run summaries are persisted in structured JSON artifacts, while human-readable outputs can be exported in CSV, JSON, and Markdown forms. We also implemented an evaluation scaffold using `scikit-learn` for accuracy, Cohen’s kappa, per-label precision and recall, F1, and confusion matrices. These pieces are important because they make the system not only operable, but also auditable and testable [9][10][17].

## 5. Current and Target Agentic Workflow

The project is structured as a bounded agentic workflow rather than a single pipeline. At the control layer, the system is intended to accept a document-centered goal, inspect the document manifest, select the next bounded action, execute that action through the appropriate worker module, evaluate the result, and decide whether to continue, retry, branch, escalate, or finalize.

Under this design, the final workflow consists of the following components:

- **Planning and Task Management Agent**, which interprets the user goal, breaks it into bounded steps, maintains workflow state, and decides which downstream action should run next.
- **Document Intake and Routing Agent**, which classifies incoming documents into practical IT services categories such as solicitation, SOW/PWS, prior proposal, contract/amendment, past performance record, compliance instruction set, or draft response.
- **Historical Match and Comparison Agent**, which locates similar prior documents and produces change-analysis summaries that help determine whether prior content can be reused or adapted.
- **Requirement Extraction and Structuring Agent**, which separates technical or service requirements from compliance and submission-format requirements and converts them into traceable units.
- **Retrieval and Context Assembly Agent**, which pulls relevant prior examples, capabilities, past performance narratives, and supporting evidence needed for downstream reasoning or drafting.
- **Proposal Drafting Agent**, which uses extracted requirements and retrieved content to generate a first-pass outline or draft aligned to the document type and task objective.
- **Evaluation and Rewrite Agent**, which reviews the generated response for completeness, persuasiveness, weak sections, unsupported claims, and revision opportunities before sending it back through a rewrite pass.
- **QA, Approval, and Handoff Agent**, which performs acronym checks, naming consistency checks, unresolved placeholder checks, formatting validation, and human-approval gating for higher-risk outputs.

This workflow is designed so that the same engine can support multiple branches without becoming an open-ended autonomous system. A compliance-centered run can route into context preparation and evidence-backed compliance analysis, a comparison-driven run can prioritize prior-context matching and delta reporting, and a drafting-centered run can move through outline generation, evaluation, rewrite, and final validation. In all cases, the workflow remains bounded by explicit actions, retry limits, and approval gates.

## 6. Design Decisions and Experimental Findings

This phase of the project has been experimental in a deliberate and structured way. One of the most important design decisions has been to keep the system bounded. We want the workflow to be genuinely agentic, but not uncontrolled. For that reason, we adopted a planner that selects from a fixed action vocabulary and a workflow evaluator that determines whether a result should be accepted, retried on a limited subset, branched to another action, escalated for approval, or terminated as blocked.

Another important design decision has been to prefer hybrid methods where appropriate. Requirement extraction works more reliably when lexical cues and LLM-based refinement are combined. Retrieval works better when semantic similarity is supplemented with keyword matching. Reasoning becomes more robust when a fallback path exists. In practice, these layered methods have been more useful for document workflows than relying on a single model call to perform all interpretation and decision-making at once.

We also found that the IT services domain focus strengthens the technical quality of the system. It gives us a clear set of document roles, a meaningful definition of historical comparison, a realistic retrieval context for past performance and prior proposals, and a stronger justification for evaluator and rewrite loops. This focus makes the agentic workflow easier to define, easier to test, and more relevant to actual organizational use.

## 7. Current Progress Assessment

We currently assess the project as being approximately **70% complete**. This estimate is based on the fact that the majority of the worker capabilities and the core agentic workflow structure are already established. The implemented foundation includes document parsing, chunking, extraction, classification, retrieval, compliance reasoning, confidence scoring, persistence, output generation, and evaluation support. In addition, the control-plane concepts required for bounded planning, workflow state, approval checkpoints, and iterative evaluation are now part of the project architecture and implementation direction.

At the current stage, the project is no longer in a purely exploratory or conceptual phase. It already has a real technical backbone and a clearly defined control model. The remaining work is concentrated in end-to-end workflow integration, additional branch completion, validation on representative IT services examples, and final hardening of the planning, comparison, drafting, and approval-aware execution paths. For that reason, we consider the project to be in a late integration phase rather than an early build phase.

## 8. Remaining Work and Next Steps

The next phase of the project is centered on completing the full end-to-end bounded agentic loop and demonstrating it on representative IT services scenarios. The main next steps are:

- finish the planning and task-state layer so the system can track progress across actions,
- complete the domain-specific routing behavior for incoming document sets,
- integrate historical comparison across prior proposals, contracts, amendments, and past performance material,
- finish the proposal drafting, evaluator, and rewrite loop for bounded drafting support,
- complete the final approval and handoff behavior so uncertain or high-impact results are explicitly paused for human review,
- and expand workflow-level tests, resume behavior, and artifact validation so that both the control layer and worker layer can be demonstrated credibly in the final system.

These tasks are significant, but they are being built on top of an already functioning architecture rather than from scratch.

## 9. Conclusion

In summary, the project has been developed as a bounded agentic AI workflow for IT services document processing, compliance review, historical comparison, and proposal drafting support. The architecture, implementation choices, and experiments during this phase have all been directed toward that goal from the beginning: a system that can plan within a controlled action space, reason over evidence, loop through evaluation where appropriate, and involve human approval where needed.

The most important outcome of this interim stage is that the project already has a substantial technical foundation and a clearly defined agentic operating model. The remaining work is focused on completing integration and validating the full workflow at the system level. For that reason, we believe it is accurate and professionally defensible to state in this interim report that the project is currently around **70% complete**, with the major foundational work already in place and the final phase centered on full workflow integration, validation, and refinement.

## 10. References

[1] LangChain. *LangGraph: Build resilient language agents*. 2024.

[2] Xi, Z., Chen, W., Guo, X., He, W., Ding, Y., Hong, B., Zhang, M., Wang, J., Jin, E., Huang, E., Zheng, R., Fan, X., Wang, X., Xiong, L., & Wang, Y. (2023). *The rise and potential of large language model based agents: A survey*.

[3] Wooldridge, M., & Jennings, N. R. (1995). *Intelligent agents: Theory and practice*.

[4] Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W.-t., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). *Retrieval-augmented generation for knowledge-intensive NLP tasks*.

[5] Reimers, N., & Gurevych, I. (2019). *Sentence-BERT: Sentence embeddings using Siamese BERT-networks*.

[6] Robertson, S., & Zaragoza, H. (2009). *The probabilistic relevance framework: BM25 and beyond*.

[7] Liu, N. F., Lin, K., Hewitt, J., Paranjape, O., Bevilacqua, M., Petroni, F., & Liang, P. (2024). *Lost in the middle: How language models use long contexts*.

[9] Cohen, J. (1960). *A coefficient of agreement for nominal scales*.

[10] Sokolova, M., & Lapalme, G. (2009). *A systematic analysis of performance measures for classification tasks*.

[17] Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., Blondel, M., Prettenhofer, P., Weiss, R., Dubourg, V., et al. (2011). *Scikit-learn: Machine learning in Python*.

[18] Chroma. *Chroma: the open-source embedding database*.

[20] Amershi, S., Weld, D., Vorvoreanu, M., Fourney, A., Nushi, B., Collisson, P., Suh, J., Iqbal, S., Bennett, P. N., Inkpen, K., et al. (2019). *Guidelines for human-AI interaction*.
