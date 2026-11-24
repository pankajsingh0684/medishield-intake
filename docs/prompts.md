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

## Output rules (saves tokens)

Add this once to `CLAUDE.md` or `.github/copilot-instructions.md`, so it does not have to be repeated in every prompt:

```
Output rules: write reports and long listings to a file under reports/ and show me only a summary of at most 15 lines:
changed file paths, test and ruff results (last lines only), and any deviation from the spec. Do not print file contents,
per-document tables or full logs. Do one request at a time; if a step also needs a measurement, use --sample N and the cache instead of a full run.
```

Other habits that save time: start a new chat for each step and attach only the files the step needs; say "Read only spec sections X and Y"; reply "OK, proceed" to a plan instead of re-explaining; use `--sample` for iterations and run the full dataset once at the end of a step.

## Suggested model per step

| Model | Steps |
| --- | --- |
| Strong (hard design or many moving parts) | 12 graph wiring, 14 policy agent, 16 orchestrator, 20 evaluation |
| Standard | 9b, 10, 11, 13, 15, 18, 22 |
| Fast (mostly mechanical) | 17, 19, 21, 23, and the Phase 4 bonus steps |

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

Expected counts as a sanity check: about 94 APPROVE, 18 REJECT, 43 ESCALATE across the original 155 documents (149 / 22 / 67 across 238 after Step 19). A large difference means a scenario was mapped wrongly.

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
4. Database: do NOT edit the first Alembic migration. Add a second migration for: cases.received_at (timestamptz, defaults to creation time); claim_history.kind as a TEXT column with a CHECK constraint (not a native Postgres enum), mapped to ClaimHistoryKind, claim_number, admit_date, discharge_date; and a policy_exclusions table as in spec section 4. Update the SQLAlchemy models. Add repository methods: ClaimHistoryRepo (by member and kind, by claim_number), PolicyExclusionRepo.lookup(policy_id, cpt_code) where a code matches when it has the same shape class as the range (digits only, digits ending in a letter, or a leading letter) and range_start <= code <= range_end as upper-case strings; any matching range counts (policy_exclusions columns: exclusion_id, policy_id, range_start, range_end, category, basis, page; no date columns, effective dates come from the policies row).
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

## Step 5d: Local credentials for all four services

Run this once, before Step 7. Use the corrected `.env.example` as the template (placeholders only, `LLM_PROVIDER=stub`, `127.0.0.1` everywhere, `REDIS_PASSWORD`, `LLM_RECORD_FIXTURES=false`, empty `GROQ_API_KEY`).

```
Task: make local credentials explicit, consistent and safe for Postgres, Redis, MinIO and Qdrant. Do not commit anything. Never print or echo real secrets in your output; show only variable names and whether they are set.

Part A: audit (change nothing yet). For each service, report:
1. Which variables infra/docker-compose.yml reads, and where each value actually comes from now (.env, .env.example, a default in the compose file, or an inherited shell variable).
   - Postgres: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
   - Redis: whether a password is required (requirepass) now
   - MinIO: root user and password, bucket names
   - Qdrant: whether an API key is required now
2. Whether .env exists and whether it is ignored by git (git check-ignore .env).
3. Whether .env.example contains any real-looking secret. It must only contain obvious placeholders such as replace-with-... or change-me.
4. Which variables the app uses to reach each service (DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, S3 endpoint/access key/secret key/buckets, QDRANT_URL, QDRANT_API_KEY), and whether the values match the compose credentials.
5. Where the medishield_test database and the medishield-documents / medishield-documents-test buckets are created now.
6. Whether the healthchecks and the Celery/app clients can still connect once Redis, MinIO and Qdrant have credentials.
Then stop and wait for my OK.

Part B: after my OK, in this order:
1. Replace .env.example with the version I give you, exactly as written. Create .env from it if missing. Generate a random value for each secret (openssl rand -hex 16 or Python secrets) and write it only into .env:
   POSTGRES_PASSWORD, REDIS_PASSWORD, S3_SECRET_KEY (at least 8 characters), QDRANT_API_KEY, JWT_SECRET, SEED_TEST_USER_PASSWORD.
   Keep the same value consistent everywhere it is used (compose, DATABASE_URL, TEST_DATABASE_URL, REDIS_URL, S3 keys, QDRANT_API_KEY).
   Ensure .env is in .gitignore. Keep LLM_PROVIDER=stub.
2. Update infra/docker-compose.yml to read every secret from .env with no hardcoded defaults for secrets:
   Redis started with --requirepass, MinIO with its root user and password taken from S3_ACCESS_KEY and S3_SECRET_KEY, Qdrant with QDRANT__SERVICE__API_KEY.
   Healthchecks must authenticate. Keep all ports bound to 127.0.0.1.
3. Update packages/core/config.py Settings for the new variables (required ones without defaults), including REDIS_PASSWORD, and update the Redis, S3 and Qdrant clients to use them.
   Make the app refuse to start when APP_ENV=production and any secret still starts with "replace-with". Test that it fails in production and does not fail in development or test.
   Add tests that missing secrets raise a clear error.
4. Before any reset, tell me exactly which volumes `docker compose -f infra/docker-compose.yml down -v` will delete (by name) and what data is lost, then wait for my OK. Then run it, followed by `up -d`, and wait until all four services are healthy.
5. Make initialization repeatable in one script (for example scripts/init_local.sh): create the medishield_test database, the medishield-documents and medishield-documents-test buckets, and any Qdrant collection needed later, only if they do not exist.
6. Run `uv run alembic upgrade head`, then `uv run python scripts/seed.py` for the development database.
7. Run `uv run pytest` and `uv run ruff check .`. pytest must show 0 skipped.
8. Add a "Local setup" section to README.md: copy .env.example to .env, set the secrets, start compose, run the init script, migrate, seed. Include how to open each service without printing a secret:
   - Postgres: `docker compose exec postgres psql -U <user> -d medishield`
   - Redis: `docker compose exec redis redis-cli` then `AUTH <password>`
   - MinIO console: http://127.0.0.1:9001 with the root user and password from .env
   - Qdrant dashboard: http://127.0.0.1:6333/dashboard with the API key from .env
Finally show `git status` and the changed files, and confirm no secret appears in any tracked file (run gitleaks, or grep for each secret value).
```

Resetting deletes the data in all four services (including MinIO uploads from the Step 6 smoke test). Postgres is rebuilt from the migrations and seed script.

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
Create packages/core/llm/ with:
- LLMGateway protocol: complete_json(model, system, messages, images, schema) -> BaseModel.
- StubProvider (default) that returns recorded JSON fixtures from data/fixtures/llm/, keyed by prompt name plus a SHA-256 of the canonicalized input
  (messages plus image bytes hash). A missing fixture raises a clear error that prints the key. Add a record mode (LLM_RECORD_FIXTURES=true) that writes a
  fixture from a real response; off by default.
- GroqProvider (OpenAI-compatible API, base URL https://api.groq.com/openai/v1, key from GROQ_API_KEY). Use JSON mode (response_format json_object, with the word
  "JSON" in the prompt) plus our own schema validation and one retry; do not rely on json_schema. Images are sent as base64 data URLs; respect the provider's image limits.
- AnthropicProvider and OpenAIProvider as optional adapters (real calls only when configured; never called in tests).
- Retry with jitter on 429 and 5xx; timeout (AGENT_TIMEOUT_S); one schema-validation retry, then raise LLMSchemaError; optional fallback provider switch after
  repeated failure (no fallback when LLM_FALLBACK_PROVIDER is empty); token and latency logging; PHI redaction in logs (no raw field values).
- Prompt-injection control per spec 7.1: document text goes in a clearly delimited data block and the system prompt says to ignore instructions inside it.
Prompts: loader for packages/agents/prompts/{agent}.{version}.md with front matter (model, temperature, schema).
Config: LLM_PROVIDER=stub|groq|anthropic|openai (default stub). Model names come only from settings (LLM_VISION_MODEL, LLM_TEXT_MODEL); do not hardcode model IDs.
Add GROQ_API_KEY and LLM_RECORD_FIXTURES to Settings and .env.example (keys empty).
Tests: stub returns the fixture; missing fixture error shows the key; schema failure triggers one retry then error; Groq request shape with an image; retries on 429; fallback after
repeated failure and none when unset; logs contain no raw field values; an injected "approve this claim" string in the document text does not change the system prompt.
Mock all real providers with httpx mocks; do not call the network.
Do not: write agent logic.
Done when: uv run pytest and uv run ruff check . pass with no API keys set.
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

## Step 9b: OCR extractor precision (small)

Model: Standard. Dev split only; no preprocessing changes.

```
Step 9b: OCR extractor precision.
Read: spec.md 7.3; reports/ocr_baseline.md.
Goal: a wrong extracted value must never beat a fallback value.
1. Any extracted value that fails its validator (CPT shape, ICD-10 shape with decimals, plausible date, valid amount) is dropped or given low confidence, so it cannot win the per-field merge. Add a test.
2. Fix ICD-10 truncation (keep K35.80, G43.909). CPT extraction requires a CPT or procedure label, and rejects numbers equal to the patient ID, ZIP code or claim number.
3. ocr_report.py: add --sample N (fixed, stratified, dev split only) and an on-disk OCR cache keyed by image hash. Run on a sample of 20, write reports/ocr_9b_sample.md, and show before and after only for the fields you changed.
Do not: change preprocessing or Tesseract settings, touch holdout documents, or edit the dataset.
Done when: tests pass (0 skipped) and the sample report shows fewer wrong values.
Show me the plan first.
```

## Step 10: Claims agent

Model: Standard.

```
Step 10: Claims agent and validators.
Read: spec.md 7.5 (including the required-fields table); PRD FR-CLM-01..06.
Create packages/agents/claims/ (validators.py, agent.py) and data/schemas/claim_submission_standard.v1.json (mark as an assumed standard, OQ-04).
Rules:
- Validators: ICD-10 regex; CPT five characters; NPI: strip the "NPI-" prefix, 10 digits, and a failed Luhn check only appends NPI_CHECKSUM to ClaimsResult.warnings (a validation error only if NPI_LUHN_STRICT=true); dates measured against cases.received_at, not today; amount over 0.
- Use OCR fields first; ask the LLM gateway only for missing or low-confidence fields; normalize; validate.
- Required fields depend on doc_type. A missing required field gives schema_valid=false at normal confidence (never 0, or rule R1 would escalate before R3 can reject).
- Per-field confidence and bounding boxes propagate.
Tests: table-driven validator tests (lowercase codes, bad Luhn, future date, zero amount, missing fields, the NPI prefix); agent tests with the stub; a prescription needs no CPT or amount.
Do not: touch coverage logic.
Done when: tests pass (0 skipped), at least 95% coverage on validators.
Show me the plan first.
```

## Step 11: KYC agent

Model: Standard.

```
Step 11: KYC agent.
Read: spec.md 7.4; PRD FR-KYC-01..06.
Create packages/agents/kyc/ using MemberRepo (no direct SQL). Implement:
- Lookup: member_id, then policy_number, then date of birth plus fuzzy name for documents that print no identifier.
- DOB match; fuzzy name (rapidfuzz token set ratio, thresholds 0.85 and 0.70) but ANY difference after normalization is flagged, because the dataset's name mismatch changes one vowel and still scores about 95%.
- Policy number and active-on-service-date check; ID expiry and ID_EXPIRING_SOON (LOW, never changes a decision), both measured against cases.received_at; Medicare cards print an EXPIRED banner instead of a date.
- LLM tamper check with prompt kyc_tamper.v1.md; tamper-only findings never reject by themselves. kyc_passed = no HIGH flag.
- "Member match only" mode for discharge summaries and prescriptions.
Tests: each flag alone and combined; expired and expiring-soon IDs; name variations (middle initial, case, order) and a one-vowel change; lookup by DOB plus name; member not found; tamper flag with the stub; member-match-only mode. Use the seeded dataset members.
Do not: implement ELA (Step 25).
Done when: tests pass (0 skipped).
Show me the plan first.
```

## Step 12: LangGraph wiring and Celery

Model: Strong.

```
Step 12: Graph wiring, node wrapper, Celery task.
Read: spec.md 6 and 12 (reliability); ADR-002, ADR-004; PRD FR-ORC-01, FR-ORC-08.
Goal: upload a file and have it flow classify -> ocr -> routed claims/kyc -> join, persisted, using the stub provider.
Create packages/graph/ (builder.py, routing.py with the routing table, nodes.py, wrapper.py) and apps/worker (Celery app, run_pipeline task; Redis with the password from settings).
- instrument() wrapper: audit events NODE_START and NODE_END, timeout, 2 retries with backoff, exceptions become an ERROR envelope, persists agent_runs, updates case status.
- Routing by doc_type (spec 6.2, D1: discharge summaries and prescriptions run Claims extraction and KYC member match, never Policy). Route to mark_needs_review when doc_type == UNKNOWN or "NEEDS_REVIEW" is in routing_tags; any ERROR also goes to review; node failure goes to mark_failed.
- Policy, Fraud and Orchestrator are placeholder nodes returning SKIPPED. Policy will run after Claims (OQ-17).
- POST /cases now enqueues run_pipeline (replace the Step 6 TODO). Celery: acks_late, 3 attempts, dead-letter handling sets FAILED.
Tests: routing table for every doc_type; fan-in waits for all routed nodes; failure paths; idempotent rerun with a new pipeline_run; an integration test through the API with the stub and eager Celery, using dataset fixtures.
Do not: implement Policy, Fraud or decision logic.
Done when: uploading with curl moves a case from RECEIVED to a final status, with audit_events and agent_runs rows.
Show me the plan first.
```

---

# Phase 2: Coverage, fraud, decision

## Step 13: Policy ingestion

Model: Standard.

```
Step 13: Policy ingestion (Docling + Qdrant).
Read: spec.md 7.6 (ingestion); ADR-006; PRD FR-POL-01, 02, 07, 08.
Create packages/rag/ (ingest.py, chunking.py, embeddings.py, store.py), endpoints POST /api/v1/policies and GET /api/v1/policies, and the Celery task ingest_policy.
- Do NOT generate policies. Use data/policies/medishield_gold_plan.pdf and medishield_silver_plan.pdf.
- Docling parse; heading-based chunks of 400 to 800 tokens with 80 overlap; keep tables whole under 1000 tokens; chunk_type tags; payload: policy_id, version, section_path, page, effective_from, effective_to; local embedding model from settings; dense and sparse vectors.
- Check the policy_chunks collection that scripts/init_local.py created; recreate it if its configuration does not match.
- Parse each PDF's "Excluded CPT Code Ranges" table into policy_exclusions rows (range_start, range_end, category, basis, page; ranges may be alphanumeric, keep text).
- Status PENDING -> READY or FAILED with chunk_count.
Tests: chunker unit tests; both policies ingest; exclusion row counts match the PDFs; re-ingestion is idempotent; payload filters work.
Do not: implement the Policy agent.
Done when: both policies are READY with chunk counts and a manual Qdrant query returns relevant chunks.
Show me the plan first.
```

## Step 14: Policy agent

Model: Strong.

```
Step 14: Policy agent.
Read: spec.md 7.6 (retrieval); ADR-006; PRD FR-POL-03..06.
Create packages/agents/policy/ and packages/rag/retrieve.py.
- Step 0, deterministic: look up each CPT code with PolicyExclusionRepo.lookup(policy_id, cpt_code). A hit means covered=False with confidence 0.95 and no LLM call.
- Other codes: select the policy from the member's policy number; filter by service date; per-code queries (CPT lookup table data/cpt_descriptions.json, about 30 codes); hybrid search with reciprocal rank fusion; rerank to the top 5; LLM answer through the gateway (policy_decide.v1.md) returning covered, coverage_percentage, clause id, exclusions, or null; verify the cited text appears verbatim in a retrieved chunk; weak retrieval gives covered=None and low confidence; combine across codes (all covered, minimum percentage, exclusions override).
Tests: covered and uncovered codes on both policies; exclusion-table hit gives 0.95 without an LLM call; a numeric code such as 00020 does not match 0001T-0099T; a claim with one excluded code (17000) and one covered code (93306) is not covered; overlapping ranges are handled; hallucinated citation rejected; no relevant clause gives covered None; wrong policy date gives no match; a fabricated Silver member selects the Silver policy.
Do not: change the decision engine; run Policy for discharge summaries or prescriptions (D1).
Done when: tests pass (0 skipped) and a script prints the clause and decision for a sample claim.
Show me the plan first.
```

## Step 15: Fraud agent

Model: Standard.

```
Step 15: Fraud agent.
Read: spec.md 7.7; ADR-008; PRD FR-FRD-01..06.
Create packages/agents/fraud/ using ClaimHistoryRepo; scorer: noisy-OR with weights in weights.py; round the score to 4 decimal places before comparing with a threshold.
Detectors and weights (spec 7.7): duplicate 0.90 (same member and claim number, or same NPI, service date and CPT set, as a PRIOR_CLAIM row or an earlier processed case; the first submission is never flagged; the dataset's _dup file has a different hash), frequency spike 0.45, provider billing outlier 0.40, amount outlier 0.35 (skipped for codes without a reference price), code mismatch 0.40 (includes an obstetric CPT such as 59400 with a non-obstetric diagnosis; data/icd_cpt_plausibility.json), tamper signal 0.40, identity mismatch 0.50 (KYC NAME_MISMATCH), near-threshold 0.35 (amount from NEAR_THRESHOLD_LOW up to but not including NEAR_THRESHOLD_HIGH), date conflict 0.45 (prescription later than the EPISODE_CLAIM by more than DATE_CONFLICT_DAYS), readmission 0.45 (admission within READMISSION_DAYS of a PRIOR_STAY discharge).
ID documents use only the tamper and identity detectors. Risk levels at 0.30 and 0.60. Confidence 0.9 with at least 3 history claims, else 0.7; 0.5 on query failure.
Tests: each detector alone and combined; one test per dataset fraud scenario using the Step 5c seeds; exact 0.30 and 0.60 boundaries; cold-start member; query failure; a property test that adding an anomaly never lowers the score; clean cases do not trigger frequency or billing detectors.
Do not: use an LLM for the score.
Done when: tests pass (0 skipped).
Show me the plan first.
```

## Step 16: Orchestrator node and justification

Model: Strong.

```
Step 16: Orchestrator node.
Read: spec.md 6.2 and 7.8; ADR-003, ADR-014; PRD FR-ORC-01..09.
Goal: replace the placeholder nodes so the full pipeline produces a decision.
- Orchestrator node calls decide() from packages/decision, then asks the LLM (orchestrator_justify.v1.md) to write a justification from the rule_trace only. Assert in code that the LLM cannot change the decision. Persist decisions with a config snapshot and the reference date used; set the final case status.
- Wire Policy (after Claims) and Fraud into the graph.
Tests (stub fixtures): APPROVE; REJECT (not covered); REJECT (KYC); ESCALATE (fraud); ESCALATE (agent error); UNKNOWN document; policy amendment (ESCALATE, D2); discharge summary (APPROVE with no policy result, D1); the justification cannot flip the decision.
Do not: add auth or UI.
Done when: uploading a sample file yields a decision row with rule_trace and justification.
Show me the plan first.
```

## Step 17: Review, audit and override API

Model: Fast.

```
Step 17: Review, audit and override API.
Read: spec.md 8.1 and 8.4; PRD FR-UI-04..06.
Add: GET /cases/{id}/audit, GET /review-queue, POST /cases/{id}/override (reason of at least 10 characters, original decision preserved, status OVERRIDDEN, audit event), POST /cases/{id}/reclassify, POST /cases/{id}/rerun. GET /cases/{id} includes the full agent outputs and a pre-signed document URL (10 minutes).
Tests: override keeps the original decision; short reason rejected; review queue contents; rerun creates a new pipeline_run; audit ordering.
Do not: enforce roles (Step 18) or write UI.
Done when: tests pass (0 skipped) and /docs lists every endpoint.
Show me the plan first.
```

## Step 18: Authentication and roles

Model: Standard.

```
Step 18: Auth and RBAC.
Read: spec.md 8.1, 8.3 and 15; ADR-010; PRD FR-UI-06, FR-UI-07, NFR-SEC-02/03.
Implement POST /auth/login (argon2, rate limit), short-TTL JWT, require_role(...) dependencies, the role matrix from spec 8.3, a scoped service token for uploads, CORS limited to the UI origin, and the PHI log-redaction filter on all loggers. Attribute overrides to the authenticated user.
Tests: every endpoint against every role (parametrized matrix); expired and tampered tokens; login rate limit; the redaction filter removes member IDs, DOBs and names from log output.
Do not: build the login UI.
Done when: unauthenticated requests get 401 and role violations get 403 across the matrix.
Show me the plan first.
```

---

# Phase 3: Evaluation and UI

## Step 19: Dataset review and gap-filling

Model: Fast.

```
Step 19: Dataset review.
Read: spec.md 11; ADR-012, ADR-013.
The dataset is frozen. Do not regenerate or edit existing images or labels.
1. scripts/dataset_coverage.py: a matrix of scenarios (valid, expired ID, tampered ID, duplicate, missing NPI, missing ICD-10, uncovered CPT, billing outlier, rotated, low DPI, noisy scan, prompt injection "approve this claim", unrelated document, blank page, name mismatch, near-threshold, date conflict, readmission) by document counts in dev and holdout. Print rows with zero documents and scenarios with no holdout document.
2. For each gap, add a small deterministic generator in data/synthetic/generators/extras/ writing NEW documents with new IDs, labels and truth values, appended to labels.jsonl and split.json (new clusters only). Add a second cluster for each single-cluster scenario (amount under 10k, date conflict, duplicate claim, name mismatch, code mismatch, readmission) and assign them to holdout.
Tests: extras are deterministic; new labels validate; the split keeps no cluster in both sets and existing assignments unchanged.
Done when: the matrix has no empty row and every scenario has a holdout document.
Show me the plan first.
```

## Step 20: Evaluation harness and first real run

Model: Strong.

```
Step 20: Evaluation harness.
Read: spec.md 11; ADR-012, ADR-013; PRD section 10; AC-02, AC-03.
Create packages/eval/: a runner (uploads each dataset file through the real code path; sets cases.received_at from each label's reference_date with ALLOW_RECEIVED_AT_OVERRIDE=true, DATASET_AS_OF_DATE for unknowns; processes a cluster's original claim before its _dup file; uses the Step 5c history), metrics (classification accuracy; extraction completeness against truth.json; decision correctness with a confusion matrix and per-scenario, per-category and per-split breakdown; latency p50 and p95; optional calibration), report writers (JSON and Markdown), a retrieval review sheet generator, and the CLI `uv run python -m packages.eval.run --provider stub|groq|anthropic|openai --split dev|holdout|all [--sample N]`. Exit non-zero when decision correctness is below 0.60 or the weighted score is below 0.70.
Add an on-disk cache of model responses keyed by input hash so reruns are cheap.
Tests: metrics on handcrafted predictions; breakdowns; report generation; exit codes; received_at set only when the override flag is on.
First run with the stub, then (I will set the key and confirm the model IDs) with the real provider on dev only, and show me the report summary.
Do not: tune prompts yet. Tuning uses dev; final numbers use holdout.
Done when: a report file exists with all metrics and sample sizes.
Show me the plan first.
```

After the first real run, iterate with:

```
Evaluation summary: <paste the summary only>. Name the 3 most common failure patterns (per-scenario breakdown and failing case IDs). For each, propose the smallest change (prompt wording, preprocessing, validator, threshold) and its expected effect. Wait for my pick, change one thing, rerun on dev with --sample, and compare. Do not change the decision rules in spec 7.8 without asking me.
```

## Step 21: Next.js app: login, dashboard, case detail

Model: Fast. Keep the UI plain; function over polish.

```
Step 21: Frontend foundation.
Read: spec.md 9; PRD FR-UI-01..03, NFR-UX-01.
Create apps/web (Next.js App Router, TypeScript, Tailwind, TanStack Query) with API types generated from the OpenAPI schema. Pages: /login, / (dashboard: status badges with icon plus text, filters, search, pagination, counts), /cases/[id] (document viewer with zoom and page navigation; collapsible per-agent panels; decision panel with confidence, justification and rule trace).
Token in an httpOnly cookie through a Next route handler; no PHI in localStorage; empty, loading and error states; keyboard accessible.
Tests: Playwright for login, dashboard load and case detail (against the running API with seeded data).
Do not: build the review queue or policies pages.
Done when: I can log in, see cases and open one with its agent outputs.
Show me the plan first.
```

## Step 22: Review queue, override, audit log, policies

Model: Standard.

```
Step 22: Remaining UI.
Read: spec.md 9; PRD FR-UI-04, 05, 06, 10; AC-06, AC-07.
Add: /review (ESCALATE, NEEDS_REVIEW and FAILED cases with age and reason); override dialog (approve, reject, reclassify; reason of at least 10 characters); audit tab on case detail; click-to-highlight of extracted fields on the document; /policies (list, upload, ingestion status). Hide actions by role (auditor is read-only).
Tests: Playwright: escalated case -> override with reason -> OVERRIDDEN, original decision still visible, audit shows it; the auditor sees no override buttons; policy upload shows status.
Do not: add WebSockets.
Done when: AC-06 and AC-07 pass by hand and in Playwright.
Show me the plan first.
```

## Step 23: Docs, diagram, CI

Model: Fast.

```
Step 23: Documentation and CI.
Read: PRD deliverables 6 and 7; spec.md 14.
Create: README.md (overview, architecture, prerequisites including uv, Node, Docker and Tesseract, environment variables table, setup in under 10 commands, how to run the API, worker, web, seed, evaluation and tests, one end-to-end case with sample commands and expected output); docs/architecture.md with a Mermaid diagram using the real component and model names; a GitHub Actions workflow running ruff, mypy on core and decision, pytest, gitleaks and the web build.
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
