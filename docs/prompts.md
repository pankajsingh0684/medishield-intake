# Build Prompts: MediShield Multi-Agent Document Intake System

Use these with an AI coding assistant in VS Code (Claude Code, Copilot Chat, or similar). Work one step at a time: paste the prompt, review the diff, run the checks, commit, then move on.

Files the assistant should be able to read: `prd` (the PRD), `spec.md`, `adr.md`. Put `spec.md` and `adr.md` in `docs/` in the repo. If the assistant cannot see the PRD, export it to `docs/prd.md`.

**Version v0.2 (2026-10-31).** Steps 1 to 5 are done and marked below. New: Steps 5a to 5c (align the existing dataset generators and the finished Phase 0 code with spec v0.2). Steps 10, 11, 12, 13, 14, 15, 16, 19 and 20 changed. Copy the v0.2 spec, adr, prompts and plan into `docs/` first.

---

## 0. Setup once: project context prompt

Save this as `CLAUDE.md` in the repo root (Claude Code reads it automatically). For other assistants, save it as `.github/copilot-instructions.md` or paste it at the start of each session.

```
# Project context
You are helping build the MediShield multi-agent document intake system.
Source of truth: docs/prd.md (requirements), docs/spec.md (how to build), docs/adr.md (decisions).
If a request conflicts with them, stop and tell me instead of silently deviating.

# Stack
Python 3.12 managed with uv (use `uv add`, `uv run`; never pip). FastAPI, Celery + Redis, PostgreSQL (SQLAlchemy 2 + Alembic),
MinIO (S3), Qdrant, Docling, LangGraph, Pydantic v2, pytest, ruff. Frontend: Next.js (TypeScript).

# Rules
- Work only on the step I name. Do not build later steps or add unrequested features.
- Typed code everywhere; agent modules must not import each other; share data only through packages/core models and graph state.
- No secrets in code. Config comes from environment variables via a typed Settings class.
- Write tests with the code. Run `uv run pytest` and `uv run ruff check .` and fix failures before saying you are done.
- Prefer small, readable functions. No clever abstractions.
- Real PHI is never used. All data is synthetic.
- The dataset in data/synthetic/ is frozen after Step 5a. Never regenerate it, edit its images, or change the generators unless the step says so.
- Dates for expiry and recency checks come from cases.received_at, never the system clock.
- When finished, summarize: files created or changed, how to run it, what is not done yet.
```

---

## Reusable step template

```
Step <N>: <title>.
Read: spec.md sections <list>, adr.md <ADR numbers>, PRD requirements <IDs>.
Goal: <one sentence>.
Create/modify: <paths>.
Requirements:
- ...
Tests: <what must be covered>.
Do not: <what is out of scope for this step>.
Done when: <commands and results I will check>.
Before coding, show me a short plan (files and approach) and wait for my OK.
```

The last line keeps you in control: review the plan, reply "OK" or adjust, then the assistant codes.

---

# Phase 0: Foundations

**Steps 1 to 5 are done (2026-10-31).** Their prompts are kept for reference. Do not re-run them. Step 5b updates the code they produced to spec v0.2.

## Step 1: Project skeleton (done)

```
Step 1: Project skeleton with uv.
Read: spec.md section 2.3 (repo layout) and section 14.
Goal: an empty but working monorepo that runs tests and lint.
Create:
- pyproject.toml via uv (Python 3.12), dev deps pytest and ruff, runtime deps pydantic and pydantic-settings.
- Folders from spec section 2.3 (apps/api, apps/worker, apps/web, packages/{core,agents,graph,decision,rag,forensics,eval}, data/{synthetic,policies,schemas}, infra, docs), with __init__.py in Python packages.
- pytest config (pythonpath = ["."], testpaths = ["packages", "apps"]) and ruff config (line length 100).
- .gitignore, .env.example (variable names from spec section 3, no real values), README.md stub.
- One smoke test.
Do not: add application code, Docker, or dependencies not listed.
Done when: `uv run pytest` and `uv run ruff check .` pass and `git status` shows a clean tree after commit.
Show me the plan first.
```

## Step 2: Docker Compose and typed settings (done; extended in Step 5b)

```
Step 2: Local infrastructure and settings.
Read: spec.md sections 2.1, 3, 14; ADR-004, ADR-005, ADR-006.
Goal: one command starts Postgres 16, Redis, MinIO and Qdrant; the app loads config from env.
Create:
- infra/docker-compose.yml with those four services, named volumes, healthchecks, ports bound to localhost only, credentials read from .env (no hardcoded secrets).
- packages/core/config.py: Settings (pydantic-settings) with every variable in spec section 3, required ones without defaults, thresholds with the documented defaults.
- Update .env.example. Add a make-style script or README section for `docker compose up -d` and for creating the MinIO bucket.
Tests: Settings loads from env vars; missing required vars raise a clear error; threshold defaults equal 0.30, 0.60, 0.60, 0.60.
Do not: add API code or database tables.
Done when: `docker compose -f infra/docker-compose.yml up -d` shows all services healthy and tests pass.
Show me the plan first.
```

## Step 3: Core models and enums (done; extended in Step 5b)

```
Step 3: Core Pydantic models.
Read: spec.md section 5 (shared types) and section 4 (enums); PRD section 8.2.
Goal: all typed contracts used between agents.
Create packages/core/enums.py (DocType, DecisionKind, RiskLevel, CaseStatus, UserRole, AgentStatus) and packages/core/models.py with Envelope, Classification, OcrField, BBox, OcrPayload, KycFlag, KycResult, ClaimFields, ClaimsResult, PolicyClause, PolicyResult, Anomaly, FraudResult, RuleStep, Decision, and GraphState (packages/graph/state.py) as in spec sections 5 and 6.1.
Requirements: confidence fields bounded 0..1; fraud_score bounded 0..1; JSON round-trip works; extra fields forbidden.
Tests: valid and invalid examples per model, JSON serialize/deserialize round trip, bounds enforced, enum values match the PRD exactly.
Do not: write agents or database code.
Done when: tests pass and I can print each model's JSON schema.
Show me the plan first.
```

## Step 4: Decision engine (test first) (done; variants checked in Step 5b)

```
Step 4: Deterministic decision engine.
Read: spec.md section 7.8; ADR-003; PRD FR-ORC-01..09.
Goal: pure function decide(state, thresholds) that returns decision, confidence and rule_trace.
Create packages/decision/engine.py and packages/decision/thresholds.py (frozen Thresholds model built from Settings).
Write the tests FIRST, then the implementation.
Rules (in this precedence): R1 any agent ERROR or confidence below threshold -> ESCALATE; R2 fraud_score >= 0.30 -> ESCALATE; R3 KYC failed, covered is False, or schema invalid -> REJECT; R4 otherwise APPROVE. SKIPPED agents are ignored. ID_DOCUMENT and POLICY_AMENDMENT variants as in spec 7.8. covered=None counts as low confidence.
Tests must cover: each rule alone; all overlapping combinations (for example KYC failed + fraud 0.5 -> ESCALATE); boundaries 0.30 and 0.60 exactly; SKIPPED agents; missing agent outputs; confidence calculation and caps; rule_trace contents. Add a hypothesis property test: a decision is always one of the three values and APPROVE never occurs when any R1-R3 condition holds.
Do not: call any LLM or database. The justification text is added later (Step 16).
Done when: all tests pass and coverage of packages/decision is 100%.
Show me the plan first.
```

## Step 5: Database layer and seed data (done; extended in Step 5b and Step 5c)

```
Step 5: Database models, migrations and seeds.
Read: spec.md section 4; ADR-009; PRD OQ-08.
Goal: Postgres schema and a seeded mock member and claim history store.
Create:
- packages/core/db/ with SQLAlchemy 2 models for cases, agent_runs, decisions, overrides, audit_events, members, claim_history, policies, users.
- Alembic setup and the first migration; audit_events must reject UPDATE and DELETE (trigger).
- Repository classes (CaseRepo, MemberRepo, ClaimHistoryRepo, AuditRepo) with typed methods; no raw SQL in agents later.
- scripts/seed.py: 40 synthetic members and 200 claim_history rows (seeded Faker, reproducible), plus test users for each role with argon2 hashes.
Tests (use a Postgres test container or the compose DB): migration applies cleanly; audit_events update/delete fails; repositories round trip; seed is idempotent.
Do not: build API endpoints.
Done when: `uv run alembic upgrade head` and `uv run python scripts/seed.py` work on a fresh DB and tests pass.
Show me the plan first.
```

---

# Phase 0b: Dataset alignment (new in v0.2)

Run in this order: 5a, then 5b, then 5c. Put the four generator scripts and `scripts_overview.txt` in `data/synthetic/generators/` first. Install their libraries with `uv add --group data pillow numpy fpdf2`.

## Step 5a: Fix and instrument the dataset generators

Attach `data/synthetic/generators/generate_docs.py` and `docs/spec.md`.

```
Step 5a: Fix and instrument the dataset generator generate_docs.py. Do not redesign it.
Make only these changes:
1. Seed everything at the top: random.seed(42) and np.random.seed(42).
2. save_image: call r = rng.random() every time (keep the random stream stable), then apply the effect if blur or r < 0.4, so blur=True always blurs.
3. generate_id_document: for drivers_license and passport pass tampered=("tampered_id" in c["edge_flags"]) and display_name=c["id_display_name"]. In generate_patient_clusters force id_type="drivers_license" when fraud_reason == "name_mismatch" or the cluster is in tampered_idx. Make the tampered ID visibly different (altered expiry date text differing from the barcode/footer text).
4. Force claim_type="CMS1500" when fraud_reason == "amount_under_10k" or the cluster is in missing_fld_idx.
5. Make metadata file_path relative to the dataset folder.
6. Record ground truth. Add a module-level TRUTH dict keyed by doc_id and fill it where values are computed:
   claim forms: claim_amount (the exact printed total), cpt_codes, icd10_code (primary) and icd10_codes (every ICD-10 code printed, primary first), provider_npi (null when printed as missing), service_date, signature_present;
   discharge: admit_date, discharge_date, icd10_code, icd10_codes (everything printed), cpt_codes;
   prescriptions: rx_date, drug names, which field is missing (dea, dosage, refills, drug_name);
   IDs: printed name, printed expiry date, expired (bool), tampered (bool);
   all: patient_id, policy_number, cluster_id, and reference_date (the cluster's treatment date).
   Write TRUTH to dataset/truth.json and clusters (default=str) to dataset/clusters.json. For readmission and date_conflict clusters also record the prior-stay or claim date that a history table would need (prior_discharge_date, claim_service_date). Readmission rule: prior_discharge_date must be 5 to 20 days BEFORE admit_date. Date-conflict rule: rx_date more than 30 days after claim_service_date.
7. Add expected_decision to every metadata entry using the table in this message.
Do not change layouts or fonts. Show the plan first and list every function you will touch.
Done when: running it twice gives byte-identical files (compare checksums), truth.json has an entry for every doc_id, and no name_mismatch or tampered cluster uses an unsupported ID type.
```

Paste this table into the prompt as "the table in this message":

```
Populate expected_decision using exactly these rules (spec.md section 11). Allowed values: APPROVE, REJECT, ESCALATE.
Apply in order, first match wins:
1. Unknown, policy amendment, or any fraud-labeled document -> ESCALATE
2. ID: tampered -> ESCALATE
3. ID: expired -> REJECT
4. Claim form with an uncovered procedure or a missing field, or prescription with a missing field -> REJECT
5. Everything else (including IDs that are only expiring soon, and discharge summaries) -> APPROVE
Read the inputs (tampered, expired, missing field type, fraud scenario) from the data the generator already holds. If inputs are absent or contradict each other, list the document in a report and leave its label unset. Do not guess.
```

Run order for the whole dataset, from `data/synthetic/`:

```bash
uv run python generators/generate_docs.py
POLICY_OUT_DIR=dataset/policies uv run python generators/generate_gold_policy.py
uv run python generators/generate_silver_policy.py
uv run python generators/generate_unknown.py
```

Then ask Copilot for one more small change in `generate_unknown.py`: remove existing `unknown_*` entries from `metadata.json` before appending, and write relative paths (otherwise each rerun duplicates the 4 entries). Run everything twice into two folders and compare checksums. Copy the two policy PDFs to `data/policies/`. If `dataset/` is under about 100 MB, commit it; otherwise use Git LFS. Commit as `step 5a: synthetic dataset` and treat it as frozen.

Expected counts as a sanity check: about 94 APPROVE, 18 REJECT, 43 ESCALATE across 155 documents. A large difference means a scenario was mapped wrongly.

## Step 5b: Retrofit Steps 3 to 5 to spec v0.2

```
Step 5b: Align the finished Phase 0 code with spec.md v0.2. Read the Changelog at the end of spec.md first.
Read: spec.md Changelog, sections 3, 4, 5, 7.8; ADR-003, ADR-009, ADR-013, ADR-014.
Goal: the code from Steps 2 to 5 matches the updated spec, with no regressions.
First do a diff review and show me a table: for each item below, what the code has now and what the spec says. Wait for my OK before changing anything.
Then, one commit-sized change at a time:
1. Settings (packages/core/config.py, .env.example): add APP_ENV (development, test or production; default development), NPI_LUHN_STRICT (default false), ALLOW_RECEIVED_AT_OVERRIDE (default false), NEAR_THRESHOLD_LOW (9500), NEAR_THRESHOLD_HIGH (10000), DATE_CONFLICT_DAYS (30), READMISSION_DAYS (30). Settings must fail at startup when APP_ENV=production and ALLOW_RECEIVED_AT_OVERRIDE=true.
2. Models and enums (packages/core): compare KycFlag codes, ClaimFields and Anomaly detector names with spec section 5. Add what is missing: ID_EXPIRING_SOON in KycFlag; a `warnings: list[str] = []` field on ClaimsResult (NPI_CHECKSUM is a Claims warning, NOT a KycFlag code); a ClaimHistoryKind StrEnum (PRIOR_CLAIM, EPISODE_CLAIM, PRIOR_STAY); and the detector names IDENTITY_MISMATCH, NEAR_THRESHOLD, DATE_CONFLICT, READMISSION_30D. Keep extra="forbid".
3. Decision engine (packages/decision): compare with spec 7.8. Verify and add tests for: policy amendment always ESCALATE unless KYC fails; discharge summary and prescription (policy SKIPPED) reject only on KYC failure or schema_valid false; low-severity and warning flags never change a decision; a claim with schema_valid false and normal confidence is REJECT, not ESCALATE. Change code only where a test fails. Keep 100% coverage.
4. Database: do NOT edit the first Alembic migration. Add a second migration for: cases.received_at (timestamptz, defaults to creation time); claim_history.kind as a TEXT column with a CHECK constraint (not a native Postgres enum), mapped to ClaimHistoryKind, claim_number, admit_date, discharge_date; and a policy_exclusions table as in spec section 4. Update the SQLAlchemy models. Add repository methods: ClaimHistoryRepo (by member and kind, by claim_number), PolicyExclusionRepo.lookup(policy_id, cpt_code) where a code matches when range_start <= code <= range_end as upper-case strings of equal length (policy_exclusions columns: exclusion_id, policy_id, range_start, range_end, category, basis, page; no date columns, effective dates come from the policies row).
Tests: all earlier tests still pass; model tests for the new fields; the migration applies on a fresh DB and on the DB that already has the first migration; repository tests for the new methods.
Do not: touch the dataset, build agents, or change the precedence rules R1 to R4.
Done when: uv run pytest and uv run ruff check . pass and uv run alembic upgrade head works on both a fresh and an existing database.
Show me the plan first.
```

## Step 5c: Integrate the dataset

Attach `docs/spec.md`, `docs/plan.md` and `data/synthetic/generators/scripts_overview.txt`.

```
Step 5c: Integrate the existing synthetic dataset.
Read: spec.md sections 4, 11 and 12; ADR-012, ADR-013; plan.md Steps 5a to 5c.
Context: the dataset is generated and frozen in data/synthetic/dataset/ (151 PNGs in 5 categories, 4 unknown, metadata.json, truth.json, clusters.json) and the two policy PDFs are in data/policies/. Do NOT modify or regenerate the generators or the images.
First, inspect metadata.json, truth.json and clusters.json: list every field name and show me one example entry per category. Report what is present and what is missing compared with the label schema in spec section 11 (doc_type, fields, kyc_expected, coverage_expected, fraud_expected, decision_expected, scenario, reference_date). Wait for my OK before coding.
Then:
1. Create a Pydantic LabelRecord model in packages/eval/labels.py and a script scripts/build_labels.py that converts metadata.json plus truth.json into data/synthetic/labels.jsonl. Map categories to DocType values; keep missing fields as null; never invent expected values; copy expected_decision as is.
2. Create packages/eval/split.py that assigns each document to dev or holdout (about 70/30) stratified by scenario and kept together by patient cluster; write the fixed assignment to data/synthetic/split.json (deterministic, committed).
3. Create scripts/seed_from_dataset.py that builds members and claim_history rows from clusters.json: members from the patients (name, DOB, member ID, policy number); PRIOR_CLAIM rows for ordinary members within normal ranges; an EPISODE_CLAIM row for the date-conflict cluster; a PRIOR_STAY row for the readmission cluster; the original claim of each cluster recorded so that its "_dup" file is detected as a duplicate by claim number. Add a fabricated Silver-plan member for retrieval tests (every generated policy number is Gold). Update scripts/seed.py to call it and keep it idempotent. Tell me whether the earlier random members conflict, and keep or remove them accordingly.
Tests: every label validates; every file listed in labels exists; counts per category are 31, 30, 30, 30, 30, 4; split is deterministic and has no cluster in both sets; seeding is idempotent; every KYC and fraud scenario in the metadata has the member or history data it needs.
Do not: call any LLM, change the decision engine, or edit the images.
Done when: uv run pytest and uv run ruff check . pass, labels.jsonl and split.json exist, and uv run python scripts/seed.py works on a fresh database.
Show me the plan first.
```

**Gate 0.** Tests green, dataset committed, D1 and D2 both confirmed. Then continue with Step 6.

---

# Phase 1: Core pipeline

## Step 6: Ingestion API

```
Step 6: Ingestion API.
Read: spec.md sections 2.2, 8.1, 8.2, 8.4; ADR-005; PRD FR-ING-01..09.
Goal: upload a document and get a case_id.
Create apps/api (FastAPI app factory, routers, dependencies) and packages/core/storage.py (S3/MinIO client wrapper).
Endpoints now: POST /api/v1/cases, GET /api/v1/cases (filter + pagination), GET /api/v1/cases/{id}, GET /health, GET /ready.
Requirements: accept JPEG, PNG, PDF, TIFF only, detected by magic bytes not extension; enforce MAX_UPLOAD_MB; store original unmodified; compute SHA-256; duplicate upload returns the existing case with duplicate_of; status RECEIVED; error format from spec 8.2; return 202. Do NOT enqueue anything yet (leave a clearly marked TODO hook).
Tests: valid upload for each type; wrong type; oversize; duplicate; list filters; storage failure returns a clean error.
Do not: add auth (Step 18) or Celery (Step 12).
Done when: I can upload a file with curl and see the object in MinIO and the row in Postgres.
Show me the plan first.
```

## Step 7: LLM gateway with stub mode

```
Step 7: LLM gateway.
Read: spec.md sections 7.1 and 10; ADR-001.
Goal: one interface for all model calls, runnable offline with fixtures.
Create packages/core/llm/ with: LLMGateway protocol complete_json(model, system, messages, images, schema) -> BaseModel; AnthropicProvider; OpenAIProvider; StubProvider that returns recorded JSON fixtures from data/fixtures/llm/ keyed by prompt name + input hash; retry with jitter on 429/5xx; timeout; one schema-validation retry then raise LLMSchemaError; fallback provider switch; token and latency logging; PHI redaction in logs.
Prompts: loader for packages/agents/prompts/{agent}.{version}.md with front matter (model, temperature, schema).
Config: LLM_PROVIDER=stub|anthropic|openai.
Tests: stub returns fixture; schema failure triggers one retry then error; retries on 429; fallback is used after repeated failure; logs contain no raw field values. Mock the real providers with httpx mocks; do not call the network.
Do not: write agent logic.
Done when: tests pass with no API keys set.
Show me the plan first.
```

## Step 8: Classifier agent

```
Step 8: Classifier agent.
Read: spec.md section 7.2; PRD FR-CLS-01..06.
Goal: classify a document image into the six types with confidence and routing tags.
Create packages/agents/classifier/ (agent.py, prompt classifier.v1.md) and packages/core/documents.py (render PDF/TIFF pages to images with pymupdf/Pillow, downscale to max 1568 px, sample first page plus one later page).
Requirements: uses the LLM gateway only; output validated as Classification; confidence below THRESH_CLASSIFY_REVIEW or UNKNOWN is flagged for review routing; record model, prompt version, raw response reference.
Tests with the stub provider: each of the six types; low confidence; malformed output; multi-page sampling. Use a few real images from data/synthetic/dataset/ as inputs (the ID category also contains member cards and Medicare cards, which must still classify as ID_DOCUMENT).
Do not: call a real model yet; do not build graph wiring.
Done when: tests pass and a small script `scripts/classify_file.py <path>` prints the Classification using stub fixtures.
Show me the plan first.
```

## Step 9: OCR pre-processor

```
Step 9: OCR pre-processor.
Read: spec.md section 7.3; ADR-007; PRD FR-OCR-01..05.
Goal: normalized OcrPayload from any supported file.
Create packages/agents/ocr/ implementing the three tiers: (1) PDF text layer via pymupdf if at least 50 chars per page; (2) deskew/rotate with OpenCV then Tesseract (pytesseract image_to_data); (3) vision LLM fallback via the gateway when mean confidence is below 0.70 or key fields are missing, merging by per-field confidence.
Include the canonical field vocabulary from spec 7.3 and a field-extraction step that maps raw text to fields (regex for IDs, dates, codes; LLM only in the fallback tier).
Add tesseract to the dev setup notes in README and to the Docker image notes.
Tests: text-layer PDF skips OCR; a skewed sample image is corrected; low-confidence triggers fallback (stub); output validates as OcrPayload; empty page handled.
Do not: implement multilingual OCR (bonus, Step 29).
Done when: tests pass and `scripts/ocr_file.py <path>` prints fields.
Show me the plan first.
```

## Step 10: Claims agent

```
Step 10: Claims agent and validators.
Read: spec.md section 7.5; PRD FR-CLM-01..06.
Goal: extract and validate claim fields.
Create packages/agents/claims/ with validators.py (ICD-10 regex, CPT five-character check, NPI: strip the printed "NPI-" prefix, then the Luhn check only appends NPI_CHECKSUM to ClaimsResult.warnings (not a KYC flag, not a validation error, unless NPI_LUHN_STRICT=true) because the dataset NPIs are synthetic; date rules measured against cases.received_at, not today; amount rules) and agent.py (use OCR fields first, targeted LLM extraction via gateway for missing or low-confidence fields, normalization, validation, confidence rule).
Create data/schemas/claim_submission_standard.v1.json (JSON Schema) and validate against it. Mark it clearly as an assumed standard (OQ-04). Required fields differ per document type (spec 7.5 table): for example a prescription has no CPT code or amount.
Tests: table-driven validator tests including edge cases (lowercase codes, bad Luhn, future date, zero amount, missing fields); agent tests with stub; per-field confidence and bounding boxes propagate; a missing required field gives schema_valid=false but confidence stays at normal extraction confidence (it must NOT drop to 0, otherwise rule R1 escalates before R3 can reject); required-field table per document type.
Do not: touch coverage logic.
Done when: tests pass with at least 95% coverage on validators.
Show me the plan first.
```

## Step 11: KYC agent

```
Step 11: KYC agent.
Read: spec.md section 7.4; PRD FR-KYC-01..06.
Goal: identity and document checks against the member database.
Create packages/agents/kyc/ implementing: member lookup (member_id, then policy_number, then date of birth plus fuzzy name for documents that print no identifier), DOB match, fuzzy name match (rapidfuzz token set ratio with thresholds 0.85 and 0.70, but any difference after normalization is still flagged, because the dataset's name mismatch changes one vowel and scores about 95%), policy number and active-on-service-date check, ID expiry and ID_EXPIRING_SOON (LOW, never changes a decision) both measured against cases.received_at, and an LLM tamper check using kyc_tamper.v1.md. Flags use the codes and severities in spec 7.4; kyc_passed = no HIGH flag; tamper-only findings never cause a reject by themselves; confidence rules as in the spec; "member match only" mode for discharge summaries and prescriptions.
Use MemberRepo from Step 5 (seeded from the dataset in Step 5c); no direct SQL.
Tests: each flag alone; combined flags; expired ID; expiring-soon ID; Medicare card that prints an EXPIRED banner instead of a date; name variations (middle initial, case, order) and a one-vowel change; lookup by DOB plus name; no confidence cap for an absent field when another identifier matched; member not found; tamper flag with stub; member-match-only mode.
Do not: implement ELA (bonus, Step 25).
Done when: tests pass using the seeded database.
Show me the plan first.
```

## Step 12: LangGraph wiring and Celery

```
Step 12: Graph wiring, node wrapper, Celery task.
Read: spec.md sections 6 and 12 (reliability); ADR-002, ADR-004; PRD FR-ORC-01, FR-ORC-08.
Goal: upload a file and have it flow through classify -> ocr -> routed claims/kyc -> join, persisted, using stub LLMs.
Create packages/graph/ (builder.py, routing.py with the routing table, nodes.py, wrapper.py) and apps/worker (Celery app, run_pipeline task).
Requirements:
- instrument() wrapper: audit events NODE_START/NODE_END, timeout, 2 retries with backoff, converts exceptions to an ERROR envelope, persists agent_runs, updates case status.
- Conditional routing by doc_type; UNKNOWN or low confidence goes to mark_needs_review; node failure goes to mark_failed.
- Policy/Fraud/Orchestrator are placeholder nodes returning SKIPPED for now. Policy will run after Claims (OQ-17).
- Routing follows spec 6.2 with D1: discharge summaries and prescriptions run Claims extraction and KYC member match but never reach Policy.
- POST /cases now enqueues run_pipeline; Celery uses acks_late, 3 attempts, dead-letter handling that sets FAILED.
Tests: routing table for every doc type; fan-in waits for all routed nodes; failure paths; idempotent rerun with a new pipeline_run; integration test uploading a file through the API with a stub provider and an eager Celery.
Do not: implement Policy, Fraud or decision logic.
Done when: uploading via curl results in a case moving RECEIVED -> ... -> a final status, with audit_events and agent_runs rows.
Show me the plan first.
```

---

# Phase 2: Coverage, fraud, decision

## Step 13: Policy ingestion

```
Step 13: Policy ingestion (Docling + Qdrant).
Read: spec.md section 7.6 (ingestion); ADR-006; PRD FR-POL-01, 02, 07, 08.
Goal: upload a policy PDF and have it chunked and indexed.
Create packages/rag/ (ingest.py, chunking.py, embeddings.py, store.py) and endpoints POST /api/v1/policies and GET /api/v1/policies; Celery task ingest_policy.
Requirements: Docling parse; heading-based chunking 400-800 tokens with 80 overlap, tables kept whole when under 1000 tokens; chunk_type tagging; payload fields policy_id, version, section_path, page, effective_from, effective_to; local embedding model from settings; Qdrant collection with dense and sparse vectors; status PENDING -> READY or FAILED with chunk_count.
Do NOT generate sample policies. Use the existing medishield_gold_plan.pdf and medishield_silver_plan.pdf in data/policies/. Each has 10 bookmarked sections and a machine-readable "Excluded CPT Code Ranges" table: parse that table into policy_exclusions rows (exclusion_id, policy_id, range_start, range_end, category, basis, page; ranges may be alphanumeric such as 0001T, V2100, D0100, so keep them as text) during ingestion, in addition to the chunks.
Tests: chunker unit tests; ingestion of both policies; exclusion table parsed for both (row counts match the PDFs); re-ingestion is idempotent; payload filters work.
Do not: implement the Policy agent.
Done when: both policies show READY with chunk counts and a manual Qdrant query returns relevant chunks.
Show me the plan first.
```

## Step 14: Policy agent

```
Step 14: Policy agent.
Read: spec.md section 7.6 (retrieval); ADR-006; PRD FR-POL-03..06.
Goal: decide coverage for the claim's procedure codes using only retrieved clauses.
Create packages/agents/policy/ and packages/rag/retrieve.py implementing: step 0, a deterministic lookup of each CPT code in policy_exclusions through PolicyExclusionRepo (a hit means covered=False with confidence 0.95, no LLM call); then, for codes not excluded, policy selection from the member's policy number; effective-date filter by service date; per-code queries (CPT lookup table in data/cpt_descriptions.json for ~30 codes); hybrid search with reciprocal rank fusion; rerank to top 5; LLM answer via gateway with prompt policy_decide.v1.md returning covered, coverage_percentage, clause id, exclusions, or null if undecidable; verify the cited text appears verbatim in a retrieved chunk; weak retrieval -> covered=None and low confidence; combine rules across codes (all covered, minimum percentage, exclusions override).
Tests: covered and uncovered codes on both policies; exclusion-table hit returns confidence 0.95 without calling the LLM; exclusion match; hallucinated citation rejected; no relevant clause -> covered None; wrong policy date -> no match.
Do not: change the decision engine; run the Policy agent for discharge summaries or prescriptions (D1).
Done when: tests pass and a script prints the clause and decision for a sample claim.
Show me the plan first.
```

## Step 15: Fraud agent

```
Step 15: Fraud agent.
Read: spec.md section 7.7; ADR-008; PRD FR-FRD-01..06.
Goal: deterministic fraud score with evidence.
Create packages/agents/fraud/ with detectors with the weights in spec 7.7: duplicate (0.90; by claim number or provider NPI + service date + CPT set against PRIOR_CLAIM rows and earlier processed cases, because the dataset's _dup file has a different checksum), frequency spike, provider billing outlier, amount outlier, code mismatch (includes an obstetric CPT such as 59400 with a non-obstetric diagnosis), tamper signal, identity mismatch (KYC NAME_MISMATCH, 0.50), near-threshold (amount from NEAR_THRESHOLD_LOW up to but not including NEAR_THRESHOLD_HIGH, 0.35), date conflict (prescription later than the EPISODE_CLAIM service date by more than DATE_CONFLICT_DAYS, 0.45), readmission (admission within READMISSION_DAYS of a PRIOR_STAY discharge, 0.45), each returning strength and evidence; round the score to 4 decimal places before comparing with a threshold; scorer using noisy-OR with configurable weights in packages/agents/fraud/weights.py; risk level mapping; confidence rules (history size, query failure).
Add data/icd_cpt_plausibility.json (small table). Use ClaimHistoryRepo.
Tests: each detector alone and combined; one test per dataset fraud scenario using the seeded history from Step 5c (the first submission is never flagged as a duplicate); ID documents use only the tamper and identity detectors; score bounds; exact 0.30 and 0.60 boundaries; cold-start member; query failure -> confidence 0.5; evidence strings; property test that adding an anomaly never lowers the score.
Do not: use an LLM for the score.
Done when: tests pass on seeded data with known duplicates.
Show me the plan first.
```

## Step 16: Orchestrator node and justification

```
Step 16: Orchestrator node.
Read: spec.md sections 6.2 and 7.8; ADR-003; PRD FR-ORC-01..09.
Goal: replace the placeholder nodes so the full pipeline produces a decision.
Create the Orchestrator node that calls decide() from packages/decision, then asks the LLM (prompt orchestrator_justify.v1.md) to write a plain-language justification from the rule_trace only; the LLM cannot change the decision (assert in code). Persist decisions with config_snapshot; set final case status; wire Policy and Fraud nodes into the graph (Policy after Claims).
Tests: end-to-end graph tests with stub fixtures for an APPROVE, a REJECT (not covered), a REJECT (KYC), an ESCALATE (fraud), an ESCALATE (agent error), UNKNOWN document; a policy amendment (ESCALATE, D2); a discharge summary (APPROVE without any policy result, D1); justification text cannot flip the decision.
Do not: add auth or UI.
Done when: uploading a sample file yields a decision row with rule_trace and justification.
Show me the plan first.
```

## Step 17: Remaining API endpoints

```
Step 17: Review, audit and override API.
Read: spec.md sections 8.1 and 8.4; PRD FR-UI-04..06.
Goal: everything the UI needs from the backend.
Add endpoints: GET /cases/{id}/audit, GET /review-queue, POST /cases/{id}/override (reason at least 10 chars, original decision preserved, status OVERRIDDEN, audit event), POST /cases/{id}/reclassify, POST /cases/{id}/rerun. Include the full agent outputs and a pre-signed document URL (10 minutes) in GET /cases/{id}.
Tests: override flow keeps the original decision; short reason rejected; review queue contents; rerun creates a new pipeline_run; audit ordering.
Do not: enforce roles yet (Step 18); write UI.
Done when: tests pass and OpenAPI docs at /docs list all endpoints.
Show me the plan first.
```

## Step 18: Authentication and roles

```
Step 18: Auth and RBAC.
Read: spec.md sections 8.1, 8.3 and 15; ADR-010; PRD FR-UI-06, FR-UI-07, NFR-SEC-02/03.
Goal: secure the API.
Implement POST /auth/login (argon2, rate limiting), JWT access tokens with short TTL, FastAPI dependencies require_role(...), the role matrix from spec 8.3, a scoped service token for uploads, CORS limited to the UI origin, and the PHI log-redaction filter applied to all loggers.
Attribute overrides to the authenticated user.
Tests: every endpoint against every role (parametrized matrix); expired and tampered tokens; login rate limit; redaction filter removes member IDs, DOBs and names from log output.
Do not: build the login UI.
Done when: unauthenticated requests get 401 and role violations get 403 across the test matrix.
Show me the plan first.
```

---

# Phase 3: Evaluation and UI

## Step 19: Dataset review and gap-filling

```
Step 19: Review the synthetic dataset against the spec.
Read: spec.md section 11; ADR-012, ADR-013; PRD section 10.
Context: the generators already exist and the dataset is frozen (Steps 5a to 5c). Do not regenerate or edit existing images.
Goal: confirm that every scenario the evaluation needs is present, and fill gaps without changing existing files.
Do:
1. Build a coverage matrix (scripts/dataset_coverage.py): rows are the scenarios in spec 11 (valid, expired ID, tampered ID, duplicate, missing NPI, missing ICD-10, uncovered CPT, billing outlier, rotated, low DPI, noisy scan, prompt injection "approve this claim", unrelated document, blank page, name mismatch, near-threshold, date conflict, readmission); columns are document counts in dev and holdout. Print rows with zero documents.
2. For each empty row, add a small deterministic generator script in data/synthetic/generators/extras/ that writes new documents with new IDs, new labels and truth values, appended to labels.jsonl and split.json (new clusters only).
3. Confirm the split: no cluster in both sets and existing assignments unchanged.
Tests: coverage script runs; extras are deterministic (checksums); every new label validates; split still has no shared cluster.
Do not: change the existing generators, images or labels.
Done when: the coverage matrix has no empty row and the committed split is unchanged for existing clusters.
Show me the plan first.
```

## Step 20: Evaluation harness and first real run

```
Step 20: Evaluation harness.
Read: spec.md section 11; ADR-012; PRD section 10 and acceptance criteria AC-02, AC-03.
Goal: measure classification, extraction and decision quality.
Create packages/eval/ with a runner (uploads each dataset file through the real pipeline code path, waits for completion; sets cases.received_at from each label's reference_date with ALLOW_RECEIVED_AT_OVERRIDE=true; processes a cluster's original claim before its _dup file; assigns the member history from Step 5c), metrics (classification accuracy, extraction completeness against truth.json, decision correctness with confusion matrix and per-scenario, per-document-category and per-split (dev, holdout) breakdown, latency p50/p95, optional calibration/ECE), report writers (JSON and Markdown), a manual retrieval-review sheet generator, and a CLI `uv run python -m packages.eval.run --provider stub|anthropic|openai`. Exit non-zero if decision correctness is below 0.60 or weighted score below 0.70.
Tests: metrics on handcrafted predictions; per-category and per-split breakdown; report generation; exit code logic; runner sets received_at only when the override flag is on.
Then run it once with stub fixtures and once with a real provider (I will set the API key) and show me the report.
Do not: tune prompts yet; first show me the baseline numbers. Tuning later uses dev only; the final numbers are reported on holdout.
Done when: a report file exists with all metrics and sample sizes.
Show me the plan first.
```

After the first real run, iterate with this prompt:

```
Here is the evaluation report: <paste>. Identify the 3 most common failure patterns (use the per-scenario breakdown and the failing case IDs). For each, propose the smallest change (prompt wording, preprocessing, validator rule, threshold) and the expected effect. Wait for my pick, change one thing, rerun the evaluation, and compare against the previous report. Do not change the decision rules in spec section 7.8 without asking me.
```

## Step 21: Next.js app: login, dashboard, case detail

```
Step 21: Frontend foundation.
Read: spec.md section 9; PRD FR-UI-01..03, NFR-UX-01.
Goal: working dashboard and case detail.
Create apps/web (Next.js App Router, TypeScript, Tailwind, TanStack Query). Generate API types from the OpenAPI schema with openapi-typescript. Pages: /login, / (dashboard with status badges, filters, search, pagination, counts), /cases/[id] (document viewer with zoom and page navigation on the left; collapsible per-agent panels, decision panel with confidence, justification and rule trace on the right).
Requirements: badge mapping from spec 9 (icon plus text, not color only); token stored in an httpOnly cookie via a Next route handler; no PHI in localStorage; empty, loading and error states; keyboard accessible.
Tests: Playwright for login, dashboard load, case detail render (against the running API with seeded data).
Do not: build the review queue or policies pages.
Done when: I can log in, see cases, and open one with its agent outputs.
Show me the plan first.
```

## Step 22: Review queue, override, audit log, policies

```
Step 22: Remaining UI.
Read: spec.md section 9; PRD FR-UI-04, 05, 06, 10; AC-06, AC-07.
Goal: complete the operations workflow.
Add: /review (queue of ESCALATE, NEEDS_REVIEW, FAILED cases with age and reason), override dialog (approve, reject, reclassify; reason required, at least 10 characters), audit log tab on case detail, click-to-highlight of extracted fields on the document image, /policies (list, upload, ingestion status). Hide actions by role (reviewer, supervisor, auditor read-only, admin).
Tests: Playwright: escalated case -> override with reason -> status OVERRIDDEN and original decision still visible, audit shows the override; auditor cannot see override buttons; policy upload shows status.
Do not: add WebSockets yet.
Done when: AC-06 and AC-07 pass by hand and in Playwright.
Show me the plan first.
```

## Step 23: Docs, diagram, CI

```
Step 23: Documentation and CI.
Read: PRD deliverables 6 and 7; spec.md section 14.
Goal: a repo someone else can run.
Create: README.md (overview, architecture, prerequisites with uv/Node/Docker/Tesseract, environment variables table, setup in under 10 commands, how to run API, worker, web, seed, evaluation, tests, a walkthrough of one end-to-end case with sample commands and expected outputs), docs/architecture.md with a Mermaid diagram showing actual component names, models and data flow, and a GitHub Actions workflow running ruff, mypy on core and decision, pytest, gitleaks and the web build.
Check: no secrets in the repo; .env.example is complete.
Done when: a fresh clone follows the README and reaches a decided case.
Show me the plan first.
```

---

# Phase 4: Bonus (only after the pass threshold is met)

## Step 24: WebSocket live status

```
Step 24: Live status.
Read: ADR-011; PRD FR-UI-08.
Publish events from the node wrapper to Redis; add WS /cases/{id}/events with JWT auth that closes at a terminal state; UI timeline updates from events with a polling fallback every 5 seconds. Tests: events arrive in order; unauthorized socket rejected; fallback works when the socket is blocked.
```

## Step 25: ELA tamper detection

```
Step 25: ELA.
Read: spec.md section 7.4; PRD FR-KYC-05.
Create packages/forensics/ela.py (JPEG re-save at quality 90, difference map, region statistics, threshold from a calibration script over the dataset) and add the ELA_ANOMALY flag (MEDIUM only) to the KYC agent. Tests: untouched vs pasted-over images from the dataset; PNG inputs skipped; false-positive rate reported.
```

## Step 26: Calibration plot

```
Step 26: Calibration.
Read: spec.md section 11; PRD bonus "Confidence Calibration".
Add a reliability diagram (5 bins) and ECE to the evaluation report using orchestrator confidence versus decision correctness; state the small sample size and show bin counts. Do not change the confidence formula; only report.
```

## Step 27: PDF case report

```
Step 27: Case report.
Read: PRD FR-UI-09.
Add GET /cases/{id}/report generating a PDF (reportlab) with case summary, document thumbnail, each agent's output, decision, rule trace, overrides and audit timeline; add a Download Case Report button in the UI. Tests: PDF generated and contains the case_id and decision; auditor role allowed.
```

## Step 28: LangSmith tracing

```
Step 28: Tracing.
Read: NFR-OBS-02, NFR-SEC-04.
Enable LangSmith behind LANGSMITH_ENABLED (default false), with a processor that redacts PHI fields from inputs and outputs, and document in the README that it must stay off for real PHI unless approved. Tests: redaction applied; disabled by default; no network call when disabled.
```

## Step 29: Multilingual OCR

```
Step 29: Spanish and Hindi.
Read: PRD FR-OCR-05, OQ-16.
Add Tesseract language packs (spa, hin), language detection per page, and fixtures in the dataset (3 Spanish, 3 Hindi documents). Report extraction completeness separately by language. Do not change the English path.
```

---

# Prompts for when things go wrong

**A test fails and you do not know why**
```
`uv run pytest <path>` fails with: <paste output>. Explain the root cause in two sentences, propose the smallest fix, and show the diff. Do not change the test unless the test itself is wrong, and tell me if you think it is.
```

**The assistant is doing too much**
```
Stop. You changed files outside Step <N>. List every file you touched, revert anything not required for this step, and continue only with the step's scope.
```

**Review before commit**
```
Review the uncommitted changes against spec.md and adr.md. List: (1) requirement IDs satisfied, (2) deviations from the spec, (3) missing tests, (4) any hardcoded secret or PHI in logs. Be concise.
```

**A decision needs to change**
```
I want to change <X>. Which ADRs and spec sections does this affect? Draft the updated ADR text (new status line, what is superseded) and list the code that would change. Do not edit code yet.
```

**Start of each new session**
```
Read CLAUDE.md, docs/spec.md and docs/adr.md. Tell me which step we are on (git log helps), what is done, and what Step <N> needs. Do not write code yet.
```
