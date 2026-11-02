# Technical Specification: MediShield Multi-Agent Document Intake System

| Field | Value |
| --- | --- |
| Version / status | v0.2, draft (aligned with the generated dataset; see Changelog at the end) |
| Derived from | PRD v0.1 (requirement IDs FR-, NFR-, AC-, OQ- refer to the PRD) |
| Companion | `adr.md` (decisions ADR-001 to ADR-012) |
| Date | 2026-10-30 |

Conventions: **MUST / SHOULD / MAY** follow RFC 2119. Items tagged **[Default]** implement a PRD default for an open question and change if the question is answered differently (see section 17).

---

## 1. Purpose and scope

This spec defines how the PRD is built: repository layout, runtime components, data model, agent contracts, graph topology, algorithms, APIs, UI, configuration, testing and deployment. It targets the v1 deliverable: ingestion API, seven-stage agent pipeline (Classifier, OCR, KYC, Claims, Policy, Fraud, Orchestrator), Policy RAG, case management UI, synthetic dataset and evaluation harness. All development data is synthetic (PRD A-03).

## 2. System architecture

### 2.1 Runtime components

| Component | Tech | Responsibility |
| --- | --- | --- |
| `api` | FastAPI (Python 3.11+), Uvicorn | Upload, case/policy/override endpoints, WebSocket events, auth |
| `worker` | Celery workers, Redis broker | Run the LangGraph pipeline per case; ingest policy PDFs |
| `db` | PostgreSQL 16 | Cases, agent runs, audit log, members, claim history, policies metadata |
| `objectstore` | MinIO (S3 API) | Raw documents, page renders, policy PDFs, report PDFs |
| `vectordb` | Qdrant | Policy chunk embeddings and metadata filters |
| `cache/queue` | Redis | Celery broker/result backend, pub/sub for live events |
| `web` | Next.js 14 (App Router), TypeScript | Case management UI |
| `llm gateway` | In-process Python module | Provider abstraction for vision/text LLM calls with retry, timeout, logging |

### 2.2 Request flow

1. `POST /cases` stores the file in MinIO, inserts a `cases` row (`RECEIVED`), enqueues `run_pipeline(case_id)`, returns `202` with `case_id` (FR-ING-01..04).
2. A worker loads the file, renders pages to images, and invokes the compiled LangGraph.
3. Each node writes its typed output to the `agent_runs` table and appends audit events before returning state.
4. The Orchestrator node writes `decisions` and sets the case status.
5. The API publishes events on Redis pub/sub channel `case:{id}`; the UI subscribes via WebSocket (bonus FR-UI-08).

### 2.3 Repository layout

```
medishield-intake/
  apps/
    api/            # FastAPI app: routers, auth, schemas, deps
    worker/         # Celery app and tasks
    web/            # Next.js UI
  packages/
    core/           # shared domain: enums, pydantic models, config, llm gateway
    agents/         # classifier, ocr, kyc, claims, policy, fraud, orchestrator
    graph/          # LangGraph state, builder, routing, node wrappers
    rag/            # docling ingestion, chunking, embeddings, retriever
    decision/       # deterministic decision engine (pure functions)
    forensics/      # ELA and image tamper heuristics
    eval/           # dataset loader, metrics, calibration, report
  data/
    synthetic/      # images, labels.jsonl, mock members/claims seeds
    policies/       # sample policy PDFs
    schemas/        # claim_submission_standard.v1.json
  infra/            # docker-compose.yml, Dockerfiles, migrations (alembic)
  docs/             # README, architecture diagram, walkthrough
```

Rule: `agents/*` MUST NOT import each other. They exchange data only through the graph state and typed models in `core` (NFR-QUAL-01).

## 3. Configuration

All configuration comes from environment variables, loaded into a typed `Settings` object (pydantic-settings). No secrets in code or images (NFR-SEC-02).

| Variable | Purpose | Default |
| --- | --- | --- |
| `DATABASE_URL` | Postgres DSN | none (required) |
| `REDIS_URL` | Broker and pub/sub | none (required) |
| `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | MinIO/S3 | none (required) |
| `QDRANT_URL`, `QDRANT_API_KEY` | Vector DB | none (required) |
| `LLM_PROVIDER` | `stub`, `groq`, `anthropic` or `openai` **[Decision, ADR-001 v0.2]**: `stub` for development and tests, `groq` for the real evaluation | `stub` |
| `LLM_VISION_MODEL`, `LLM_TEXT_MODEL` | Model IDs **[Default, ADR-001]** | set per environment |
| `LLM_FALLBACK_PROVIDER`, `LLM_FALLBACK_MODEL` | Optional fallback; empty means no fallback | empty |
| `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Provider keys (all optional; only the selected provider's key is needed) | none |
| `LLM_RECORD_FIXTURES` | Stub gateway records a fixture from a real response | `false` |
| `EMBEDDING_MODEL` | Policy embeddings | `BAAI/bge-small-en-v1.5` |
| `THRESH_FRAUD_ESCALATE` | Fraud escalation cut | `0.30` |
| `THRESH_FRAUD_HIGH` | HIGH risk cut | `0.60` |
| `THRESH_AGENT_CONFIDENCE` | Min agent confidence | `0.60` |
| `THRESH_CLASSIFY_REVIEW` | Classifier review cut | `0.60` |
| `MAX_UPLOAD_MB` | Upload limit | `25` |
| `PIPELINE_TIMEOUT_S` | Per-case timeout | `300` |
| `AGENT_TIMEOUT_S` | Per-agent timeout | `90` |
| `JWT_SECRET`, `JWT_TTL_MIN` | UI/API auth | none, `60` |
| `LANGSMITH_ENABLED`, `LANGSMITH_API_KEY` | Tracing (bonus) | `false` |
| `PHI_LOG_REDACTION` | Redact PHI in logs/traces | `true` |
| `APP_ENV` | Runtime environment: `development`, `test` or `production` | `development` |
| `ALLOW_RECEIVED_AT_OVERRIDE` | Lets the evaluation runner set `cases.received_at` (see 7.4); refused when `APP_ENV=production` (startup fails if both are set) | `false` |
| `NPI_LUHN_STRICT` | Fail validation on a bad NPI checksum (the synthetic NPIs are not checksum-valid) | `false` |
| `NEAR_THRESHOLD_LOW`, `NEAR_THRESHOLD_HIGH` | Amount band for the structuring detector | `9500`, `10000` |
| `DATE_CONFLICT_DAYS` | Prescription later than the episode claim by more than this | `30` |
| `READMISSION_DAYS` | Admission within this many days of a prior discharge | `30` |

Thresholds are versioned: each decision stores a `config_snapshot` JSON with the values used (FR-ORC-09).

## 4. Data model (PostgreSQL)

```sql
-- enums
CREATE TYPE case_status AS ENUM
  ('RECEIVED','CLASSIFIED','PROCESSING','FRAUD_CHECK','AGGREGATED',
   'DECIDED','NEEDS_REVIEW','OVERRIDDEN','FAILED');
CREATE TYPE decision_kind AS ENUM ('APPROVE','REJECT','ESCALATE');
CREATE TYPE doc_type AS ENUM
  ('CLAIM_FORM','ID_DOCUMENT','DISCHARGE_SUMMARY','PRESCRIPTION','POLICY_AMENDMENT','UNKNOWN');
CREATE TYPE risk_level AS ENUM ('LOW','MEDIUM','HIGH');
CREATE TYPE user_role AS ENUM ('REVIEWER','SUPERVISOR','AUDITOR','ADMIN');

CREATE TABLE cases (
  case_id        UUID PRIMARY KEY,
  status         case_status NOT NULL,
  channel        TEXT,                       -- email|mobile|scanner|api
  doc_type       doc_type,
  object_key     TEXT NOT NULL,              -- raw document location
  sha256         CHAR(64) NOT NULL,
  mime_type      TEXT NOT NULL,
  page_count     INT,
  duplicate_of   UUID REFERENCES cases(case_id),
  member_ref     TEXT,                       -- resolved by KYC
  received_at    TIMESTAMPTZ NOT NULL DEFAULT now(),  -- reference date for expiry/recency checks
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON cases (status, created_at DESC);
CREATE INDEX ON cases (sha256);

CREATE TABLE agent_runs (
  run_id         UUID PRIMARY KEY,
  case_id        UUID NOT NULL REFERENCES cases,
  pipeline_run   UUID NOT NULL,              -- groups one end-to-end execution
  agent          TEXT NOT NULL,              -- classifier|ocr|kyc|claims|policy|fraud|orchestrator
  agent_version  TEXT NOT NULL,
  status         TEXT NOT NULL,              -- OK|ERROR|SKIPPED
  model          TEXT,
  prompt_version TEXT,
  confidence     NUMERIC(4,3),
  output         JSONB NOT NULL,
  error          TEXT,
  tokens_in      INT, tokens_out INT,
  started_at     TIMESTAMPTZ NOT NULL,
  finished_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE decisions (
  decision_id    UUID PRIMARY KEY,
  case_id        UUID NOT NULL REFERENCES cases,
  pipeline_run   UUID NOT NULL,
  decision       decision_kind NOT NULL,
  confidence     NUMERIC(4,3) NOT NULL,
  justification  TEXT NOT NULL,
  rule_trace     JSONB NOT NULL,             -- ordered rules evaluated and outcome
  config_snapshot JSONB NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE overrides (
  override_id    UUID PRIMARY KEY,
  case_id        UUID NOT NULL REFERENCES cases,
  user_id        UUID NOT NULL,
  from_decision  decision_kind,
  to_decision    decision_kind NOT NULL,
  reason         TEXT NOT NULL CHECK (length(reason) >= 10),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- append-only: revoke UPDATE/DELETE; enforced by trigger
CREATE TABLE audit_events (
  event_id       BIGSERIAL PRIMARY KEY,
  case_id        UUID NOT NULL,
  ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_type     TEXT NOT NULL,              -- SYSTEM|AGENT|USER
  actor          TEXT NOT NULL,              -- agent name or user id
  event_type     TEXT NOT NULL,              -- NODE_START|NODE_END|DECISION|OVERRIDE|STATUS|ERROR
  payload        JSONB NOT NULL
);

CREATE TABLE members (
  member_id TEXT PRIMARY KEY, full_name TEXT, date_of_birth DATE,
  policy_number TEXT NOT NULL, policy_id UUID, status TEXT, id_doc_expiry DATE
);

CREATE TABLE claim_history (
  claim_id UUID PRIMARY KEY, member_id TEXT REFERENCES members,
  kind TEXT NOT NULL CHECK (kind IN ('PRIOR_CLAIM','EPISODE_CLAIM','PRIOR_STAY')),
  claim_number TEXT,
  provider_npi CHAR(10), cpt_codes TEXT[], icd10_codes TEXT[],
  amount NUMERIC(12,2), service_date DATE, submitted_at TIMESTAMPTZ,
  admit_date DATE, discharge_date DATE,       -- used by PRIOR_STAY rows
  source_case_id UUID
);
CREATE INDEX ON claim_history (member_id, service_date);
CREATE INDEX ON claim_history (provider_npi);

CREATE TABLE policies (
  policy_id UUID PRIMARY KEY, name TEXT, version TEXT,
  effective_from DATE, effective_to DATE,
  object_key TEXT, ingest_status TEXT, chunk_count INT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- parsed from the policy's "Excluded CPT Code Ranges" table at ingestion (7.6, step 0)
-- lookup: range_start <= code <= range_end, compared as upper-case strings of equal length (ranges do not cross letter classes);
-- effective dates come from the policies row, so there is no date column here
CREATE TABLE policy_exclusions (
  exclusion_id UUID PRIMARY KEY, policy_id UUID NOT NULL REFERENCES policies,
  range_start TEXT NOT NULL, range_end TEXT NOT NULL,   -- may be alphanumeric: 0001T, V2100, D0100
  category TEXT, basis TEXT, page INT
);

CREATE TABLE users (
  user_id UUID PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, role user_role NOT NULL
);
```

Notes: `FAILED` is a terminal technical state that also routes to the review queue (FR-ORC-08). `PROCESSING` covers the parallel specialist stage (PRD section 8.1). `members`/`claim_history` are seeded mocks **[Default, OQ-08]**; production would replace them with read-only adapters behind the same repository interface.

`claim_history.kind` is a TEXT column with a CHECK constraint, not a native Postgres enum (so a new kind needs no `ALTER TYPE`); the application maps it to a `ClaimHistoryKind` StrEnum in `packages/core/enums.py`. It separates three uses so one claim never matches itself: `PRIOR_CLAIM` rows (older claims) feed the duplicate, frequency and billing detectors; `EPISODE_CLAIM` is the claim that belongs to the same treatment episode as the document being checked and feeds only the date-conflict detector; `PRIOR_STAY` rows carry admit and discharge dates and feed only the readmission detector. The dataset's own current claim MUST NOT be seeded as a `PRIOR_CLAIM`.

## 5. Shared types

All agent I/O uses Pydantic v2 models in `packages/core/models.py`; the UI uses TypeScript types generated from the OpenAPI schema (`openapi-typescript`).

```python
class Envelope(BaseModel):
    agent: str
    agent_version: str
    status: Literal["OK", "ERROR", "SKIPPED"]
    confidence: float = Field(ge=0, le=1)
    model: str | None = None
    started_at: datetime
    finished_at: datetime
    error: str | None = None
    raw_response_ref: str | None = None   # SHA-256 reference of the raw model response (FR-CLS-06); set by the LLM gateway

class Classification(Envelope):
    doc_type: DocType
    routing_tags: list[str] = []

class OcrField(BaseModel):
    key: str; value: str; confidence: float; page: int

class BBox(BaseModel):
    text: str; page: int; x: float; y: float; w: float; h: float

class OcrPayload(Envelope):
    fields: list[OcrField]; raw_text: str; bounding_boxes: list[BBox]
    pages: int; used_text_layer: bool

class KycFlag(BaseModel):
    code: Literal["MEMBER_NOT_FOUND","DOB_MISMATCH","NAME_MISMATCH","POLICY_MISMATCH",
                  "ID_EXPIRED","ID_EXPIRING_SOON","TAMPER_SUSPECTED","LOW_QUALITY","ELA_ANOMALY"]
    severity: Literal["LOW","MEDIUM","HIGH"]
    evidence: str                       # page / bbox / field reference

class KycResult(Envelope):
    kyc_passed: bool; flags: list[KycFlag]; member_ref: str | None

class ClaimFields(BaseModel):
    claim_amount: Decimal | None
    icd10_codes: list[str]; cpt_codes: list[str]
    provider_npi: str | None; service_date: date | None
    claim_number: str | None
    admit_date: date | None; discharge_date: date | None
    signature_present: bool | None
    extra: dict[str, Any] = {}      # type-specific fields (prescription: drugs, sig, dea, refills, rx_date)
    field_confidence: dict[str, float] = {}
    field_source: dict[str, BBox | None] = {}

class ClaimsResult(Envelope):
    extracted_fields: ClaimFields
    schema_valid: bool; validation_errors: list[str]   # blocking; drive schema_valid
    warnings: list[str] = []         # non-blocking, e.g. "NPI_CHECKSUM"; never change a decision

class PolicyClause(BaseModel):
    text: str; policy_id: UUID; page: int; section: str | None; score: float

class PolicyResult(Envelope):
    covered: bool | None            # None when no reliable clause found
    coverage_percentage: float | None
    policy_clause: PolicyClause | None
    exclusions: list[PolicyClause] = []

class Anomaly(BaseModel):
    type: Literal["DUPLICATE_CLAIM","FREQUENCY_SPIKE","PROVIDER_BILLING_OUTLIER",
                  "AMOUNT_OUTLIER","CODE_MISMATCH","TAMPER_SIGNAL","IDENTITY_MISMATCH",
                  "NEAR_THRESHOLD","DATE_CONFLICT","READMISSION_30D"]
    evidence: str; weight: float

class FraudResult(Envelope):
    fraud_score: float = Field(ge=0, le=1)
    anomalies: list[Anomaly]; risk_level: RiskLevel

class Decision(Envelope):
    decision: DecisionKind; justification: str
    agent_summaries: dict[str, str]; rule_trace: list[RuleStep]
```

Schema violations from an LLM are handled per section 7.1 (one retry, then error).

## 6. LangGraph design

### 6.1 State

```python
class GraphState(TypedDict, total=False):
    case_id: str; pipeline_run: str
    document: DocumentRef            # object key, mime, pages
    classification: Classification
    ocr: OcrPayload
    kyc: KycResult
    claims: ClaimsResult
    policy: PolicyResult
    fraud: FraudResult
    decision: Decision
    errors: Annotated[list[str], operator.add]
    audit: Annotated[list[AuditEvent], operator.add]
```

Parallel nodes write to disjoint keys (`kyc`, `claims`, `policy`); list fields use additive reducers, so no merge conflicts.

### 6.2 Nodes and edges

```
START -> load_document -> classify
classify --(UNKNOWN or conf < THRESH_CLASSIFY_REVIEW or error)--> mark_needs_review -> END
classify --(otherwise)--> ocr -> route
route --> [kyc?] [claims?] [policy?]   # conditional fan-out by doc_type (PRD 7.2)
claims -> policy                        # [Default, OQ-17] Policy waits for Claims codes
kyc, policy (or claims when no policy) -> join
join -> fraud -> aggregate -> orchestrate -> persist -> END
any node error after retries -> mark_failed -> END   (status FAILED, routed to review)
```

Routing is a pure function `route(doc_type) -> set[AgentName]` backed by a table **[Default, OQ-05]**:

| doc_type | kyc | claims | policy | fraud |
| --- | --- | --- | --- | --- |
| CLAIM_FORM | full | yes | yes | yes |
| ID_DOCUMENT | full | no | no | yes (tamper and identity signals) |
| DISCHARGE_SUMMARY | member match only | yes (extraction only) | no (D1) | yes |
| PRESCRIPTION | member match only | yes (extraction only) | no (D1) | yes |
| POLICY_AMENDMENT | full | no | yes (consistency) | no |

A skipped agent writes `status=SKIPPED` with no confidence contribution; the decision engine treats SKIPPED as "not applicable", not as a failure.

**D1 [Confirmed 2026-10-31].** Discharge summaries and prescriptions are supporting documents: they are extracted, matched to a member and fraud-checked, but they do not get a coverage decision. Only claim forms (and policy amendments) reach the Policy Agent. Reverse this by changing the two "no (D1)" cells and the matching variants in 7.8.

Join barrier: the `join` node runs once every routed node has completed (LangGraph fan-in). Orchestrator MUST NOT run before all routed agents finish (FR-ORC-01).

### 6.3 Node wrapper

Every node is wrapped by `instrument(agent_name)` which: appends `NODE_START`/`NODE_END` audit events, enforces `AGENT_TIMEOUT_S`, retries transient errors (2 retries, exponential backoff), persists an `agent_runs` row, publishes a Redis event, and converts exceptions into an `ERROR` envelope with `confidence=0`.

## 7. Agent specifications

### 7.1 LLM gateway (shared)

- Interface: `complete_json(model, system, messages, images, schema) -> BaseModel`.
- Uses provider-native structured output / tool schema; validates against the Pydantic model. On validation failure: one retry with the validation error appended; second failure raises `LLMSchemaError` (agent returns ERROR, FR-CLS-04).
- Timeout and retry with jitter on 429/5xx; fallback provider after 2 failed attempts **[Default, ADR-001]**.
- Logs prompt version, model, token counts, latency; never logs raw PHI when `PHI_LOG_REDACTION=true`.
- Treats document content as untrusted: system prompt states that text inside images is data; model output is schema-constrained; no tools are exposed to document-conditioned calls (NFR-AI-03).

### 7.2 Classifier Agent

- Input: first page image plus one sampled later page for multi-page files (FR-CLS-05), downscaled to a max long edge of 1568 px.
- Prompt `classifier.v1`: lists the six types with distinguishing cues, asks for `doc_type`, calibrated `confidence` and `routing_tags`, and requires `UNKNOWN` when no type fits.
- Post-rules: `confidence < THRESH_CLASSIFY_REVIEW` => treated as UNKNOWN for routing; the original label is kept for display.
- Representation: the classifier keeps the predicted `doc_type` and adds `"NEEDS_REVIEW"` to `routing_tags` when confidence is below `THRESH_CLASSIFY_REVIEW`. The router sends a case to `mark_needs_review` when `doc_type == UNKNOWN` or `"NEEDS_REVIEW" in routing_tags`, and handles `status == ERROR` separately (also to review).
- Input validation: PNG and JPEG are fully decoded before use; zero-byte, truncated, corrupt or mislabeled files, zero-page PDFs and unsupported types return an ERROR envelope without calling the model.
- Class guidance in the prompt (from the generated dataset): CMS-1500 and UB-04 forms are both `CLAIM_FORM`; driver's licenses, passports, state IDs, health-plan member cards and Medicare cards are all `ID_DOCUMENT`; typed and handwritten amendments are `POLICY_AMENDMENT`, and a government ID image appended below an amendment does not change that; bank statements, utility bills, blank pages and unreadable scans are `UNKNOWN`.
- Output: `Classification`. Persists model, prompt version and raw response reference (FR-CLS-06).

### 7.3 OCR / Pre-processor

1. If the file is a PDF with a text layer of at least 50 characters per page, extract with `pdfplumber`/`pymupdf` and set `used_text_layer=true` (FR-OCR-03).
2. Otherwise render pages at 300 DPI, deskew/rotate (OpenCV), then run Tesseract (`--psm 6`, `image_to_data`) for words and boxes.
3. If mean Tesseract word confidence is below 0.70 or key fields are missing, call the vision LLM for structured field extraction and merge, preferring the higher-confidence value per field (ADR-007).
4. Normalize to `OcrPayload` (`fields`, `raw_text`, `bounding_boxes`). Field keys use a canonical vocabulary: `member_id`, `member_name`, `dob`, `policy_number`, `id_number`, `id_expiry`, `claim_amount`, `icd10`, `cpt`, `provider_npi`, `service_date`, `provider_name`, `diagnosis`, `medication`.
5. Confidence = mean field confidence weighted by page coverage.

### 7.4 KYC Agent

Checks run in this order; each produces flags:

| Check | Logic | Flag |
| --- | --- | --- |
| Member lookup | by `member_id`, then `policy_number`; when the document carries neither (passports, state IDs), by date of birth plus the best fuzzy name match (ratio at least 0.80) | `MEMBER_NOT_FOUND` (HIGH) |
| DOB | exact date match | `DOB_MISMATCH` (HIGH) |
| Name | normalize both names (case, punctuation, middle initial, extra spaces); any remaining difference is a flag; fuzzy ratio 0.85 or above gives MEDIUM, below gives HIGH | `NAME_MISMATCH` (MEDIUM or HIGH) |
| Policy number | equals member record, policy active on service date | `POLICY_MISMATCH` (HIGH) |
| Expiry | printed expiry date earlier than the reference date (below), or an explicit EXPIRED marking on the document (the Medicare card prints no date, only a banner); expiry within 30 days after the reference date | `ID_EXPIRED` (HIGH); `ID_EXPIRING_SOON` (LOW, never changes a decision) |
| Visual tamper | vision LLM prompt `kyc_tamper.v1` asks for font/spacing inconsistencies, overlaid patches, pixel artifacts; returns anomalies with regions | `TAMPER_SUSPECTED` (MEDIUM or HIGH) |
| ELA (bonus) | JPEG re-save at quality 90, difference map, region statistics above a calibrated threshold | `ELA_ANOMALY` (MEDIUM) |

`kyc_passed = no HIGH-severity flag`. Tamper and ELA flags alone MUST lower confidence and escalate rather than reject (R-06): they are included in `flags` with severity MEDIUM unless corroborated by a data mismatch. Confidence = 1 minus the highest weighted flag penalty, floored at 0.1; a field that is absent from the document is skipped (not a mismatch) when another identifier matched, and the cap of 0.55, which escalates the case, applies only when no identifier could be extracted at all.

For "member match only" document types, only member lookup, DOB and name checks run.

**Reference date.** Expiry, policy-active and recency checks use `cases.received_at`, never the wall clock. In production `received_at` is the upload time. In evaluation the runner sets it to the label's `reference_date` (the cluster's treatment date) when `ALLOW_RECEIVED_AT_OVERRIDE=true`, so a dataset built around 2025 dates stays valid; the override is refused in production.

**Identity mismatch.** Any `NAME_MISMATCH` is passed to the Fraud agent as an `IDENTITY_MISMATCH` signal (7.7), so a name that differs from the member record escalates the case even when it does not fail KYC. A HIGH name mismatch also fails KYC.

### 7.5 Claims Agent

1. Take fields from `ocr`; for any required field missing or below 0.7 confidence, run a targeted vision LLM extraction (prompt `claims_extract.v1`) returning values with page and bbox.
2. Normalize: amount to `Decimal` (strip currency symbols), codes uppercase, dates to ISO.
3. Validate (FR-CLM-02/03):
   - Required fields depend on `doc_type` (table after step 5).
   - ICD-10: `^[A-TV-Z][0-9][0-9AB](\.[0-9A-TV-Z]{1,4})?$`.
   - CPT: `^\d{4}[0-9FT]$` (five characters).
   - NPI: strip any `NPI-` prefix, then require 10 digits. A failed Luhn check (prefix `80840`) appends the non-blocking warning `NPI_CHECKSUM` to `ClaimsResult.warnings` (it is not a KYC flag and not a validation error), because the synthetic NPIs are not checksum-valid. With `NPI_LUHN_STRICT=true` it becomes a validation error and `schema_valid` is false.
   - `service_date` not later than `cases.received_at` and not more than 365 days before it **[Default]**.
   - `claim_amount > 0` and below a configurable maximum (default 1,000,000).
   - Conform to `data/schemas/claim_submission_standard.v1.json` (JSON Schema) **[Default, OQ-04]**.
4. `schema_valid = no errors`. Each error is a string `FIELD_CODE: message`.
5. Confidence reflects how reliably the values were read, not whether the form is complete. It is the minimum over the confidences of fields that are present, with 0.9 for a field confirmed absent (its label was found and the value is blank or marked missing). It drops below 0.6 only when the page cannot be read well enough to tell whether a field is present (for example OCR mean confidence below 0.7 after the LLM fallback). A missing required field therefore gives `schema_valid=false` at normal confidence, so rule R3 rejects the claim instead of rule R1 escalating it.

**Required fields by document type**

| doc_type | Required |
| --- | --- |
| CLAIM_FORM | `claim_amount`, `service_date`, `icd10_codes` (1 or more), `cpt_codes` (1 or more), `provider_npi`, `signature_present` |
| DISCHARGE_SUMMARY | `admit_date`, `discharge_date`, `icd10_codes` (1 or more), `signature_present` |
| PRESCRIPTION | drug name, dosage instructions (sig), refills, prescriber NPI and DEA number, `rx_date` (stored in `extra`) |
| ID_DOCUMENT, POLICY_AMENDMENT | not processed by the Claims Agent |

The generated forms mark absent values with explicit text such as `[DOB MISSING]`, `[NPI MISSING]`, `[SIGNATURE MISSING]` or `[DEA MISSING]`, and some leave the line blank; both count as confirmed absent. The prior-authorization number is blank on valid forms, so it is not a required field.

### 7.6 Policy Agent and RAG module

**Ingestion (`POST /policies`)**

1. Store PDF in MinIO; insert `policies` row with `ingest_status=PENDING`.
2. Celery task `ingest_policy(policy_id)`: parse with Docling into a structured document (headings, tables, page numbers).
3. Chunk by section: split on heading boundaries, target 400 to 800 tokens, 80-token overlap, keeping tables as single chunks where under 1,000 tokens. Each chunk carries `policy_id`, `version`, `section_path`, `page`, `effective_from/to`, `chunk_type` (`coverage`, `exclusion`, `definition`, `schedule`, `other`) assigned by a lightweight classifier prompt.
4. Embed with `EMBEDDING_MODEL` and upsert into Qdrant collection `policy_chunks` (cosine). Set status `READY` and `chunk_count`.

**Step 0: deterministic exclusion lookup.** Both sample policies contain a machine-readable table of excluded CPT ranges (section 4.1 of each policy). Ingestion parses it into `policy_exclusions` rows (`range_start`, `range_end`, `category`, `basis`, `page`) alongside the vector chunks. Before any retrieval, each CPT code is checked against the member policy's ranges: a hit returns `covered=false`, cites the matching table row, and has confidence 0.95, with no LLM call. Ranges include alphanumeric codes (`0001T-0099T`, `V2100-V2799`, `D0100-D9999`), so compare by prefix then number. A code not in the table is covered only if retrieval finds a matching inclusion clause (for example surgical services or diagnostic imaging); if none is found the result is `covered=None`, which escalates.

**Retrieval (`Policy Agent`)**

1. Resolve `policy_id` from the member's policy number via KYC `member_ref`; filter by `effective_from <= service_date <= effective_to` (FR-POL-05/08).
2. Build queries per CPT code (`"coverage for CPT {code} {description}"`, with description from a small CPT lookup table in `data/`) and per ICD-10 code; run hybrid search (dense + BM25 over chunk text via Qdrant sparse vectors), top 8 each, merged with reciprocal rank fusion, then a cross-encoder or LLM rerank to top 5.
3. Ask the text LLM (prompt `policy_decide.v1`) with only the retrieved chunks to return `covered`, `coverage_percentage`, supporting clause id and exclusions, with an instruction to answer `null` when the text does not decide coverage.
4. Verify that the cited clause text is a substring of a retrieved chunk; reject hallucinated citations.
5. Confidence = rerank score of the cited clause adjusted by LLM self-reported certainty (min of the two). If top rerank score is below 0.35, return `covered=None` with confidence 0.3, which forces escalation (FR-POL-06).
6. A claim is `covered` only when every CPT code is covered; coverage percentage is the minimum across codes; exclusions that match any ICD-10 or CPT code set `covered=false`.

For POLICY_AMENDMENT documents the agent compares amendment fields to the current policy and reports a consistency result using the same output schema **[Default, OQ-15]**.

### 7.7 Fraud Detection Agent

Deterministic scoring; the LLM MAY write explanatory text only (FR-FRD-06).

`fraud_score = min(1.0, 1 - Π(1 - wᵢ·sᵢ))` over detectors (noisy-OR), where `sᵢ ∈ [0,1]` is detector strength and `wᵢ` its weight.

| Detector | Signal | Weight wᵢ |
| --- | --- | --- |
| DUPLICATE_CLAIM | Same member and claim number (or same provider NPI, service date and CPT set) as a `PRIOR_CLAIM` row or an earlier processed case; the first submission is never flagged, so processing order matters. The duplicate dataset file has a different scan effect and therefore a different checksum, so checksum matching alone will not catch it | 0.90 |
| FREQUENCY_SPIKE | Claims in the last 30 days for the member exceed mean + 3 sd of the member's 12-month history (or a global baseline when history is under 3 claims) | 0.45 |
| PROVIDER_BILLING_OUTLIER | Provider's average amount for the CPT set exceeds the population median by more than 3 MAD | 0.40 |
| AMOUNT_OUTLIER | Amount over the 99th percentile for the CPT set | 0.35 |
| CODE_MISMATCH | ICD-10 and CPT pair absent from a plausibility table in `data/`; includes an obstetric CPT (for example 59400) with a non-obstetric diagnosis | 0.40 |
| TAMPER_SIGNAL | KYC `TAMPER_SUSPECTED` or `ELA_ANOMALY` present | 0.40 |
| IDENTITY_MISMATCH | KYC `NAME_MISMATCH` flag present (any severity) | 0.50 |
| NEAR_THRESHOLD | Total claim amount from `NEAR_THRESHOLD_LOW` up to but not including `NEAR_THRESHOLD_HIGH` (structuring just under the review limit) | 0.35 |
| DATE_CONFLICT | Prescription date more than `DATE_CONFLICT_DAYS` after the member's `EPISODE_CLAIM` service date | 0.45 |
| READMISSION_30D | Admission date within `READMISSION_DAYS` after a `PRIOR_STAY` discharge date | 0.45 |

The binary detectors (identity, near-threshold, date conflict, readmission, code mismatch, tamper, duplicate) use strength 1 when they fire. Scores are rounded to 4 decimal places before comparison with a threshold, so a single detector with weight 0.30 is not decided by floating-point noise. A reference-price table in `data/` backs `AMOUNT_OUTLIER`; the detector is skipped for codes without a reference price (for example the placeholder code 99999).

Risk level: `LOW < THRESH_FRAUD_ESCALATE (0.30)`, `MEDIUM` from 0.30 to below `THRESH_FRAUD_HIGH (0.60)`, `HIGH` at or above 0.60 **[Default, FR-FRD-04]**. Each anomaly records evidence (for example matching `claim_id`) and its contribution. Agent confidence is 0.9 when at least 3 historical claims exist for the member, else 0.7; it is 0.5 if the claim history query fails (case escalates).

Fraud runs for ID_DOCUMENT with only the tamper and identity-mismatch detectors. The frequency and billing-outlier detectors need a baseline: seeded `PRIOR_CLAIM` history for ordinary members must stay within normal ranges so that they do not produce false positives on clean cases.

### 7.8 Orchestrator and decision engine

The decision is computed by a pure function in `packages/decision` (ADR-003). The LLM only drafts the justification afterward from the rule trace, and cannot change the decision.

```python
def decide(s: GraphState, cfg: Thresholds) -> tuple[DecisionKind, list[RuleStep], float]:
    agents = applicable_results(s)                       # excludes SKIPPED
    # R1: reliability
    if any(a.status == "ERROR" for a in agents):          return ESCALATE, "AGENT_ERROR"
    if any(a.confidence < cfg.agent_conf for a in agents): return ESCALATE, "LOW_CONFIDENCE"
    # R2: fraud
    if s.fraud and s.fraud.fraud_score >= cfg.fraud_escalate: return ESCALATE, "FRAUD_SCORE"
    # R3: reject
    if s.kyc and not s.kyc.kyc_passed:                    return REJECT, "KYC_FAILED"
    if s.policy and s.policy.covered is False:            return REJECT, "NOT_COVERED"
    if s.claims and not s.claims.schema_valid:            return REJECT, "SCHEMA_INVALID"
    # R4: approve
    return APPROVE, "ALL_CHECKS_PASSED"
```

Precedence (R1, R2, R3, R4) implements PRD FR-ORC-05 **[Default, OQ-06]**. Document-type variants **[Default, OQ-15]**:

- ID_DOCUMENT: APPROVE means "identity verified"; no claims/coverage conditions apply.
- POLICY_AMENDMENT **[Confirmed, D2]**: always ESCALATE for human confirmation unless KYC fails (REJECT) in v1. Because all amendments escalate, evaluation reports decision accuracy per document category as well as overall.
- DISCHARGE_SUMMARY and PRESCRIPTION **[Confirmed, D1]**: supporting documents with no coverage check. REJECT only for KYC failure or `schema_valid=false`; APPROVE means "document accepted".
- Low-severity KYC flags (`ID_EXPIRING_SOON`) and Claims warnings (`NPI_CHECKSUM` in `ClaimsResult.warnings`) never change a decision.

Confidence: `min` of applicable agent confidences, multiplied by 0.9 for REJECT decisions that rest on a single source, and capped at 0.59 for ESCALATE decisions triggered by R1 (FR-ORC-07, OQ-07). The `rule_trace` lists every rule evaluated with `fired: bool` and inputs, giving a full explanation (AC-04, NFR-AI-01).

Persistence: insert `decisions`, set case status `DECIDED`, append `DECISION` audit event, publish event.

## 8. API specification

Base path `/api/v1`. JSON unless stated. Auth: `Authorization: Bearer <JWT>`; roles per section 8.3. OpenAPI is generated by FastAPI and is the contract source for the UI types.

### 8.1 Endpoints

| Method and path | Roles | Request | Response |
| --- | --- | --- | --- |
| `POST /cases` | REVIEWER+, service token | multipart `file` (JPEG, PNG, PDF, TIFF), optional `channel` | `202 {case_id, status}`; `400` type; `413` size; `200` with `duplicate_of` when checksum matches |
| `GET /cases` | REVIEWER+, AUDITOR | query `status`, `decision`, `doc_type`, `q`, `from`, `to`, `page`, `page_size` | `{items[], total}` |
| `GET /cases/{id}` | REVIEWER+, AUDITOR | none | case, classification, agent outputs, decision, `document_url` (signed, 10 min) |
| `GET /cases/{id}/audit` | REVIEWER+, AUDITOR | none | ordered `audit_events[]` |
| `GET /review-queue` | REVIEWER+ | `page`, `page_size` | cases with `NEEDS_REVIEW`, `FAILED` or decision `ESCALATE` not yet overridden |
| `POST /cases/{id}/override` | REVIEWER+ | `{to_decision, reason}` (reason at least 10 chars) | `200 {override}`; original decision preserved |
| `POST /cases/{id}/reclassify` | REVIEWER+ | `{doc_type}` | re-enqueues pipeline from `ocr` with fixed type |
| `POST /cases/{id}/rerun` | SUPERVISOR+ | none | new `pipeline_run` |
| `POST /policies` | SUPERVISOR+ | multipart PDF, `name`, `version`, `effective_from`, `effective_to` | `202 {policy_id}` |
| `GET /policies` | REVIEWER+ | none | policies with `ingest_status`, `chunk_count` |
| `GET /cases/{id}/report` | REVIEWER+, AUDITOR | none | PDF report (bonus) |
| `GET /health`, `GET /ready` | none | none | liveness and dependency readiness |
| `WS /cases/{id}/events` | REVIEWER+ | none | stream of `{agent, status, ts}` (bonus) |
| `POST /auth/login` | none | `{email, password}` | `{access_token}` |

### 8.2 Error format

```json
{ "error": { "code": "UNSUPPORTED_MEDIA_TYPE", "message": "...", "request_id": "..." } }
```

### 8.3 Role matrix

| Capability | REVIEWER | SUPERVISOR | AUDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| View cases and audit | yes | yes | yes (read-only) | yes |
| Override decisions | yes | yes | no | yes |
| Rerun / upload policies | no | yes | no | yes |
| Manage users | no | no | no | yes |

### 8.4 Behavior rules

- Upload is idempotent by SHA-256: a duplicate returns the existing `case_id` with `duplicate_of` set, and does not rerun (FR-ING-06).
- Override writes an `overrides` row and `OVERRIDE` audit event, sets status `OVERRIDDEN`, and never mutates the original `decisions` row (FR-UI-06).
- Document URLs are pre-signed, expire in 10 minutes, and are never stored in the database.

## 9. UI specification (Next.js)

| Route | Content | Requirement |
| --- | --- | --- |
| `/login` | Email and password | NFR-SEC-03 |
| `/` (dashboard) | Table of cases with status badges (Processing, Approved, Rejected, Escalated), filters, search by case ID, pagination, counts by status | FR-UI-01 |
| `/cases/[id]` | Left: document viewer (zoom, pan, page navigation). Right: collapsible per-agent panels (Classifier, OCR fields, KYC, Claims, Policy, Fraud), decision panel (decision, confidence, justification, rule trace), audit log tab | FR-UI-02/03/05 |
| `/review` | Queue of escalated, NEEDS_REVIEW and FAILED cases with age, reason, assignee; override dialog (approve, reject, reclassify) requiring a reason | FR-UI-04/06 |
| `/policies` | Policy list, upload form, ingestion status | FR-UI-10 |

Implementation notes:

- Data fetching: TanStack Query; polling every 5 s for in-progress cases when WebSocket is disabled; WebSocket updates a case's agent timeline when enabled (FR-UI-08).
- Status badge mapping: PROCESSING = `RECEIVED, CLASSIFIED, PROCESSING, FRAUD_CHECK, AGGREGATED`; `NEEDS_REVIEW` and `FAILED` render as Escalated with a sub-label **[Default]**.
- Field-level evidence: clicking an extracted field highlights its bounding box on the image.
- Accessibility: keyboard-navigable table, visible focus, color-independent badges (icon plus text), WCAG 2.1 AA contrast (NFR-UX-01).
- State: server state only; no PHI in `localStorage`.

## 10. Prompts and model management

- Prompts live in `packages/agents/prompts/{agent}.{version}.md` with front matter (`model`, `temperature=0`, `max_tokens`, `schema`). Prompt version is recorded in every `agent_runs` row.
- Vision calls use temperature 0 and JSON-schema constrained outputs.
- Each prompt has a regression test set drawn from the synthetic dataset; changing a prompt requires a passing evaluation run (NFR-QUAL-02).
- Model IDs are configuration only. The PRD's named model (a dated Claude Sonnet identifier) MUST be verified for current availability before release, and the default falls back to the provider's current Sonnet or GPT-4o class model (OQ-02).

## 11. Evaluation harness

`packages/eval` runs the full pipeline over `data/synthetic/labels.jsonl` and writes `reports/eval_{timestamp}.json` and `.md`.

Label schema per document:

```json
{ "file": "case_007.png", "doc_type": "CLAIM_FORM",
  "fields": {"claim_amount": 1250.00, "icd10_codes": ["M54.5"], "cpt_codes": ["97110"],
             "provider_npi": "1234567893", "service_date": "2026-08-12"},
  "kyc_expected": "PASS", "coverage_expected": true, "fraud_expected": "LOW",
  "decision_expected": "APPROVE", "scenario": "valid_clean" }
```

Label derivation rules (v0.2.2). `decision_expected` is copied from the generator's `expected_decision`. The other expected fields are derived only where the truth data states them, and are otherwise null; they are diagnostic and do not enter the scored metrics.

| Field | Rule |
| --- | --- |
| `kyc_expected` | ID documents only: `FAIL` if `expired`, else `PASS`; null for other types |
| `coverage_expected` | Claim forms only: `false` in an uncovered-procedure cluster, else `true`; null for other types (D1) |
| `fraud_expected` | `LOW` when `fraud_label` is false; `FLAGGED` (at least MEDIUM) when true, with `fraud_reason` kept; no numeric level is invented |
| `scenario` | First match in this order: fraud reason, tampered ID, expired ID, expiring-soon ID, uncovered procedure, missing field, duplicate claim file (`_dup`), policy amendment, unknown, otherwise `valid_clean`; cases that match nothing are left null and listed |
| `fields.provider_npi` | Stored without the printed `NPI-` prefix (the Claims agent strips it, so extraction is scored on digits) |
| `reference_date` | From truth for clustered documents; the four unknown documents carry null and the runner uses the constant `DATASET_AS_OF_DATE = 2025-12-31` |

Metrics:

| Metric | Definition |
| --- | --- |
| Classification accuracy | exact match of `doc_type` |
| Extraction completeness | correct required fields / total required fields over Claims-eligible docs (amount tolerance 0.01; codes as sets) |
| Decision correctness | exact match of decision; also confusion matrix and breakdowns per scenario, per document category and per split (dev, holdout) |
| Retrieval relevance | manual rubric 0 to 2 per query (script produces the review sheet); pass at mean at least 1.0 |
| Latency | p50 and p95 end to end |
| Calibration (bonus) | 5-bin reliability diagram and ECE of orchestrator confidence against decision correctness |

**Dataset (generated).** The project uses four existing generator scripts in `data/synthetic/generators/`: `generate_docs.py` (151 PNGs in five categories from 30 patient clusters), `generate_gold_policy.py` and `generate_silver_policy.py` (two policy PDFs), and `generate_unknown.py` (4 out-of-distribution documents). Pillow and numpy render the images and fpdf2 renders the PDFs. Everything is fictional. The generator also writes `truth.json` (true values per document: amounts, codes, NPI, dates, signature present, printed name and expiry, tampered, expired, missing field type) and `clusters.json`; `labels.jsonl` is built from these plus `metadata.json`.

**Expected decisions (D1 and D2, both confirmed).**

| Document | Expected decision |
| --- | --- |
| Unknown, policy amendment, any fraud-labeled document | ESCALATE |
| ID: tampered | ESCALATE |
| ID: expired | REJECT |
| ID: otherwise, including expiring soon | APPROVE |
| Claim form: uncovered procedure or missing fields | REJECT |
| Claim form: otherwise | APPROVE |
| Prescription: missing field | REJECT |
| Prescription and discharge summary: otherwise | APPROVE |

**Run rules.** The runner sets `received_at` from each label's `reference_date` (7.4). It processes a cluster's original claim before its `_dup` file so the duplicate detector sees the first submission. History seeds follow the kinds in section 4: prior claims for ordinary members, an `EPISODE_CLAIM` row for the date-conflict cluster, and a `PRIOR_STAY` row for the readmission cluster. Documents are split into dev and holdout (about 70/30) by cluster, stratified by scenario, and the split is committed in `split.json`; tune on dev and report final numbers on holdout. Silver-plan retrieval is tested with a fabricated Silver member, because every generated policy number is Gold.

Gates: the evaluation script exits non-zero when decision correctness is below 0.60 or weighted score is below 0.70 (AC-03).

## 12. Non-functional design

| NFR | Design response |
| --- | --- |
| NFR-PERF-01/02 | Async pipeline; Celery concurrency sized to 25 documents per minute; parallel specialist nodes; page images cached in MinIO; target LLM calls per document: classifier 1, OCR fallback 0 or 1, KYC tamper 1, Claims 0 or 1, Policy 1 to 2, justification 1 |
| NFR-REL-01/02 | Celery `acks_late`, 3 attempts with backoff, dead-letter queue; `pipeline_run` ID makes reruns idempotent; DB writes keyed by (`case_id`, `pipeline_run`, `agent`) |
| NFR-SEC-01 | TLS at ingress; MinIO SSE; Postgres volume encryption; Qdrant over TLS |
| NFR-SEC-03/04 | JWT with roles; least-privilege DB users (agents have read-only access to `members` and `claim_history`); log redaction filter masks member ID, DOB, names, policy numbers; LangSmith disabled by default |
| NFR-AUD-01 | `audit_events` is append-only (no UPDATE/DELETE grants plus trigger); every node and human action logged with UTC timestamp |
| NFR-OBS-01/02 | JSON logs with `case_id`, `pipeline_run`; Prometheus metrics (`queue_depth`, `agent_latency_seconds`, `agent_errors_total`, `decisions_total`); optional LangSmith tracing |
| NFR-AI-03 | Prompt-injection controls per section 7.1; red-team cases in the dataset (document containing "approve this claim") |
| NFR-DEP-01 | `docker compose up` brings up api, worker, redis, postgres, minio, qdrant, web |

## 13. Testing strategy

| Level | Scope | Tooling |
| --- | --- | --- |
| Unit | Decision engine (every rule and precedence combination), validators (ICD-10, CPT, NPI Luhn), fraud math, chunker, routing table | pytest, hypothesis for decision properties |
| Contract | Pydantic models vs JSON examples; OpenAPI vs generated TS types | pytest, schemathesis |
| Agent | Each agent against recorded LLM responses (VCR-style fixtures) and live smoke tests behind a flag | pytest |
| Integration | Full graph with a stub LLM; API upload to DECIDED; policy upload then retrieval | pytest, docker compose |
| Evaluation | Section 11 on the labeled set | `eval` package |
| UI | Dashboard load, case detail render, override end to end | Playwright |
| Security | Secret scanning in CI, dependency audit, authorization tests per role | gitleaks, pip-audit, pytest |

Decision-engine coverage MUST include: each of R1 to R4 firing alone, every pair with overlapping triggers (for example KYC failed with fraud 0.5 gives ESCALATE), SKIPPED agents, boundary values 0.30 and 0.60 (AC-04).

## 14. Deployment and operations

- `docker-compose.yml` for local and demo; Dockerfiles per app (multi-stage, non-root).
- Migrations with Alembic; seed script loads members, claim history, two sample policies and test users.
- CI: lint (ruff, mypy strict on `core`, `decision`), tests, secret scan, build images.
- Production target (outside v1 scope, **[Default, OQ-01]**): containerized on managed Kubernetes, managed Postgres, S3, managed Redis; workers autoscaled on queue depth.
- Runbook items: LLM provider outage (switch `LLM_PROVIDER`), stuck cases (rerun), DLQ draining, policy reindex.

## 15. Security and privacy details

- Documents and extracted fields are PHI in production. In v1 only synthetic data is used (A-03).
- Before any real-data pilot (OQ-03): executed BAA with every LLM provider, zero-retention settings, region pinning, data retention schedule, penetration test, and review of tracing destinations.
- Pre-signed URLs only; no public buckets; CORS limited to the UI origin.
- Passwords hashed with argon2; login rate limiting; JWT short TTL.
- Uploaded files are scanned for type by magic bytes (not extension), size-limited, and parsed in the worker only. PDF rendering uses a sandboxed process with no network.

## 16. Requirements traceability

| PRD requirement group | Spec section |
| --- | --- |
| FR-ING | 2.2, 4, 8 |
| FR-CLS | 6.2, 7.2 |
| FR-OCR | 7.3 |
| FR-KYC | 7.4 |
| FR-CLM | 7.5 |
| FR-POL | 7.6 |
| FR-FRD | 7.7 |
| FR-ORC | 6.2, 7.8 |
| FR-UI | 8, 9 |
| NFR-* | 3, 12, 15 |
| AC-01 to AC-09 | 11, 13 |

## 17. Open items affecting this spec

| PRD ID | Spec impact | Default used here |
| --- | --- | --- |
| OQ-02 | Model IDs and fallback | Groq primary for the real run (vision-capable Llama 4 models), stub until Step 20, Anthropic and OpenAI as optional providers; model IDs confirmed in the Groq console before Step 20 |
| OQ-03 | Retention, tracing, BAA | Synthetic only; tracing off |
| OQ-04 | Claim standard schema | Authored `claim_submission_standard.v1.json` |
| OQ-05 | Routing table | Section 6.2 table |
| OQ-06 | Rule precedence | R1, R2, R3, R4 |
| OQ-08 | Data sources | Seeded PostgreSQL mocks |
| OQ-10 | MEDIUM/HIGH actions | Both escalate; HIGH adds `SIU` tag in justification |
| OQ-11 | Auto-reject policy | Decision stored as recommendation; REJECT visible to reviewers; no outbound notification in v1 |
| OQ-15 | Policy amendment handling | Always escalate unless KYC fails |
| OQ-17 | Policy depends on Claims | Policy node runs after Claims |
| D1 (confirmed 2026-10-31) | Do discharge summaries and prescriptions get a coverage decision? | Decided: no, supporting documents only |
| D2 (confirmed 2026-10-31) | Amendments escalate by default, which inflates the escalation share of labels | Decided: keep the default; report accuracy per category |
| Clock | Dataset dates are in 2025 | `received_at` reference date, overridden only in evaluation |

---

## Changelog

**v0.2.5**
- Classifier review representation (`NEEDS_REVIEW` routing tag) and input validation stated in 7.2.

**v0.2.4**
- `Envelope.raw_response_ref` added (needed to persist the raw response reference, FR-CLS-06).

**v0.2.3**
- Provider decision: stub by default, Groq for the real evaluation; Anthropic and OpenAI optional. New settings `GROQ_API_KEY` and `LLM_RECORD_FIXTURES`.

**v0.2.2**
- Section 11: label derivation rules for `kyc_expected`, `coverage_expected`, `fraud_expected`, `scenario`, NPI normalization and the reference date of unknown documents.

**v0.2.1**
- `NPI_CHECKSUM` is a `ClaimsResult.warnings` entry, not a `KycFlag`; `ClaimsResult` gained `warnings`.
- `claim_history.kind` is TEXT plus CHECK, mapped to a `ClaimHistoryKind` StrEnum.
- `policy_exclusions` lookup rule stated.

**v0.2**
- Claims confidence no longer drops to 0 for a missing field (it would have made rule R1 pre-empt the reject rule); added required fields per document type.
- Added the deterministic CPT exclusion lookup (policy step 0) and the `policy_exclusions` table.
- Fraud: new detectors (identity mismatch, near-threshold, date conflict, readmission), obstetric code mismatch at weight 0.40, `claim_history.kind`.
- KYC: lookup by date of birth and fuzzy name for documents without identifiers, any normalized name difference is a flag, `ID_EXPIRING_SOON`, reference date from `received_at`, no confidence cap for an absent field when another identifier matched.
- NPI prefix stripped and Luhn made a warning; service-date recency measured against `received_at`.
- Routing: discharge summaries and prescriptions skip the Policy Agent (D1).
- D1 and D2 confirmed by the product owner (D1: supporting documents get no coverage decision; D2: policy amendments always ESCALATE unless KYC fails).
- Evaluation: dataset described, expected-decision table, run rules, per-category reporting, dev and holdout split.
