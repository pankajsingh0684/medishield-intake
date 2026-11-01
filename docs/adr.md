# Architecture Decision Records: MediShield Multi-Agent Document Intake System

| Field | Value |
| --- | --- |
| Version | v0.2 |
| Date | 2026-10-31 |
| Derived from | PRD v0.1 section 14 (candidate ADRs) and `spec.md` |
| Status key | **Proposed** (awaiting sign-off), **Accepted**, **Superseded** |

**v0.2 (2026-10-31):** aligned with `spec.md` v0.2 after the dataset review. ADR-003, 006, 008 and 012 were extended; ADR-013 and ADR-014 are new. Phase 0 (steps 1 to 5) is already built; where an ADR changes something already built, the record says so and the change is made in plan Step 5b.

All records below are **Proposed**. Where the PRD left a question open, the record states the default chosen and the trigger that would reopen it.

## Index

| ADR | Decision | Status | Driven by |
| --- | --- | --- | --- |
| ADR-001 | Vision LLM selection, provider abstraction and fallback | Proposed | OQ-02, NFR-SEC-05, R-01 |
| ADR-002 | LangGraph state machine with parallel fan-out and join | Proposed | FR-ORC-01, spec 6 |
| ADR-003 | Deterministic decision engine; LLM writes justification only | Proposed | FR-ORC-05/06, R-03 |
| ADR-004 | Celery with Redis for asynchronous execution and retries | Proposed | FR-ING-04, NFR-REL-01 |
| ADR-005 | MinIO/S3 object storage with immutable raw documents | Proposed | FR-ING-03, NFR-AUD-02 |
| ADR-006 | Qdrant with Docling section-aware chunking and hybrid retrieval | Proposed | FR-POL-01..03 |
| ADR-007 | Tiered OCR: text layer, then Tesseract, then vision LLM fallback | Proposed | FR-OCR-01..04 |
| ADR-008 | Rule and statistics fraud scoring (noisy-OR) | Proposed | FR-FRD-02/06, OQ-10 |
| ADR-009 | PostgreSQL relational model with append-only audit log | Proposed | OQ-08, FR-UI-05 |
| ADR-010 | JWT authentication, RBAC and PHI-safe logging | Proposed | NFR-SEC-01..05, OQ-13 |
| ADR-011 | Redis pub/sub with WebSocket for live status; polling fallback | Proposed | FR-UI-08 |
| ADR-012 | Synthetic data generation and evaluation harness with calibration | Proposed | PRD section 10 |
| ADR-013 | Reference date from `received_at` and evaluation clock override | Proposed | FR-KYC, FR-CLM, spec 7.4 |
| ADR-014 | Supporting documents and policy amendments in the decision engine (D1, D2) | Proposed | FR-ORC-05, OQ-15 |

---

## ADR-001: Vision LLM selection, provider abstraction and fallback

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering

### Context
The Classifier, KYC tamper check, OCR fallback, Claims fallback extraction and Policy answer step need a vision-capable LLM. The assignment names a specific dated Claude Sonnet version or GPT-4o. Model versions retire, pricing and latency vary, and production PHI use requires vendor agreements (OQ-02, OQ-03). A single hard-wired provider would make outages and deprecations a pipeline failure (R-09).

### Decision
- Call models only through an in-repo **LLM gateway** exposing `complete_json(model, system, messages, images, schema)`.
- Default primary: Anthropic Claude Sonnet class model; fallback: OpenAI GPT-4o class model. Model IDs are environment configuration, never code constants.
- Structured outputs validated by Pydantic; one retry with the validation error, then the agent returns `ERROR`.
- Temperature 0; prompts versioned and stored per agent; model and prompt version recorded in every `agent_runs` row.
- Real PHI MUST NOT be sent to any provider until a BAA and zero-retention terms are in place.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Hard-code one provider | Outage or deprecation stops intake; no leverage on price |
| Self-hosted open vision model only | Lower accuracy on noisy scans expected; heavy GPU ops for v1; kept as a future gateway backend |
| LangChain model wrappers everywhere | Extra abstraction and version churn for little gain over a thin internal interface |

### Consequences
- Positive: provider swap is a config change; consistent logging, retries and redaction in one place; supports A/B evaluation of models on the labeled set.
- Negative: provider-specific features (for example native PDF input, prompt caching) need adapter code; two providers double the secret management.
- Follow-ups: verify current model availability before release; add per-model cost tracking (NFR-COST-01); decide self-hosted option if the BAA cannot be obtained.

---

## ADR-002: LangGraph state machine with parallel fan-out and join

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering

### Context
The pipeline has conditional routing after classification, parallel specialists, a fan-in barrier, and failure routes to human review. The PRD specifies LangGraph and the state sequence RECEIVED, CLASSIFIED, parallel KYC/Claims/Policy, FRAUD_CHECK, AGGREGATED, DECIDED. The source runs Policy in parallel with Claims although Policy needs Claims' procedure codes (OQ-17).

### Decision
- Implement the pipeline as one compiled LangGraph `StateGraph` with a typed `GraphState`.
- Specialists write disjoint state keys; list fields use additive reducers.
- Routing is a pure function over `doc_type` using a table (spec 6.2).
- **Policy runs after Claims** inside the parallel block; KYC runs alongside both (default for OQ-17). The join node waits for all routed nodes.
- A node wrapper adds audit events, timeouts, retries and error-to-envelope conversion. Failures route to `mark_failed` which sets `FAILED` and places the case in the review queue.
- Agent modules do not import each other; they only read and write the state.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Strict parallel Policy extracting its own codes from OCR | Duplicates Claims logic and risks inconsistent codes between agents |
| Hand-written asyncio orchestration | Re-implements checkpointing, fan-in and tracing that LangGraph provides |
| LLM-driven supervisor agent that decides the next step | Non-deterministic routing; harder to test and audit (conflicts with ADR-003) |

### Consequences
- Positive: explicit, testable topology; native fan-in; easy tracing; matches the PRD diagram and states.
- Negative: latency adds Policy time after Claims (about one retrieval and one LLM call); LangGraph version coupling.
- Follow-ups: pin LangGraph version; enable a checkpointer only if mid-run resume is needed (v1 reruns from the start).

---

## ADR-003: Deterministic decision engine; LLM writes justification only

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering, Operations

### Context
The PRD decision rule has overlapping conditions: a case can match both REJECT (KYC failed) and ESCALATE (fraud at or above 0.3). Decisions affect payments and are subject to audit and regulation (R-03, OQ-06, OQ-11). LLM-made decisions would be hard to reproduce and defend.

### Decision
- Implement `decide()` as a pure function in `packages/decision`, taking typed agent outputs and a versioned threshold config.
- Precedence: **R1** any agent error or confidence below 0.6 gives ESCALATE; **R2** fraud score at or above 0.3 gives ESCALATE; **R3** KYC failed, procedure not covered or schema invalid gives REJECT; **R4** otherwise APPROVE.
- Skipped agents are "not applicable" and do not count as failures or passes.
- Orchestrator confidence is the minimum applicable agent confidence, with caps defined in spec 7.8 (default for OQ-07).
- An LLM drafts the human-readable justification from the `rule_trace`, and cannot alter the decision.
- Thresholds are configuration and a snapshot is stored with each decision.
- The system produces a decision recommendation; reviewers can override any decision. No automatic outbound notification of rejection in v1 (OQ-11).

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| LLM orchestrator decides from summaries | Not reproducible; cannot unit test every branch; weak audit story |
| Weighted score combining all agents | Hides hard rules (KYC failure must not be averaged away); harder to explain |
| Reject before escalate on overlap | Auto-rejects possibly fraudulent or unreliable cases without human view; riskier for legal exposure |

### Consequences
- Positive: exhaustive unit and property tests (AC-04); full rule trace in the UI and audit log; thresholds tunable without code changes.
- Negative: rules may be too coarse; precedence needs Operations sign-off (OQ-06); more cases escalate on overlap.
- Follow-ups: track escalation rate and override rate; revisit with a calibrated model only after enough labeled outcomes exist.

**Amendment v0.2.** Agent confidence means certainty of extraction, not completeness: a missing required field gives `schema_valid=false` at normal confidence, so rule R3 can reject it. Setting confidence to 0 would let rule R1 escalate first and no incomplete claim could ever be rejected. Warning and low-severity flags (`ID_EXPIRING_SOON`, `NPI_CHECKSUM`) never change a decision. See also ADR-014.

---

## ADR-004: Celery with Redis for asynchronous execution and retries

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** Platform

### Context
Uploads must return immediately while processing takes tens of seconds. The PRD names Redis or Celery. Peak sizing is about 25 documents per minute (NFR-PERF-02) with retries, dead-lettering and no lost documents after acknowledgement (NFR-REL-01/03).

### Decision
- Use **Celery** workers with **Redis** as broker and result backend; one task `run_pipeline(case_id)`, separate queues `pipeline` and `policy_ingest`.
- `acks_late=True`, `task_reject_on_worker_lost=True`, 3 attempts with exponential backoff and jitter, a dead-letter queue for exhausted tasks that sets the case to `FAILED` and surfaces it in the review queue.
- Tasks are idempotent: each execution has a `pipeline_run` ID, and agent outputs are keyed by (`case_id`, `pipeline_run`, `agent`).
- Redis also carries pub/sub events (ADR-011). Persistence (AOF) enabled for the broker.
- Concurrency is sized from LLM rate limits, and scaled by queue depth.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| FastAPI BackgroundTasks | Lost on process restart; no retries or scaling |
| RQ or Dramatiq | Fewer features for routing, retries and monitoring; the team has less precedent |
| Kafka or SQS | Heavier than needed for v1 volume; revisit at production scale |
| Temporal | Strong durability but extra platform to run; kept as an option if long-running human-in-the-loop workflows are added |

### Consequences
- Positive: simple local setup; mature retry and monitoring (Flower, Prometheus exporter).
- Negative: Redis durability is weaker than a log-based broker; long LLM calls need generous visibility timeouts; async state is split between Celery and the database.
- Follow-ups: define alerting on queue depth and DLQ size; load test at 5x peak.

---

## ADR-005: MinIO/S3 object storage with immutable raw documents

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** Platform, Compliance

### Context
Raw submissions are evidence for KYC audits (3 audits ongoing) and must be retrievable unchanged. Files range from images to multi-page PDFs and TIFFs. Retention rules are not yet defined (OQ-03).

### Decision
- Store the original upload byte-for-byte in S3-compatible storage (MinIO locally, S3 in production) under `raw/{yyyy}/{mm}/{case_id}/original.{ext}` with SHA-256 recorded in the database.
- Enable bucket versioning and server-side encryption; production uses object lock (compliance mode) for the configured retention period.
- Derived artifacts (page renders, OCR overlays, report PDFs) go under a separate prefix and can be regenerated.
- The API never exposes object keys; the UI receives pre-signed URLs valid for 10 minutes.
- Retention and legal hold are configuration (default set by Compliance).

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Store files in PostgreSQL | Bloat and backup cost for large binaries |
| Local filesystem | Not shared across workers; no versioning or lock |
| Rewrite or normalize originals | Destroys evidence integrity; derived copies serve that need |

### Consequences
- Positive: auditable originals, simple duplicate detection by checksum, horizontal scalability.
- Negative: object lock limits deletion (right-to-erasure requests need a policy); extra component locally.
- Follow-ups: confirm retention periods and erasure handling with Compliance.

---

## ADR-006: Qdrant with Docling section-aware chunking and hybrid retrieval

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering

### Context
Coverage decisions depend on locating the right clause and exclusions for CPT and ICD-10 codes in long policy PDFs with tables and sections. Wrong or outdated clauses cause false coverage decisions (R-05). The PRD requires real-time upload through Docling and ChromaDB or Qdrant, tested on at least two policies.

### Decision
- Parse PDFs with **Docling** into structured content with headings, tables and page numbers.
- Chunk on heading boundaries (400 to 800 tokens, 80 overlap), keeping tables intact when practical; tag chunks as coverage, exclusion, definition or schedule; store `policy_id`, `version`, `section_path`, `page`, effective dates.
- Store vectors in **Qdrant** (dense plus sparse vectors) with payload filters for policy and effective date.
- Retrieval: per-code queries, hybrid search, reciprocal rank fusion, rerank to the top 5, then the LLM answers only from retrieved text; cited clause text must appear verbatim in a retrieved chunk.
- Step 0 before retrieval: the sample policies carry a machine-readable "Excluded CPT Code Ranges" table. It is parsed at ingestion into a `policy_exclusions` table and looked up deterministically per CPT code; a hit means `covered=False` with confidence 0.95 and no LLM call. Retrieval and the LLM handle codes that are not excluded.
- Weak retrieval returns `covered=None` and low confidence so the case escalates.
- Embeddings default to an open `bge-small` class model run locally, avoiding sending policy text to extra vendors.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| ChromaDB | Simpler, but weaker metadata filtering, hybrid search and production story |
| pgvector in PostgreSQL | One fewer service, but hybrid search and filtering are less mature; viable if operations prefer fewer components |
| Fixed-size token chunks | Splits clauses from their exclusions and tables |
| Long-context stuffing of whole policies | Cost, latency and weaker citation guarantees |

### Consequences
- Positive: filter-by-policy-and-date correctness; verifiable citations; real-time ingestion without redeploy (AC-05).
- Negative: an extra service to run; ingestion quality depends on PDF structure; rerank adds latency.
- Follow-ups: build a CPT description lookup; manual relevance review on two sample policies (PRD section 10); revisit pgvector if operational simplicity outweighs features.
- v0.2: the exclusion table makes the most common reject path exact and cheap. The two policies come from the existing generator scripts (Gold and Silver), not new samples.

---

## ADR-007: Tiered OCR: text layer, then Tesseract, then vision LLM fallback

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering

### Context
Inputs mix digital PDFs, clean scans, phone photos and faxes. The PRD allows Tesseract or a vision LLM. Pure LLM OCR is costly and slower; pure Tesseract is weak on skewed or low-quality images and handwriting. Bounding boxes are needed for reviewer evidence (FR-CLM-04). Multilingual support is a bonus (FR-OCR-05).

### Decision
1. If a PDF page has a text layer, extract it directly and skip OCR.
2. Else deskew and rotate-correct at 300 DPI, then run **Tesseract** to get words, boxes and confidences.
3. If mean confidence is below 0.70 or required fields are missing, invoke the **vision LLM** for structured field extraction and merge by per-field confidence.
4. Normalize everything into one `OcrPayload` with a canonical field vocabulary; downstream agents consume only this payload.
5. Multilingual: Tesseract language packs (Spanish, Hindi) as a bonus path; revisit a dedicated multilingual OCR model if accuracy is insufficient.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Vision LLM for every page | Highest cost and latency; no native word boxes |
| Cloud OCR service (Textract, Document AI) | Sends PHI to another vendor; additional BAA; kept as a swappable backend |
| Tesseract only | Fails the extraction completeness target on poor scans |

### Consequences
- Positive: cheap and fast for the common case; LLM spend only where needed; boxes available for evidence highlighting.
- Negative: merging logic adds complexity; two code paths to test; image preprocessing parameters need tuning.
- Follow-ups: measure fallback rate on the dataset; add handwriting cases; evaluate cloud OCR if fallback rate is high.

---

## ADR-008: Rule and statistics fraud scoring (noisy-OR)

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering, Operations (SIU)

### Context
The Fraud agent must score claims against patient history, frequency and provider billing patterns, and output a score where 0.3 is the escalation threshold. There is no labeled production fraud data, and the score must be explainable to reviewers and auditors (NFR-AI-01, R-10, OQ-10).

### Decision
- Compute `fraud_score = 1 - Π(1 - wᵢ·sᵢ)` over named detectors with default weights: duplicate claim 0.90, frequency spike 0.45, provider billing outlier 0.40, amount outlier 0.35, code mismatch 0.40 (includes an obstetric CPT with a non-obstetric diagnosis), tamper signal 0.40, identity mismatch 0.50, near-threshold amount 0.35, date conflict 0.45, readmission within 30 days 0.45. Scores are rounded to 4 decimal places before threshold comparison.
- History rows carry a `kind` (PRIOR_CLAIM, EPISODE_CLAIM, PRIOR_STAY), stored as text with a check constraint and mapped to a StrEnum, so that date-conflict and readmission detectors have the earlier record they need. The first submission is never flagged as a duplicate, so processing order matters; duplicates are found by claim number or provider, date and code set, because a rescanned copy has a different file hash.
- Detectors are deterministic and statistical (z-scores, MAD, percentiles over `claim_history`); weights are configuration.
- Each anomaly reports evidence and its contribution; the LLM may only write an explanation.
- Risk levels: LOW below 0.30, MEDIUM from 0.30 to below 0.60, HIGH at or above 0.60 (only the 0.30 cut is from the PRD). Both MEDIUM and HIGH escalate; HIGH adds an SIU tag.
- Sensitive demographic attributes are not used as features.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Supervised ML model (gradient boosting) | No labeled fraud data; poor explainability; revisit after real outcomes accumulate |
| LLM judging fraud from text | Not reproducible or calibrated; susceptible to prompt injection |
| Isolation forest or other unsupervised model only | Hard to explain per claim; needs sufficient history |

### Consequences
- Positive: transparent, testable, tunable; works with small seeded data; satisfies the 0.3 rule exactly.
- Negative: weights are expert guesses until validated; cold-start members have weaker baselines (confidence is reduced).
- Follow-ups: validate weights against labeled outcomes; fairness review (NFR-AI-02); define SIU workflow (OQ-10).
- v0.2: the four new detectors come from the dataset review; weights are expert guesses and are tuned only on the dev split.

---

## ADR-009: PostgreSQL relational model with append-only audit log

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** Platform, Compliance

### Context
The system needs cases, agent outputs, decisions, overrides, mock member and claim history data, and an audit trail regulators can rely on. The PRD does not specify a relational database (OQ-08). Overrides must preserve the original decision (FR-UI-06).

### Decision
- Use **PostgreSQL 16** with Alembic migrations.
- Tables: `cases`, `agent_runs` (typed output in JSONB), `decisions`, `overrides`, `audit_events`, `members`, `claim_history`, `policies`, `users` (spec 4).
- `audit_events` is append-only: no UPDATE or DELETE privileges for the application role, plus a trigger that rejects mutation.
- Decisions and overrides are separate rows; an override never edits the original decision.
- Agents use a read-only database role for `members` and `claim_history`; v1 data is seeded mock data behind a repository interface so real adapters can replace it.
- Timestamps are UTC (`timestamptz`).

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| MongoDB or document store | Agent outputs fit JSONB; relational integrity and queries (dashboard filters, joins) matter more |
| SQLite | No concurrent workers or role-based privileges |
| Event sourcing for everything | Overhead for v1; the audit table gives the required trace |

### Consequences
- Positive: strong integrity, simple dashboard queries, easy audit export, JSONB flexibility for agent schemas.
- Negative: JSONB schema evolution needs discipline (version fields); append-only enforcement requires careful role setup.
- Follow-ups: define retention and partitioning for `audit_events`; add hash chaining if stronger tamper evidence is required by Compliance.

---

## ADR-010: JWT authentication, RBAC and PHI-safe logging

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** Security, Platform

### Context
Operations staff override financial decisions on PHI-bearing cases. The PRD requires no hardcoded credentials and implies HIPAA-style controls; SSO and roles are not yet defined (OQ-13). Traces and logs can leak PHI to external services (NFR-SEC-04).

### Decision
- API authentication with short-lived **JWT** access tokens; v1 uses local users (argon2 password hashes) with a pluggable OIDC provider interface for later SSO.
- Roles: REVIEWER, SUPERVISOR, AUDITOR (read-only), ADMIN, enforced in FastAPI dependencies and covered by tests per role.
- Service-to-service upload uses a scoped service token.
- Secrets only from environment or a secret manager; CI secret scanning.
- Structured logs pass through a redaction filter (member ID, DOB, names, policy numbers); `PHI_LOG_REDACTION=true` by default.
- External tracing (LangSmith) is disabled by default and can be enabled only for synthetic data or after approval.
- Document access via pre-signed URLs with a 10-minute lifetime.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Session cookies with server-side sessions | Extra state; JWT fits API plus WebSocket use; cookies remain an option for the web app |
| SSO only from day one | Identity provider is unknown; blocks local demo |
| No roles in v1 | Overrides need attribution and separation from auditors (FR-UI-06/07) |

### Consequences
- Positive: attributable overrides, least privilege, safe demo defaults.
- Negative: JWT revocation needs a deny list or short TTL; local user management is temporary.
- Follow-ups: choose the SSO provider; define session and MFA policy; document PHI data flow diagram for compliance review.

---

## ADR-011: Redis pub/sub with WebSocket for live status; polling fallback

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** Web, Platform

### Context
Reviewers benefit from seeing each agent complete in real time (bonus FR-UI-08), but the core UI must work without it. Redis is already in the stack for Celery.

### Decision
- Each node wrapper publishes `{case_id, agent, status, ts}` to Redis channel `case:{id}`.
- The API exposes `WS /cases/{id}/events`, authenticated with the same JWT; it relays events and closes when the case reaches a terminal state.
- The UI updates the agent timeline from events and falls back to polling every 5 seconds if the socket fails, so correctness never depends on WebSockets.
- Events are notifications only; the database remains the source of truth, and the UI refetches on completion.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Server-sent events | Simpler, one-way, but WebSocket was named in the PRD and allows future interaction |
| Polling only | Works, but loses the live status bonus |
| Dedicated message service (for example Pusher) | External dependency and PHI concerns |

### Consequences
- Positive: low latency updates with no new infrastructure; graceful degradation.
- Negative: pub/sub is fire-and-forget (missed events possible); sockets add connection management at scale.
- Follow-ups: cap concurrent sockets per user; consider SSE if proxies block WebSockets.

---

## ADR-012: Synthetic data generation and evaluation harness with calibration

**Status:** Proposed  **Date:** 2026-10-30  **Owners:** ML engineering

### Context
Grading and release depend on measured accuracy on a labeled set of at least 20 documents covering valid, invalid and fraudulent cases. Real PHI cannot be used (A-03). With few samples, metrics are noisy and confidence calibration is only indicative (R-04, R-11).

### Decision
- Use the project's four existing generator scripts (`generate_docs.py`, `generate_gold_policy.py`, `generate_silver_policy.py`, `generate_unknown.py`; Pillow, numpy and fpdf2) rather than writing a new one: 151 PNGs from 30 patient clusters, 4 unknown documents and two policy PDFs. They are seeded, run once, and then frozen with the output committed, because stub LLM fixtures are keyed by input hash and the fonts are Windows-only.
- The generator also writes `truth.json` (true field values per document) and `clusters.json`, and an `expected_decision` per document by a fixed table (unknown, amendment, fraud-labeled or tampered ID: ESCALATE; expired ID, uncovered or incomplete claim, incomplete prescription: REJECT; otherwise APPROVE).
- Produce `labels.jsonl` with expected type, fields, KYC result, coverage, fraud level and decision, plus matching seeded `members` and `claim_history`.
- 155 documents (about 94 APPROVE, 18 REJECT, 43 ESCALATE). A gap-filling step adds any missing scenario, such as a prompt-injection document. The set is split about 70/30 into dev and holdout by patient cluster, stratified by scenario, and the split is committed; tuning uses dev and the final report uses holdout.
- Evaluation harness runs the real pipeline and reports classification accuracy, extraction completeness, decision correctness (with confusion matrix and per-scenario breakdown), latency percentiles and optional calibration (5-bin reliability diagram, ECE). Reports include sample sizes and confidence intervals, and break results down per scenario, per document category and per split.
- Retrieval quality uses a manual 0 to 2 rubric sheet over at least two policies.
- Release gate: the evaluation script fails if decision correctness is below 0.60 or the weighted score is below 0.70 (AC-03). Prompt or model changes require a passing run.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Public document datasets only | Not tailored to MediShield forms; no linked members and claims for KYC and fraud |
| Hand-made 20 images | Not reproducible; limited scenario coverage |
| Real redacted documents | Compliance approval required first; planned for a pilot (R-11) |

### Consequences
- Positive: reproducible, safe, scenario-complete evaluation; regression protection for prompts and models.
- Negative: synthetic documents are cleaner than real ones, so scores can be optimistic; generator maintenance; the 30 policy amendments all escalate, so overall decision accuracy is inflated unless it is also reported per document category.
- Follow-ups: add a de-identified real-document pilot set under compliance approval; expand the dataset to hundreds before judging calibration.

---

## ADR-013: Reference date from `received_at` and evaluation clock override

**Status:** Proposed  **Date:** 2026-10-31  **Owners:** Backend engineering, ML engineering

### Context
Expiry, policy-active and service-date recency checks need a date. The generated dataset is dated 2025, so with the wall clock almost every claim would fail the 365-day rule and every ID would look expired. The dataset review found this (finding 13).

### Decision
- All time-dependent checks use `cases.received_at`, never the system clock. In production it is the upload time.
- In evaluation the runner may set `received_at` to each label's `reference_date` (the cluster's treatment date) only when `ALLOW_RECEIVED_AT_OVERRIDE=true`. The override is refused when the environment is production.
- The decision is stored with the reference date used, so a replay gives the same result.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Use the wall clock | Dataset becomes invalid within days and results change over time |
| A global `AS_OF_DATE` setting | One date cannot fit documents from different periods; a per-case value is simpler to audit |
| Regenerate the dataset with current dates | Pixels and hashes change; stub fixtures break |

### Consequences
- Positive: reproducible evaluation; no wall-clock flakiness in tests.
- Negative: one more setting and a guarded code path.
- Follow-ups: tests that the override is refused in production; Step 5b adds `cases.received_at` through a second migration.

---

## ADR-014: Supporting documents and policy amendments in the decision engine (D1, D2)

**Status:** Proposed (D1 and D2 both confirmed by the product owner on 2026-10-31; awaiting Operations sign-off)  **Date:** 2026-10-31  **Owners:** ML engineering, Operations

### Context
Discharge summaries and prescriptions have no procedure-and-amount claim to check against coverage, and the dataset has 30 policy amendments. The PRD leaves both open (OQ-15). D1 and D2 are confirmed.

### Decision
- **D1 (confirmed 2026-10-31).** Discharge summaries and prescriptions are supporting documents. They get extraction, member match and fraud checks, but no Policy Agent run. They are REJECTED only for KYC failure or `schema_valid=false`; otherwise APPROVE means "document accepted".
- **D2 (confirmed 2026-10-31).** Policy amendments always ESCALATE for human confirmation unless KYC fails. Evaluation reports decision accuracy per document category in addition to overall.
- Precedence R1 to R4 is unchanged; these are document-type variants inside the pure decision function.

### Alternatives considered
| Option | Why not chosen |
| --- | --- |
| Run coverage on every document type | Prescriptions and discharge summaries lack the data coverage needs; would produce false escalations |
| Let the model decide amendments | Not reproducible; amendments change policy terms and need a human |

### Consequences
- Positive: simple, testable rules; routing matches the data.
- Negative: about 28% of labels are ESCALATE because of amendments, which inflates overall accuracy.
- Follow-ups: confirm with Operations; to reverse D1 change the two "no" cells in spec 6.2 and the variants in 7.8, then update the expected-decision table in spec section 11 and relabel before Step 5c.

---

## Decision dependencies

```
ADR-001 (LLM gateway) ──> ADR-003 (justification only), ADR-007 (OCR fallback), ADR-006 (policy answer)
ADR-002 (graph) ───────> ADR-003, ADR-004 (execution), ADR-011 (events)
ADR-009 (database) ────> ADR-003 (decisions), ADR-008 (history), ADR-010 (users)
ADR-005 (storage) ─────> ADR-007 (inputs), ADR-010 (signed URLs)
ADR-012 (evaluation) ──> gates changes to ADR-001, ADR-003, ADR-006, ADR-007, ADR-008
ADR-013 (reference date) ──> ADR-009 (cases.received_at), ADR-012 (runner), KYC and Claims checks
ADR-014 (D1, D2) ──> ADR-003 (variants), ADR-012 (expected decisions)
```

## Process

- New decisions use the template below and the next number; superseded records are kept with status **Superseded by ADR-NNN**.
- A record moves from Proposed to Accepted when its owner and the named stakeholder (Operations for ADR-003 and ADR-008, Compliance for ADR-005, 009, 010) approve.

```
## ADR-NNN: Title
Status / Date / Owners
### Context
### Decision
### Alternatives considered (table)
### Consequences (positive, negative, follow-ups)
```
