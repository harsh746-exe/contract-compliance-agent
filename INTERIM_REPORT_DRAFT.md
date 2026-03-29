# Interim Report

## Project Title

**Agentic AI Workflow for IT Services Document Processing, Compliance Review, and Proposal Drafting**

## Team

Team of four

## Reporting Period

**Project start:** approximately the third week of January 2026  
**Interim report date:** March 20, 2026

## 1. Executive Summary

This interim report presents the current progress of our project, *Agentic AI Workflow for IT Services Document Processing, Compliance Review, and Proposal Drafting*. During the reporting period, the project evolved from a broad multi-agent document concept into a more concrete architecture for an IT services assistant that can plan work, invoke the right tools, reason over evidence, and return decision-ready outputs for human review.

This refinement made the project more technically credible and easier to evaluate. Rather than using agentic AI as a vague label, we now define it as a bounded workflow with specialized agents, shared working memory, retrieval-backed reasoning, evaluator and rewrite loops, and explicit human approval points for higher-risk actions. In that sense, our goal is not only document automation, but a controllable system that can move proposal and compliance work forward with limited supervision.

At the time of this interim report, we estimate that the project is approximately **70% complete**. Most of the technical foundation needed for that architecture is already implemented, including parsing, chunking, requirement extraction, classification, retrieval, compliance reasoning, confidence scoring, persistence, reporting, and evaluation support. The remaining work is concentrated in the components that make the workflow fully agentic in practice: planning, task-state management, domain routing, historical comparison, proposal drafting loops, approval gates, and end-to-end integration.

## 2. Problem Context and Motivation

The motivation for this project comes from the way document-heavy work is handled in many organizations, especially in IT services and contracting environments. Teams often deal with multiple related documents at once: a solicitation from a client, a statement of work, previous proposals, past performance narratives, current contracts, and older contract versions. In practice, reviewers must repeatedly extract key requirements, search across prior materials, compare documents for changes, draft new responses, and verify whether those responses are complete and compliant.

This process is labor-intensive and often repetitive. It also requires both technical understanding and administrative precision. A reviewer may need to determine not only what services are being requested, but also how the final submission must be structured, what supporting evidence from past work can be reused, and what gaps remain before a response is ready. Much of this work is still performed manually, or with fragmented tools that do not preserve traceability between a requirement, the evidence supporting it, and the final written response.

Our project is motivated by the idea that this workflow can be improved with a coordinated multi-agent system. Instead of asking one model to perform everything in one step, we are designing a pipeline in which specialized agents each handle part of the problem. This approach is intended to make the system more transparent, more adaptable, and more useful in real operational settings.

## 3. Project Aim and Scope

The main aim of the project is to design and implement a **bounded agentic AI workflow** that supports document understanding, compliance-oriented analysis, historical document comparison, and proposal drafting assistance for an IT services organization. A central design goal is that the system should not only analyze content, but also plan the next step, select the right tool or subworkflow, preserve task state, and escalate uncertain cases to human reviewers.

At the beginning of the project, our concept was more domain-agnostic. However, during implementation we found that a completely generic framing made it harder to define document categories, agent routing behavior, and meaningful demonstrations. For that reason, we intentionally narrowed the project to a domain-focused implementation. This does not remove the broader value of the idea, but it gives the current system a clearer operational setting and a more coherent structure.

Within this refined scope, the project is intended to support three connected workflows. The first is **document intake and routing**, where incoming files are identified and directed to the appropriate workflow. The second is **historical comparison and compliance-oriented analysis**, where a new document can be compared against relevant prior material and summarized for review. The third is **proposal drafting support**, where the system extracts requirements, retrieves relevant prior content, produces a first-pass draft, evaluates its quality, and helps guide revision.

For this interim stage, the project has focused primarily on building the technical foundation required to support those workflows. As a result, the current codebase is strongest in the areas of document processing, requirement extraction, retrieval, reasoning, and evidence-based review. These components form the operational core of the future agent loop, but the planner, long-running task coordination, and approval logic are still being integrated.

## 4. Technical Approach and System Design

From a technical standpoint, the system is implemented in **Python 3.9+** and organized into separate layers for ingestion, agent modules, orchestration, memory, output, and evaluation. This layered structure was chosen to support modular development and to make it easier to extend the system from a compliance-review backbone into a broader agentic document workflow. We increasingly interpret these layers as two cooperating planes: an execution plane that performs parsing, retrieval, and reasoning tasks, and a control plane that decides what should happen next, what evidence is needed, and when a result should be escalated.

The current implementation uses **LangGraph 0.0.20** to orchestrate the multi-step workflow and **LangChain 0.1.0** with `langchain-openai 0.0.5` for LLM-backed agent interactions. The default LLM configuration uses `ChatOpenAI` with the model name `gpt-4-turbo-preview`, while the retrieval layer relies on **ChromaDB 0.4.22** and **sentence-transformers 2.3.1**, currently configured with the embedding model `sentence-transformers/all-MiniLM-L6-v2`. The project also includes `PyPDF2 3.0.1`, `pdfplumber 0.10.3`, and `python-docx 1.1.0` for document parsing, and `scikit-learn 1.4.0` for evaluation metrics. These tools currently support the worker side of the architecture, while the final phase will wrap them in stronger planning, task-state, and approval logic.

To describe the design more precisely, the current system is agentic in a limited but real sense. It already uses model-driven extraction, dynamic retrieval, evidence-based reasoning, confidence-aware escalation, and working-memory logs instead of a single fixed script. However, a truly agentic version requires additional capabilities beyond today’s backbone: goal decomposition, explicit task state, iterative evaluation and rewrite cycles, persistence across workflow stages, and approval gates for actions that should remain human-controlled.

At the current stage, the implemented pipeline already follows a structured sequence:

`ingest_documents -> extract_requirements -> classify_requirements -> build_index -> retrieve_evidence -> reason_compliance -> score_confidence`

This existing pipeline functions as a reusable worker chain. The next architectural step is to place it under a higher-level coordinator that can route document types, trigger the right worker sequence, track progress against a goal, and loop through evaluation or revision until a stopping condition is met.

## 5. Work Completed to Date

The most significant progress so far has been the implementation of the project’s foundational modules. At this stage, the following areas are already in place:

- **Document ingestion and preprocessing.** The system can parse both PDF and DOCX files, preserve section and page-related metadata where available, and transform the documents into structured chunks. The parser uses `pdfplumber` as the preferred PDF reader, with `PyPDF2` as fallback, and uses `python-docx` for Word documents. Once parsed, the text is chunked according to approximate token size. The current configuration uses a chunk size of `600`, a chunk overlap of `100`, and a maximum chunk size of `1000`. This chunking strategy was selected because it preserves enough context for later reasoning while still making retrieval feasible and efficient.

- **Requirement extraction.** We implemented this as a hybrid method because neither pure rules nor pure prompting felt sufficient. The system first identifies likely requirement statements using phrases such as `shall`, `must`, `required`, `ensure`, `provide`, `implement`, and `maintain`. These candidates are then refined through an LLM-based extraction step that produces structured JSON output and helps split compound requirements into atomic ones. Each requirement is deduplicated and assigned a stable identifier. This hybrid design has worked better for us than relying on either heuristics or LLMs alone.

- **Requirement classification.** The classifier currently assigns requirements to generic categories such as obligations, deliverables, reporting, documentation, timelines, and compliance. It uses a fast keyword-based pass first, followed by an LLM-based pass for uncertain or more complex cases. Although these categories began as part of a domain-agnostic design, they now function as the lower-level compliance structure underneath the newer IT-services-focused workflow.

- **Retrieval.** The retrieval layer uses a hybrid approach that combines semantic similarity with keyword matching. Response or supporting documents are embedded into a Chroma vector store, and relevant evidence is retrieved with a top-k value of `5`. Semantic retrieval is supplemented by keyword-based matching, and the evidence is then merged and reranked before use in later reasoning stages. This design has proven useful because it reduces over-reliance on one retrieval method and improves resilience when documents use varied terminology.

- **Compliance reasoning and confidence scoring.** The reasoning agent currently uses a four-label rubric: `compliant`, `partial`, `not_compliant`, and `not_addressed`. The prompt instructs the model to remain evidence-based, cite evidence chunk IDs, avoid overstating compliance, and propose improvements when the evidence is incomplete. If the LLM path fails, the system falls back to a rules-based scoring method. On top of the reasoning stage, the confidence scorer adjusts confidence using multiple signals, including maximum retrieval score, average retrieval score, score variance, evidence count, contradiction heuristics, and explanation length. The current thresholds are `0.75` for high confidence and `0.50` for medium confidence. This allows the system to distinguish between acceptable results and those that should be sent for review or flagged.

- **Memory, persistence, and output generation.** The system stores extracted requirements, retrieved evidence, and compliance decisions in persistent JSON files. It also logs run-level information through a working memory structure that records agent actions, durations, outputs, and errors. On top of this, it can already generate CSV, JSON, and Markdown outputs. This is an important milestone because it means the system already produces reviewable artifacts rather than remaining an internal prototype only.

- **Evaluation scaffold.** The project includes evaluation utilities implemented with `scikit-learn`, supporting metrics such as accuracy, Cohen’s kappa, per-label precision, recall, F1, and confusion matrices. Although the final evaluation dataset is still under development, the infrastructure for structured assessment is already available.

## 6. Current Agentic Workflow Interpretation

At this stage, the system should be described as a partially completed agentic system rather than a finished autonomous agent. The current implementation already has working agents for extraction, classification, retrieval, compliance reasoning, and confidence handling, but it still operates primarily as a structured backbone rather than as a full goal-driven operator.

For the final project, we now define a truly agentic workflow as one that can accept a document-centered goal, decompose it into steps, select the right specialized agent, preserve task state, evaluate intermediate outputs, and involve a human reviewer only when uncertainty or risk crosses a threshold. Under that definition, the target architecture consists of the following components:

- **Planning and Task Management Agent**, which will interpret the user’s goal, break it into actionable steps, maintain workflow state, and decide which downstream agent should act next.
- **Document Intake and Routing Agent**, which will classify incoming documents into practical IT services categories such as solicitation, SOW/PWS, prior proposal, contract/amendment, past performance record, compliance instruction set, or draft response.
- **Historical Match and Comparison Agent**, which will locate similar prior documents and produce change-analysis summaries that help determine whether prior content can be reused or adapted.
- **Requirement Extraction and Structuring Agent**, which will separate technical or service requirements from compliance and submission-format requirements and convert them into traceable units.
- **Retrieval and Context Assembly Agent**, which will pull relevant prior examples, capabilities, past performance narratives, and supporting evidence needed for downstream reasoning or drafting.
- **Proposal Drafting Agent**, which will use extracted requirements and retrieved content to generate a first-pass outline or draft aligned to the document type and task objective.
- **Evaluation and Rewrite Agent**, which will review the generated response for completeness, persuasiveness, weak sections, unsupported claims, and revision opportunities before sending it back through a rewrite pass.
- **QA, Approval, and Handoff Agent**, which will perform acronym checks, naming consistency checks, unresolved placeholder checks, formatting validation, and human-approval gating for higher-risk outputs.

Several of the hardest technical building blocks for this architecture already exist. Extraction, retrieval, evidence-based reasoning, confidence scoring, persistence, and reporting are already functional. The remaining work is to connect these into a persistent control loop with goal tracking, approval gates, and domain-specific orchestration.

## 7. Experiments, Findings, and Design Decisions

This phase of the project has been highly experimental, but in a deliberate and structured way. We have consistently tried to balance ambition with reliability.

One important design decision was to prefer **hybrid methods** over pure single-method solutions. We found that requirement extraction worked more reliably when heuristic signals and LLM-based extraction were combined. Retrieval worked better when semantic similarity was supplemented with keyword matching. Reasoning became more robust when we added a fallback path instead of assuming perfect LLM output. These experiments reinforced the idea that a practical agentic workflow often benefits from layered methods rather than a single intelligent component trying to do everything.

Another important finding was that the project became technically stronger once we shifted from a fully domain-agnostic framing to a **domain-focused IT services framing**. This helped us define what “good retrieval” means, what kinds of document comparisons matter, and what an end-to-end workflow should look like. It also made it easier to articulate why the project requires specialized agents rather than a single summarization pipeline.

At the same time, we observed limitations that will shape the final phase. LLM-backed extraction and reasoning remain nondeterministic even under low-temperature settings. Retrieval quality still needs validation on realistic document sets, especially when relevant evidence is indirect or distributed across sections. The current system is stronger on the compliance-analysis backbone than on the proposal-drafting loop, which is why the remaining development effort is now focused on workflow integration rather than low-level module creation.

## 8. Current Progress Assessment

We currently estimate the project to be approximately **70% complete**.

This estimate is based on the fact that the major foundational layers are already implemented: ingestion, chunking, extraction, classification, retrieval, compliance reasoning, confidence scoring, persistence, output generation, and evaluation support. These components correspond to the worker capabilities of the architecture, and they already provide the system with real evidence-processing behavior rather than a purely conceptual design. In addition, the system is already supported by documentation, a runnable demo path, and an offline-first testing workflow. At the current repository state, the local test suite reports **15 tests passed and 1 skipped**, which provides additional evidence that the implemented components are real and testable.

The remaining 30% is concentrated in the control-layer features that make the final system truly agentic in day-to-day use: domain routing, historical comparison, planner-driven task decomposition, evaluator-rewrite looping, approval gates, and final QA validation. These tasks are substantial, but they are being built on top of an existing operational backbone. For that reason, we view the project as being in a late integration phase rather than an early exploratory phase.

## 9. Remaining Work and Next Steps

The next phase of the project is now clearly defined.

The next phase of the project is now clearly defined and is centered on converting the current backbone into a more fully agentic workflow.

The main next steps are:

- implement a planning and task-state layer so that the system can accept a goal, break it into steps, track progress, and decide which agent should act next,
- implement the domain-specific document routing logic so that incoming files are categorized and directed to the correct workflow,
- add the historical comparison behavior and retrieval across prior proposals, contracts, amendments, and past performance material,
- integrate the proposal drafting, evaluator, and rewrite loop so that the system can critique and improve its own output before handoff,
- add approval gates and escalation rules so uncertain or high-impact decisions are explicitly sent to a human reviewer,
- complete the combined QA and validation stage,
- and run end-to-end demonstrations on representative IT services examples.

While doing this, we remain open to experimenting with frameworks, prompts, or retrieval settings where needed. That openness has been one of the core characteristics of the project so far. However, unlike the earliest phase, our experimentation is now guided by a much more concrete architectural target: a bounded agentic system that can plan, act, self-evaluate, and hand off responsibly.

## 10. Conclusion

In summary, the project has progressed from a broad concept for a multi-agent document workflow system into a much more clearly defined and technically grounded implementation: a **bounded agentic AI workflow for IT services document processing, compliance review, historical comparison, and proposal drafting support**.

The most important achievement of this stage is that the project now has a real technical backbone. The architecture exists in code, the core worker modules are functioning, the system produces structured outputs, and the workflow is no longer only conceptual. The remaining work is primarily about connecting these components into the control layer that makes the system more fully agentic: planning, routing, evaluation loops, approval logic, and final domain integration.

For that reason, we believe it is accurate and professionally defensible to state in this interim report that the project is currently **around 70% complete**, with the major foundational work already finished and the remaining effort centered on control-layer integration, domain specialization, and final refinement.
