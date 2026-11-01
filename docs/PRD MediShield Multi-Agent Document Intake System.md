# PRD: MediShield Multi-Agent Document Intake System

Oct 29, 2026 · @PKS

## 1. Document Control & Executive Summary

This PRD defines a multi-agent AI system that classifies, extracts, verifies, fraud-scores and decides on incoming MediShield insurance documents within minutes, with a case management UI for human oversight. It is the source document for downstream technical specs and ADRs.

| Field | Value |
| --- | --- |
| Product | MediShield Multi-Agent Document Intake System |
| Version / status | v0.1, draft for review |
| Source | Assignment 02, Multi-Agent Document Intake System |
| Sponsor | VP of Operations, MediShield Health Insurance Ltd. |
| Product / engineering owner | Founding ML engineer, internal AI team |
| Requirement ID scheme | FR-xxx functional, NFR-xxx non-functional, AC-xxx acceptance, OQ-xx open question |

**Summary.** MediShield receives about 85,000 document submissions per month, reviewed by 120 people at a cost of $18.4M a year and 4.2 days per claim. The proposed system ingests each document through an API, classifies it with a vision LLM, routes it to KYC, Claims and Policy (RAG) agents in parallel, runs fraud scoring, and has an Orchestrator issue Approve, Reject or Escalate with a confidence score and justification. Operations staff work cases in a Next.js UI with a human review queue, override, and a full audit log.

**Document conventions.** Items marked *\[Assumption\]* are inferred from the source and need confirmation. Items marked *\[Added\]* are not in the source but are needed for a production-ready spec. Unresolved items are listed in section 13.

## 2. Background, Problem Statement & Business Case

Manual document intake at MediShield is slow, costly and error-prone, and it has produced regulatory exposure on KYC compliance.

**Company context.** MediShield Health Insurance Ltd. (Chicago, IL) insures over 2 million policyholders across 14 states. Documents arrive by email, mobile upload, and scanning stations at partner hospitals: scanned claim forms, discharge summaries, prescription images, identity documents and policy amendment requests.

**Baseline (today, manual process).**

| Metric | Baseline |
| --- | --- |
| Monthly document volume | \~85,000 submissions |
| Manual reviewers | 120 |
| Average time per claim | 4.2 days |
| Annual processing overhead | $18.4M |
| Re-processing rate (misclassification) | 12% |
| Regulatory audits (KYC non-compliance) | 3 ongoing |

**Problem statement.** Reviewers manually sort, validate and route every submission. Classification errors cause rework (12%) and delayed reimbursements, and inconsistent identity checks have triggered regulatory audits. The process does not scale with volume and offers no systematic fraud screening at intake.

**Opportunity.** Automating classification, extraction, coverage lookup, KYC and fraud screening reduces time-to-decision from days to minutes, concentrates human effort on exceptions, and creates a consistent, auditable KYC trail.

**Business case (qualitative; targets in section 3).** Value comes from four levers: lower processing cost per document, faster reimbursement, fewer re-processed claims, and a defensible audit trail for regulators. *\[Assumption\]* No ROI model was provided; one should be built once pilot accuracy and automation rates are measured (see OQ-14).

## 3. Goals, Non-Goals & Success Metrics

The system succeeds if it automates correct decisions for most documents within minutes while routing every uncertain or risky case to a human.

**Goals**

1. Classify incoming documents into six types and route them to the right specialist agents automatically.
2. Extract structured claim data (amounts, ICD-10, CPT, provider NPI, service date) with high completeness.
3. Verify identity and detect expired or tampered documents to close the KYC compliance gap.
4. Check procedure coverage against uploaded policy PDFs using retrieval-augmented generation.
5. Score fraud risk using claim history and statistical baselines.
6. Issue Approve / Reject / Escalate decisions with confidence and justification, and give ops staff a UI to review, override and audit.

**Non-goals (v1)**

- Actual payment execution or reimbursement disbursement.
- Replacing the member, policy or claims system of record; the system reads from them (see section 5 for the integration assumption).
- Fully autonomous denial without human recourse; rejections remain appealable and reviewable *\[Assumption\]*.
- Training or fine-tuning custom models; v1 uses off-the-shelf vision LLMs and OCR.
- Handling document types outside the six supported types, except routing them to human review.

**Success metrics**

| Metric | Target | Source / note |
| --- | --- | --- |
| Classification accuracy | ≥ 85% on 20-case test set | Weight 20%; target *\[Assumption\]*, source sets no number |
| Extraction completeness | ≥ 85% of required fields | Weight 20%; target *\[Assumption\]* |
| Policy retrieval relevance | Manual spot-check, majority relevant | Weight 15% |
| Decision correctness | ≥ 60% (hard gate); aim ≥ 80% (assumed) | Weight 25%; 60% is the stated minimum |
| Overall weighted score | ≥ 70% | Stated minimum passing threshold |
| UI functionality | Dashboard, detail, override work end to end | Weight 10% |
| Code quality | Typed interfaces, agent separation, no hardcoded credentials | Weight 10% |
| Time to decision | Minutes per document (target p95 ≤ 5 min) | Source says "within minutes"; p95 *\[Assumption\]* |
| Business outcomes (post-pilot) | Lower days-per-claim vs 4.2; re-processing rate below 12%; zero new KYC findings | Targets to be set with VP Operations (OQ-14) |

## 4. Stakeholders, Personas & User Journeys

Six groups depend on the system; the operations reviewer is the primary daily user.

| Stakeholder / persona | Role | Needs from the system |
| --- | --- | --- |
| VP of Operations | Sponsor | Lower cost and cycle time; measurable accuracy; audit readiness |
| Operations reviewer (today: 120 staff) | Primary user | Clear queue of escalated cases; see why the system escalated; override quickly |
| Operations lead / supervisor *\[Added\]* | Oversight | Dashboard of volumes, statuses and backlog; override accountability |
| Compliance / audit officer *\[Added\]* | Regulatory contact | Timestamped trace of every agent decision; KYC evidence |
| ML / platform engineer | Builder and maintainer | Typed agent contracts, observability, evaluation harness |
| Policyholder / provider (indirect) | Submitter | Fast, correct outcome; no lost documents |

**Journey A: straight-through approval.**

1. A document is uploaded via API (email, mobile or scanning station feed); a `case_id` is returned.
2. The Classifier identifies a claim form; KYC, Claims and Policy agents run in parallel.
3. Fraud score is below 0.3 and all agent confidences are at least 0.6; the Orchestrator approves.
4. The case appears as Approved on the dashboard with a full audit trail. No human touch.

**Journey B: escalation and override.**

1. Fraud score is 0.3 or higher, or an agent reports confidence below 0.6; the case is marked Escalated.
2. The reviewer opens the case, views the document image beside per-agent outputs and the justification.
3. The reviewer confirms or overrides the decision and records a reason; the override is written to the audit log.

**Journey C: unknown document.**

1. The Classifier returns UNKNOWN or low confidence.
2. The case goes straight to the human review queue without specialist processing.
3. The reviewer assigns a type (or rejects the submission) and may re-trigger the pipeline *\[Added\]*.

**Journey D: policy onboarding.**

1. An authorized user uploads a policy PDF in real time.
2. Docling parses and chunks it; chunks are embedded into the vector store.
3. The policy becomes available to the Policy Agent for retrieval.

## 5. Scope, Assumptions & Constraints

v1 delivers the full pipeline, API, RAG module, UI and evaluation dataset described in the source; production-grade hardening items are flagged as *\[Added\]*.

**In scope**

- FastAPI ingestion API (JPEG, PNG, PDF, TIFF) with case IDs, object storage and a task queue.
- Seven agents (Classifier, KYC, Claims, Policy, Fraud, Orchestrator, plus the OCR pre-processor as a shared stage) in a LangGraph state machine.
- Policy RAG: Docling ingestion, vector store (ChromaDB or Qdrant), retrieval by procedure code.
- Next.js case management UI: dashboard, case detail, decision panel, human review queue, audit log.
- Synthetic dataset of at least 20 labeled document images and an evaluation harness.
- Architecture diagram and README with one end-to-end walkthrough.

**Out of scope (v1)**

- Payment processing, provider contracting, and member-facing portals.
- Production integration with live PHI data sources beyond a stub or mock member/claims database *\[Assumption\]*.
- Languages other than English (bonus item only).
- Mobile app and scanning-station client software; only the upload API is provided.

**Assumptions**

| ID | Assumption |
| --- | --- |
| A-01 | Member database and patient claim history are accessible via a queryable store (SQL); v1 may use a seeded mock database. |
| A-02 | The stated seven-agent deliverable counts Classifier, KYC, Claims, Policy, Fraud, Orchestrator and OCR/Pre-processor. |
| A-03 | All documents and data in the build are synthetic; no real PHI is used during development. |
| A-04 | A vision-capable LLM is available through an API; the source names Claude Sonnet or GPT-4o. |
| A-05 | The decision rule in the source is authoritative and applied deterministically after agents return (see FR-ORC). |
| A-06 | One document equals one case; multi-document claims (for example claim form plus discharge summary) are linked by member/claim reference in a later phase. |
| A-07 | Human reviewers can override any automated decision, including Approve. |

**Constraints**

- Stack named in the source: Python, FastAPI, LangGraph, Next.js, Redis or Celery, S3 or MinIO, ChromaDB or Qdrant, Docling, Tesseract or a vision LLM.
- No hardcoded credentials; secrets via environment variables (graded in code quality).
- Health-insurance data handling implies HIPAA-style obligations; see NFR-SEC (the source does not state a compliance framework, see OQ-03).

## 6. System Overview

Each document moves through one LangGraph state machine: ingest, classify, OCR, three parallel specialists, fraud scoring, then a single decision.

&#91;embedded content: system architecture and LangGraph states · 10 components, 1 human step\]

Unknown or low-confidence documents leave the flow at the classifier, and escalated decisions join them in the human review queue.

**State machine.** `RECEIVED → CLASSIFIED → [PARALLEL: KYC + CLAIMS + POLICY] → FRAUD_CHECK → AGGREGATED → DECIDED`. Conditional edges after classification choose which specialists run (routing matrix in 7.2). The Orchestrator fires only once every routed upstream agent has finished.

**Design principles**

- Agents are separate modules with typed inputs and outputs; they share data only through the graph state (8.3).
- LLMs classify, extract and explain; decisions, thresholds and fraud scores are computed by deterministic code over typed outputs *\[Assumption\]*.
- Anything uncertain, failed or risky ends in a human queue; no case is silently dropped.
- Every node writes audit events, so a case can be reconstructed end to end.
- **Dependency to resolve.** The source runs KYC, Claims and Policy in parallel, yet the Policy Agent needs procedure codes from the Claims Agent. The spec must either sequence Policy after Claims inside the parallel block or let Policy extract codes from the OCR payload itself (OQ-17).

## 7. Functional Requirements

Requirements are grouped by component. Priority uses MoSCoW (Must / Should / Could). Origin is *Source* (stated in the assignment), *Added* (needed for a production-ready spec), or *Assumption*.

### 7.1 Document Ingestion API (FR-ING)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-ING-01 | Expose a FastAPI endpoint accepting multipart uploads of JPEG, PNG, PDF and TIFF files. | Must | Source |
| FR-ING-02 | Assign a unique `case_id` per submission and return it immediately with an asynchronous acknowledgement (HTTP 202). | Must | Source |
| FR-ING-03 | Store the raw document unmodified in object storage (S3 or local MinIO) with a content checksum. | Must | Source |
| FR-ING-04 | Publish a processing job to a task queue (Redis or Celery) that triggers the LangGraph pipeline. | Must | Source |
| FR-ING-05 | Reject unsupported file types and files over a size limit with a clear 4xx error; limit configurable (default 25 MB). | Should | Added |
| FR-ING-06 | Detect duplicate uploads by checksum and link them to the existing case instead of reprocessing. | Should | Added |
| FR-ING-07 | Provide case endpoints: list cases (filter by status), get case detail with agent outputs, get audit log, submit human override. | Must | Source |
| FR-ING-08 | Provide a policy upload endpoint that triggers Policy RAG ingestion (see FR-POL). | Must | Source |
| FR-ING-09 | Record submission channel (email, mobile, scanning station, API) and timestamp on the case. | Could | Added |

### 7.2 Classifier Agent (FR-CLS)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-CLS-01 | Use a vision-capable LLM (Claude Sonnet or GPT-4o) to inspect the document image and return `{doc_type, confidence, routing_tags}`. | Must | Source |
| FR-CLS-02 | `doc_type` is one of CLAIM\_FORM, ID\_DOCUMENT, DISCHARGE\_SUMMARY, PRESCRIPTION, POLICY\_AMENDMENT, UNKNOWN. | Must | Source |
| FR-CLS-03 | If `doc_type` is UNKNOWN or `confidence` is below the review threshold (default 0.6), skip specialist agents and place the case in the human review queue. | Must | Source |
| FR-CLS-04 | Output must validate against a typed schema; malformed model output triggers one retry, then routes to human review. | Must | Added |
| FR-CLS-05 | For multi-page PDFs and TIFFs, classify using page 1 plus a sampled later page; document the policy in the spec. | Should | Added |
| FR-CLS-06 | Persist the model name, prompt version and raw model response for audit. | Must | Added |

**Routing matrix.** The source states that conditional edges route documents to relevant specialists but not which. This matrix is proposed and must be confirmed (OQ-05).

| doc\_type | OCR | KYC | Claims | Policy | Fraud |
| --- | --- | --- | --- | --- | --- |
| CLAIM\_FORM | Yes | Yes | Yes | Yes | Yes |
| ID\_DOCUMENT | Yes | Yes | No | No | Yes (tamper signals only) |
| DISCHARGE\_SUMMARY | Yes | Member match only | Yes | Yes | Yes |
| PRESCRIPTION | Yes | Member match only | Yes (drug/provider fields) | Yes | Yes |
| POLICY\_AMENDMENT | Yes | Yes | No | Yes (amendment vs. policy) | No |
| UNKNOWN | No | No | No | No | No (human review) |

### 7.3 OCR / Pre-processor (FR-OCR)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-OCR-01 | Run before specialist agents on image-based inputs, using Tesseract or a vision LLM. | Must | Source |
| FR-OCR-02 | Output normalized JSON `{fields[], raw_text, bounding_boxes}`; all downstream agents consume this payload. | Must | Source |
| FR-OCR-03 | For PDFs with an embedded text layer, extract text directly and skip OCR; fall back to OCR on empty pages. | Should | Added |
| FR-OCR-04 | Normalize images (deskew, rotation, resolution) before OCR; record per-page OCR confidence. | Should | Added |
| FR-OCR-05 | Support Spanish and Hindi through a multilingual OCR model. | Could | Source (bonus) |

### 7.4 KYC Agent (FR-KYC)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-KYC-01 | Validate member ID, date of birth and policy number against the member database. | Must | Source |
| FR-KYC-02 | Check document expiry dates (for example ID validity) against the submission date. | Must | Source |
| FR-KYC-03 | Flag visual anomalies that may indicate tampering (font inconsistencies, pixel artifacts). | Must | Source |
| FR-KYC-04 | Output `{kyc_passed: bool, flags[], confidence}`; each flag has a code, severity and evidence reference (page, bounding box). | Must | Source / Added |
| FR-KYC-05 | Implement Error Level Analysis (ELA) on JPEG inputs as a lightweight image-forensics check. | Could | Source (bonus) |
| FR-KYC-06 | Mismatch between extracted name and member record is a hard fail unless within a configurable fuzzy-match tolerance. | Should | Added |

### 7.5 Claims Agent (FR-CLM)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-CLM-01 | Extract claim amount, ICD-10 diagnosis codes, CPT procedure codes, provider NPI and service date. | Must | Source |
| FR-CLM-02 | Validate the extracted fields against MediShield's claim submission standard and return `{extracted_fields, schema_valid: bool, validation_errors[]}`. | Must | Source |
| FR-CLM-03 | Apply format checks: ICD-10 pattern, 5-character CPT, 10-digit NPI with Luhn check, ISO date not in the future, amount greater than zero. | Should | Added |
| FR-CLM-04 | Report per-field confidence and source location (page, bounding box) so reviewers can verify against the image. | Should | Added |
| FR-CLM-05 | Missing required fields set `schema_valid=false` with an explicit error per missing field. | Must | Source / Added |
| FR-CLM-06 | The claim submission standard is stored as a versioned schema file (see OQ-04). | Must | Added |

### 7.6 Policy Agent and RAG Module (FR-POL)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-POL-01 | Accept real-time policy PDF uploads and ingest and chunk them with Docling. | Must | Source |
| FR-POL-02 | Embed chunks and store them in a vector database (ChromaDB or Qdrant) with metadata: policy ID, version, section, page. | Must | Source |
| FR-POL-03 | Given CPT (and related ICD-10) codes from the Claims Agent, retrieve relevant policy clauses. | Must | Source |
| FR-POL-04 | Output `{covered: bool, coverage_percentage, policy_clause, exclusions[]}`; `policy_clause` quotes the supporting text with page reference. | Must | Source / Added |
| FR-POL-05 | Restrict retrieval to the policy that applies to the member (matched via policy number from KYC/claim form). | Must | Added |
| FR-POL-06 | If no sufficiently relevant clause is retrieved, return low confidence (not covered=false by default), which drives escalation. | Must | Added |
| FR-POL-07 | Demonstrate retrieval on at least two sample policy documents. | Must | Source |
| FR-POL-08 | Support policy versioning and effective dates so a claim is checked against the policy in force on the service date. | Should | Added |

### 7.7 Fraud Detection Agent (FR-FRD)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-FRD-01 | Query the patient's claim history from the database. | Must | Source |
| FR-FRD-02 | Score the current claim against baselines: duplicate submissions, frequency anomalies, provider billing patterns. | Must | Source |
| FR-FRD-03 | Output `{fraud_score: float 0-1, anomalies[], risk_level: LOW \| MEDIUM \| HIGH}`. | Must | Source |
| FR-FRD-04 | Map score to risk level: LOW below 0.3, MEDIUM 0.3 to below 0.6, HIGH 0.6 and above. Only the 0.3 cut is from the source. | Should | Assumption |
| FR-FRD-05 | Each anomaly lists a type, evidence (for example matching prior `case_id`), and its contribution to the score. | Must | Added |
| FR-FRD-06 | Scoring is deterministic and rule/statistics based; an LLM may only generate explanatory text, not the score. | Should | Assumption |

### 7.8 Orchestrator Agent (FR-ORC)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-ORC-01 | Fire only after all routed upstream agents complete, using LangGraph state aggregation. | Must | Source |
| FR-ORC-02 | APPROVE when KYC passed AND claim schema valid AND procedure covered AND fraud score below 0.3. | Must | Source |
| FR-ORC-03 | REJECT when KYC failed OR procedure not covered OR schema invalid. | Must | Source |
| FR-ORC-04 | ESCALATE when fraud score is 0.3 or higher OR any agent confidence is below 0.6. | Must | Source |
| FR-ORC-05 | Precedence: (1) any agent error or confidence below 0.6, then (2) fraud score 0.3 or higher, then REJECT conditions, then APPROVE. Rationale: unreliable or risky cases must not be auto-decided either way. | Must | Assumption (OQ-06) |
| FR-ORC-06 | Output `{decision, confidence, justification, agent_summaries}`; decision logic is a deterministic function over typed agent outputs, with an LLM used only to draft the justification text. | Must | Source / Assumption |
| FR-ORC-07 | Orchestrator confidence is computed from agent confidences (default: minimum of agent confidences) and is logged for calibration. | Should | Assumption (OQ-07) |
| FR-ORC-08 | If an agent times out or errors after retries, the case is ESCALATED with the failure recorded. | Must | Added |
| FR-ORC-09 | Thresholds (0.3 fraud, 0.6 confidence) are configuration, versioned and recorded with each decision. | Should | Added |

### 7.9 Case Management UI (FR-UI)

| ID | Requirement | Priority | Origin |
| --- | --- | --- | --- |
| FR-UI-01 | Dashboard lists all cases with status badges: Processing, Approved, Rejected, Escalated; supports filter, sort and search by case ID. | Must | Source |
| FR-UI-02 | Case detail shows a document image viewer (zoom, multi-page) beside collapsible per-agent output panels. | Must | Source |
| FR-UI-03 | Decision panel shows final decision, confidence and justification text. | Must | Source |
| FR-UI-04 | Human review queue lists escalated and unknown-document cases with an override action (approve, reject, reclassify) that requires a reason. | Must | Source / Added |
| FR-UI-05 | Audit log shows a timestamped trace of every agent decision, input version, model and human action per case. | Must | Source |
| FR-UI-06 | Overrides are attributed to an authenticated user and appended to the audit log; original automated decision is preserved. | Must | Added |
| FR-UI-07 | Role-based access: reviewer, supervisor, auditor (read-only), admin. | Should | Added |
| FR-UI-08 | Push real-time agent status updates over WebSockets (for example "KYC Agent: passed"). | Could | Source (bonus) |
| FR-UI-09 | "Download Case Report" generates a PDF summary of the case with all agent outputs. | Could | Source (bonus) |
| FR-UI-10 | Policy upload screen to add policy PDFs and view ingestion status. | Should | Added |

## 8. Data Contracts & Interfaces

Every agent consumes and produces a typed object (Pydantic models in Python, mirrored as TypeScript types for the UI), so the spec can derive JSON Schema and OpenAPI directly. Field names below are from the source; types and envelope fields are proposed.

### 8.1 Case state model

| State | Meaning | Next |
| --- | --- | --- |
| RECEIVED | Stored, queued, `case_id` issued | CLASSIFIED |
| CLASSIFIED | Doc type and confidence set | Specialists (parallel) or NEEDS\_REVIEW |
| KYC / CLAIMS / POLICY running | Routed specialists execute in parallel | FRAUD\_CHECK |
| FRAUD\_CHECK | Fraud agent scoring | AGGREGATED |
| AGGREGATED | All agent outputs in state | DECIDED |
| DECIDED | Approve, Reject or Escalate recorded | OVERRIDDEN (optional) |
| NEEDS\_REVIEW *\[Added\]* | UNKNOWN or low-confidence classification, or pipeline failure | Human action |
| OVERRIDDEN *\[Added\]* | Human changed the decision; original retained | Terminal |

UI status badges map as: Processing = RECEIVED through AGGREGATED; Approved, Rejected, Escalated = DECIDED with that decision; NEEDS\_REVIEW is shown in the review queue as Escalated *\[Assumption\]*.

### 8.2 Agent I/O contracts

All outputs carry a common envelope: `agent`, `agent_version`, `started_at`, `finished_at`, `status` (OK, ERROR or SKIPPED), `model`, `confidence`. SKIPPED means the agent was not routed for this document type and is ignored by the decision rules. (Aligned with spec.md v0.2.)

```json
// Classifier
{ "doc_type": "CLAIM_FORM | ID_DOCUMENT | DISCHARGE_SUMMARY | PRESCRIPTION | POLICY_AMENDMENT | UNKNOWN",
  "confidence": 0.93, "routing_tags": ["claim", "has_cpt"] }

// OCR / Pre-processor
{ "fields": [{ "key": "member_id", "value": "...", "confidence": 0.9, "page": 1 }],
  "raw_text": "...", "bounding_boxes": [{ "text": "...", "page": 1, "x": 0, "y": 0, "w": 0, "h": 0 }] }

// KYC
{ "kyc_passed": true, "flags": [{ "code": "ID_EXPIRED", "severity": "HIGH", "evidence": "page 1" }], "confidence": 0.88 }

// Claims
{ "extracted_fields": { "claim_amount": 0.0, "icd10_codes": [], "cpt_codes": [], "provider_npi": "", "service_date": "YYYY-MM-DD" },
  "schema_valid": true, "validation_errors": [] }

// Policy
{ "covered": true, "coverage_percentage": 80, "policy_clause": { "text": "...", "policy_id": "...", "page": 12 }, "exclusions": [] }

// Fraud
{ "fraud_score": 0.12, "anomalies": [{ "type": "DUPLICATE_CLAIM", "evidence": "case_id", "weight": 0.0 }], "risk_level": "LOW | MEDIUM | HIGH" }

// Orchestrator
{ "decision": "APPROVE | REJECT | ESCALATE", "confidence": 0.85, "justification": "...", "agent_summaries": { } }
```

### 8.3 LangGraph shared state

The graph state holds: `case_id`, `pipeline_run`, `document` (object key, mime, pages), `classification`, `ocr`, `kyc`, `claims`, `policy`, `fraud`, `decision`, `errors[]` and `audit[]` (the audit events). Parallel branches write to disjoint keys so merges need no reducer conflicts. Each node appends an audit event on entry and exit. Key names follow spec.md v0.2.

### 8.4 REST API (FastAPI)

| Method and path | Purpose | Req. |
| --- | --- | --- |
| POST /cases | Upload document(s); returns `case_id`, status RECEIVED | FR-ING-01..04 |
| GET /cases | List cases; filter by status, decision, date, doc type; paginated | FR-UI-01 |
| GET /cases/{id} | Case detail with all agent outputs and signed document URL | FR-UI-02/03 |
| GET /cases/{id}/audit | Timestamped audit events | FR-UI-05 |
| POST /cases/{id}/override | Human decision with reason; preserves original | FR-UI-04/06 |
| GET /review-queue | Escalated and NEEDS\_REVIEW cases | FR-UI-04 |
| POST /policies | Upload policy PDF; triggers Docling ingestion | FR-POL-01 |
| GET /policies | List policies, versions and ingestion status | FR-UI-10 |
| GET /cases/{id}/report | PDF case report *(bonus)* | FR-UI-09 |
| WS /cases/{id}/events | Live agent status *(bonus)* | FR-UI-08 |

### 8.5 External dependencies and data stores

| Component | Role | Options in source |
| --- | --- | --- |
| Object storage | Raw documents | S3 or MinIO |
| Task queue | Async pipeline trigger | Redis or Celery |
| Relational DB *\[Added\]* | Cases, audit log, members, claim history | Not specified (OQ-08) |
| Vector DB | Policy chunks | ChromaDB or Qdrant |
| Vision LLM | Classifier, OCR option, tamper cues | Claude Sonnet or GPT-4o |
| Docling | Policy PDF parsing and chunking | Docling |
| Observability | Traces, tokens, latency | LangSmith (bonus) |

## 9. Non-Functional Requirements

The source specifies few non-functional targets, so most below are *\[Added\]* or *\[Assumption\]* and should be confirmed before the spec is frozen.

**Sizing basis.** 85,000 documents a month is about 2,800 a day, or roughly 5 a minute across a 10-hour working day. Design for a 5x peak (about 25 a minute) *\[Assumption\]*.

| ID | Category | Requirement | Origin |
| --- | --- | --- | --- |
| NFR-PERF-01 | Latency | End-to-end time from upload to decision: p50 ≤ 2 min, p95 ≤ 5 min for single-document cases ("within minutes"). | Source / Assumption |
| NFR-PERF-02 | Throughput | Sustain 25 documents a minute with horizontal scaling of workers; the API returns the upload acknowledgement in under 2 s. | Assumption |
| NFR-PERF-03 | UI | Dashboard first load under 3 s for 10,000 cases (paginated); case detail under 2 s excluding image load. | Assumption |
| NFR-REL-01 | Reliability | Queue jobs are retried with backoff (default 3 attempts); exhausted jobs go to a dead-letter queue and the case is ESCALATED. | Added |
| NFR-REL-02 | Idempotency | Re-running a case never creates duplicate decisions; each run has a `run_id`. | Added |
| NFR-REL-03 | Availability | 99.5% monthly for ingestion API and UI in production; no document loss once the 202 is returned. | Assumption |
| NFR-SEC-01 | Data protection | Encrypt data in transit (TLS 1.2+) and at rest (object store, database, vector store). | Added |
| NFR-SEC-02 | Secrets | No credentials in code or images; secrets come from environment variables or a secret manager. | Source |
| NFR-SEC-03 | Access control | Role-based access; least privilege for services; signed, expiring URLs for document images. | Added |
| NFR-SEC-04 | PHI / PII handling | Redact or hash PHI in logs and traces; LLM traces to external services (for example LangSmith) must be configurable and off for production PHI unless approved. | Added |
| NFR-SEC-05 | Model vendor terms | LLM providers used on real PHI require an executed BAA and zero-retention settings; development uses synthetic data only. | Added (OQ-03) |
| NFR-AUD-01 | Auditability | Audit log is append-only and records agent inputs (by reference), outputs, model and prompt versions, thresholds and human actions with UTC timestamps. | Source / Added |
| NFR-AUD-02 | Retention | Retention periods for documents, audit logs and traces are configurable; default set by compliance (OQ-03). | Added |
| NFR-COMP-01 | Compliance | Design aligned to HIPAA safeguards and to the KYC findings under audit; exact framework confirmed by compliance. | Assumption |
| NFR-OBS-01 | Observability | Structured logs with `case_id` correlation; metrics for queue depth, per-agent latency, error rate, decision mix. | Added |
| NFR-OBS-02 | Tracing | LangSmith (or equivalent) traces every agent call with token count and latency per case. | Source (bonus) |
| NFR-QUAL-01 | Code quality | Clear agent separation, typed interfaces between agents, unit tests per agent, no hardcoded credentials. | Source |
| NFR-QUAL-02 | Reproducibility | Prompts, thresholds and schemas are versioned; the evaluation run is reproducible from a seed and config. | Added |
| NFR-AI-01 | Model governance | Every automated decision is explainable by agent outputs and justification; low-confidence cases always reach a human. | Source / Added |
| NFR-AI-02 | Fairness | Evaluate decision and fraud outcomes for disparities by available demographic proxies before production use. | Added |
| NFR-AI-03 | Prompt injection | Document text is treated as untrusted data; instructions inside documents must not alter agent behavior or tools. | Added |
| NFR-UX-01 | Accessibility | UI meets WCAG 2.1 AA for core flows. | Added |
| NFR-COST-01 | Cost | Track LLM cost per document; budget ceiling to be set by Operations (OQ-12). | Added |
| NFR-DEP-01 | Deployability | One-command local setup (Docker Compose) for API, worker, queue, MinIO, vector DB and UI. | Added |

## 10. Evaluation Plan, Dataset & Acceptance Criteria

The project passes if the overall weighted score is at least 70% and Decision Correctness is at least 60%. Both are measured on a labeled synthetic test set of at least 20 documents.

**Scoring**

| Criterion | Weight | How it is measured |
| --- | --- | --- |
| Classification accuracy | 20% | Share of test documents where Classifier `doc_type` equals ground truth |
| Extraction completeness | 20% | Share of required fields (ICD-10, CPT, amount, provider NPI, service date) extracted correctly across Claims-eligible documents |
| Policy retrieval quality | 15% | Manual spot-check that retrieved clauses are relevant to queried procedure codes, on at least 2 policy documents |
| Decision correctness | 25% | Share of final decisions (Approve / Reject / Escalate) matching ground truth |
| UI functionality | 10% | Dashboard loads, case detail renders, human override works end to end |
| Code quality and structure | 10% | Agent separation, typed interfaces, no hardcoded credentials (review checklist) |

**Test dataset requirements (deliverable 5)**

- At least 20 synthetic document images with ground-truth labels; recommended 30 or more for stable metrics *\[Added\]*.
- Mix of valid, invalid and fraudulent cases covering all six document types, including at least 2 UNKNOWN.
- Ground truth per document: `doc_type`, required extracted fields, expected KYC result, expected coverage, expected fraud risk, expected decision.
- Must exercise each decision branch: Approve, Reject (KYC fail, not covered, schema invalid), Escalate (fraud, low confidence).
- Include edge cases: expired ID, tampered ID, duplicate claim, missing field, rotated or low-quality scan, uncovered procedure, conflicting codes.
- A seeded mock member database and claim history consistent with the dataset.
- Documents are fully synthetic; no real PHI.

**Suggested distribution (20 cases) *\[Added\]***

| Outcome | Cases | Examples |
| --- | --- | --- |
| Approve | 6 | Valid claim forms, covered procedures, clean history |
| Reject | 6 | Expired ID, uncovered procedure, missing ICD-10 or NPI |
| Escalate | 6 | Duplicate claim, billing anomaly, tampered ID, low-quality scan |
| Unknown / other | 2 | Unrelated document, blank page |

**Acceptance criteria**

| ID | Criterion |
| --- | --- |
| AC-01 | Uploading a document returns a `case_id` and the case reaches DECIDED or NEEDS\_REVIEW without manual intervention. |
| AC-02 | Classification accuracy, extraction completeness and decision correctness are reported by an evaluation script and meet section 3 targets. |
| AC-03 | Decision correctness is at least 60% and overall weighted score is at least 70%. |
| AC-04 | The decision rule in FR-ORC-02 to FR-ORC-05 is covered by unit tests for every branch and precedence case. |
| AC-05 | A policy PDF uploaded at runtime is retrievable by the Policy Agent without redeploy, demonstrated on 2 policies. |
| AC-06 | A reviewer can open an escalated case, override it with a reason, and see the override in the audit log with the original decision retained. |
| AC-07 | Every case shows per-agent outputs and a timestamped audit trail in the UI. |
| AC-08 | No credentials are present in the repository; configuration is documented in the README. |
| AC-09 | The README walks through one end-to-end case from upload to decision. |

**Bonus evaluation.** If delivered, a confidence calibration plot compares Orchestrator confidence against observed accuracy (for example 5 bins); with only 20 cases, calibration is indicative and the sample size should be stated.

## 11. Bonus Features & Phasing

Core acceptance comes first: bonus items start only after Gate 4, and the phase plan below is a proposed sequence *\[Assumption\]*.

&#91;embedded content: delivery roadmap · 5 phases, 4 gates\]

The source lists six bonus challenges. None is required to pass, and each maps to requirements already written above.

| Bonus | Requirement | Value | Main dependency |
| --- | --- | --- | --- |
| Confidence calibration plot | FR-ORC-07, section 10 | Shows whether confidence can be trusted for auto-approval | Labeled test set; small sample caveat |
| Streaming updates (WebSockets) | FR-UI-08 | Live agent status in the UI | Event publishing from LangGraph nodes |
| Tamper detection (ELA) | FR-KYC-05 | Stronger KYC evidence for JPEG manipulation | JPEG inputs; false-positive review (R-06) |
| Multi-language support | FR-OCR-05 | Spanish and Hindi documents | Multilingual OCR model; OQ-16 |
| Audit export (PDF report) | FR-UI-09 | Regulator-ready case summary | Audit log completeness |
| LangSmith tracing | NFR-OBS-02 | Per-case trace, tokens and latency | PHI policy for external tracing (NFR-SEC-04) |

## 12. Risks, Dependencies & Mitigations

The highest risks are wrong automated decisions on real claims, PHI exposure through LLM vendors, and a decision rule with gaps.

| ID | Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| R-01 | Vision LLM misclassifies or hallucinates fields, causing wrong decisions | Medium | High | Confidence thresholds, schema validation, field-level confidence, human review for anything below 0.6; evaluation harness gates releases |
| R-02 | PHI sent to third-party LLM providers breaches policy or regulation | Medium | High | Synthetic data only in v1; BAA and zero-retention before real data; provider abstraction to allow a self-hosted model (OQ-03) |
| R-03 | Decision rule ambiguity (overlapping REJECT and ESCALATE conditions) | High | Medium | Explicit precedence (FR-ORC-05), config-driven thresholds, unit tests for every branch (AC-04), sign-off by Operations |
| R-04 | Small test set (20 cases) gives unreliable accuracy and calibration estimates | High | Medium | Expand to 30+ cases; report confidence intervals; state sample size with every metric |
| R-05 | Policy RAG retrieves wrong or outdated clause, yielding false coverage decisions | Medium | High | Restrict by policy ID and effective date; low-confidence on weak retrieval; cite clause and page for reviewer; manual spot-check |
| R-06 | Tamper detection produces false positives (compression artifacts, scans) or misses sophisticated forgery | Medium | Medium | Treat as a flag that lowers confidence and escalates, never a sole reason to reject; add ELA as supporting evidence |
| R-07 | Prompt injection through document text | Low | High | Treat OCR text as data; structured outputs; no tool access from content; red-team cases in the dataset |
| R-08 | Reviewer over-trust (automation bias) or override fatigue | Medium | Medium | Show evidence beside the decision; sample audits of auto-approved cases; track override rate |
| R-09 | LLM latency, rate limits or outages break the minutes-level SLA | Medium | Medium | Retries with backoff, queue buffering, timeouts, fallback model, escalation on failure |
| R-10 | Bias in fraud scoring or KYC matching against particular groups | Low | High | Fairness review (NFR-AI-02); deterministic, explainable scoring features; exclude sensitive attributes |
| R-11 | Synthetic data does not reflect real document variety (handwriting, stamps, fax noise) | High | Medium | Add noisy and degraded variants; plan a pilot on de-identified real documents under compliance approval |
| R-12 | Scope: seven agents, RAG, UI and dataset in one delivery | Medium | Medium | Phase delivery (section 11); bonus items only after core acceptance criteria pass |

**Dependencies.** Access to a vision LLM API and quota; member and claim-history data source (real or seeded mock); MediShield claim submission standard (OQ-04); two sample policy PDFs; object storage, queue and vector database infrastructure; compliance sign-off for any real-data pilot.

## 13. Open Questions & Decisions Needed

The PRD proceeds on the stated assumptions; the questions below change the spec or architecture if answered differently. Those marked Blocking should be answered before the spec is frozen.

| ID | Question | Why it matters | Proposed default | Blocking? |
| --- | --- | --- | --- | --- |
| OQ-01 | Where will the system run (MediShield cloud, on-premises, managed cloud) and which cloud? | Drives storage, queue, network and PHI controls | Docker Compose locally; cloud-agnostic design | No |
| OQ-02 | Which vision LLM and version is approved? The source names a dated Claude Sonnet version or GPT-4o; confirm current availability and a fallback. | Model ADR, cost, latency, accuracy | Claude Sonnet primary, GPT-4o fallback, behind one interface | Yes |
| OQ-03 | Which compliance regime and retention rules apply (HIPAA, state rules, KYC retention)? Is a BAA in place with LLM vendors? | Logging, tracing, data residency, vendor choice | Synthetic data only; HIPAA-aligned controls | Yes |
| OQ-04 | Where is MediShield's claim submission standard defined, and in what format? | FR-CLM-02 validation rules | Versioned JSON Schema authored from sample forms | Yes |
| OQ-05 | Confirm the doc type to agent routing matrix (section 7.2). | Graph edges, expected agent outputs per type | As proposed in 7.2 | Yes |
| OQ-06 | Confirm decision precedence when rules overlap (for example KYC failed and fraud 0.5). | Decision correctness against ground truth | Low confidence, then fraud escalation, then reject, then approve | Yes |
| OQ-07 | How is Orchestrator confidence defined (minimum, weighted mean, calibrated model)? | Calibration bonus, threshold behavior | Minimum of agent confidences | No |
| OQ-08 | What are the real sources for the member database and claim history, and is read access available? Which relational database? | Integration scope, KYC and Fraud agents | Seeded PostgreSQL mock | Yes |
| OQ-09 | Are multi-document claims (claim form plus discharge summary plus prescription) in scope, and how are documents linked? | Case model and Fraud cross-checks | One document per case in v1 | No |
| OQ-10 | What do MEDIUM and HIGH risk levels trigger (special investigations referral, hold on payment)? | Fraud thresholds and UI workflow | HIGH adds an SIU flag; both escalate | No |
| OQ-11 | May the system auto-reject, and what notification or appeal process follows? Do regulators require human review for denials? | Legal exposure, workflow | Auto-reject allowed in recommendation only; confirm | Yes |
| OQ-12 | What is the LLM cost budget per document? | Model choice, caching, batching | Track, no hard cap | No |
| OQ-13 | What authentication (SSO) and roles are required for the UI? | Security design | Role-based login with seeded users | No |
| OQ-14 | What business KPI targets and ROI model should the pilot be judged against (days per claim, automation rate, re-processing rate)? | Success metrics beyond the assignment score | Set after baseline pilot | No |
| OQ-15 | How should POLICY\_AMENDMENT documents be decided? The APPROVE rule assumes a claim and coverage. | Orchestrator rule variants by type | Amendment: KYC and policy consistency, escalate by default. Confirmed 2026-10-31 (D2): always escalate unless KYC fails; report accuracy per document category. | Yes |
| OQ-16 | Which languages are needed at launch? | OCR model selection | English only; Spanish and Hindi as bonus | No |
| OQ-17 | The source runs KYC, Claims and Policy in parallel, but the Policy Agent needs procedure codes from the Claims Agent. Sequence Policy after Claims, or let Policy extract codes itself? | Changes graph topology, latency and agent contracts | Policy runs after Claims inside the parallel block; KYC runs alongside both | Yes |

## 14. Follow-on Artifacts, Traceability & Glossary

This PRD is structured so each downstream document can cite requirement IDs.

**Candidate ADRs**

| ADR | Decision | Driven by |
| --- | --- | --- |
| ADR-001 | Vision LLM selection, provider abstraction and fallback | OQ-02, NFR-SEC-05, R-01 |
| ADR-002 | Orchestration: LangGraph state machine, parallel fan-out and aggregation | FR-ORC-01, section 8.3 |
| ADR-003 | Deterministic decision engine versus LLM-driven orchestrator | FR-ORC-05/06, R-03 |
| ADR-004 | Queue and execution model (Redis or Celery) and retry semantics | FR-ING-04, NFR-REL-01 |
| ADR-005 | Object storage and document retention | FR-ING-03, NFR-AUD-02 |
| ADR-006 | Vector database choice (ChromaDB or Qdrant) and chunking strategy with Docling | FR-POL-01..03 |
| ADR-007 | OCR strategy: Tesseract versus vision LLM, and text-layer shortcut | FR-OCR-01..04 |
| ADR-008 | Fraud scoring approach: rules and statistics, feature set, thresholds | FR-FRD-02/06, OQ-10 |
| ADR-009 | Relational data model for cases, audit log, members and claim history | OQ-08, FR-UI-05 |
| ADR-010 | Authentication, RBAC and PHI handling in logs and traces | NFR-SEC-01..05, OQ-13 |
| ADR-011 | Real-time updates (WebSocket) and UI state management | FR-UI-08 |
| ADR-012 | Evaluation harness, dataset generation and calibration method | Section 10 |

**Candidate specs**

- Technical spec per agent (prompt, schema, failure modes, tests) from section 7 and 8.2.
- API spec (OpenAPI) from section 8.4.
- Data model and migration spec from section 8.1 and 8.3.
- Policy RAG spec: ingestion pipeline, retrieval, evaluation.
- UI spec: screens, states, roles, wireframes from FR-UI.
- Test and evaluation spec: dataset schema, labeling guide, metrics, acceptance tests AC-01..AC-09.
- Security and compliance spec from section 9.

**Traceability.** Business goal (section 3) maps to requirements as: classification and routing to FR-CLS and FR-ING; extraction to FR-OCR and FR-CLM; KYC compliance to FR-KYC and NFR-AUD; coverage to FR-POL; fraud to FR-FRD; automated decisions to FR-ORC; human oversight to FR-UI; and acceptance to AC-01..AC-09.

**Glossary**

| Term | Meaning |
| --- | --- |
| KYC | Know Your Customer: identity and eligibility verification |
| ICD-10 | International Classification of Diseases, 10th revision (diagnosis codes) |
| CPT | Current Procedural Terminology (procedure codes) |
| NPI | National Provider Identifier (10-digit provider ID) |
| RAG | Retrieval-augmented generation |
| Docling | Document parsing library used to ingest and chunk policy PDFs |
| ELA | Error Level Analysis, a JPEG tamper-detection technique |
| PHI | Protected health information |
| SIU | Special investigations unit |
| LangGraph | Graph-based agent orchestration framework used for the state machine |
| BAA | Business associate agreement required for vendors handling PHI |
