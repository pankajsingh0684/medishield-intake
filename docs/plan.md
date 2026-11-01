# Implementation Plan: MediShield Multi-Agent Document Intake System

| Field | Value |
| --- | --- |
| Version / status | v0.2, in progress (Phase 0 steps 1 to 5 done) |
| Date | 2026-10-31 |
| Inputs | PRD v0.1, `spec.md` v0.2, `adr.md` v0.2, `prompts.md` v0.2 |
| Working style | One step at a time; each step ends runnable, tested and committed |
| Toolchain | Python 3.12 with uv, FastAPI, Celery, PostgreSQL, Redis, MinIO, Qdrant, LangGraph, Next.js, VS Code |

**How to use this file.** Tick a box when a step meets its "Done when" line. The matching prompt for each step is in `prompts.md` (same step numbers). Update the status table at the bottom at the end of each working session.

---

## 1. Approach

1. **Contracts, then logic, then I/O.** Typed models and the decision engine come before anything that calls an LLM, a database or the network.
2. **Test first for pure logic** (decision rules, validators, fraud math).
3. **Stub before real.** All agents run against recorded LLM fixtures first; real models are switched on only after the pipeline works end to end, so graph bugs and prompt bugs are never debugged together.
4. **Vertical slices.** Every step produces something runnable and ends with one commit.
5. **Measure early.** The dataset and evaluation harness come before UI polish: decision correctness (25%), classification (20%) and extraction (20%) outweigh the UI (10%).
6. **Bonus last**, and only after Gate 4.

## 2. Effort estimates and assumptions

Estimates are focused working days for one engineer using an AI coding assistant, and are *[Assumption]*: they exclude waiting on decisions and API access. Treat them as relative sizes, not commitments.

| Phase | Steps | Estimate (days) |
| --- | --- | --- |
| 0. Foundations | 1 to 5 (done) | 3 to 4 (spent) |
| 0b. Dataset alignment | 5a, 5b, 5c | 2 to 3 |
| 1. Core pipeline | 6 to 12 | 7 to 9 |
| 2. Coverage, fraud, decision | 13 to 18 | 6 to 8 |
| 3. Evaluation and UI | 19 to 23 | 5 to 7 (Step 19 is now a review, the generators exist) |
| 4. Bonus | 24 to 29 | 4 to 6 (optional) |
| **Core total (phases 0 to 3, including 5a to 5c)** | 1 to 23 | **about 23 to 29 days** (steps 1 to 5 already spent) |

Plan for about 20 percent extra for prompt tuning after the first real evaluation run (Step 20).

## 3. Prerequisites (before Step 1)

- [x] VS Code with extensions: Python, Pylance, Ruff, Docker, ESLint
- [x] uv, Node 20+, Git, Docker Desktop installed
- [ ] Tesseract OCR installed locally (needed at Step 9)
- [ ] LLM API key for at least one provider (needed at Step 20; not before)
- [x] `prd`, `spec.md`, `adr.md`, `prompts.md` copied into `docs/` of the repo
- [ ] **Replace** `docs/spec.md`, `docs/adr.md`, `docs/prompts.md` and `docs/plan.md` with the v0.2 files (needed before Step 5a)
- [ ] Decisions on blocking open questions, or agreement to proceed on the defaults (see section 9)
- [ ] Dataset generator libraries as a separate uv group: `uv add --group data pillow numpy fpdf2` (needed at Step 5a)

## 4. Phase and step plan

Legend: **Size** S under 0.5 day, M about 1 day, L about 2 days. **Depends on** lists step numbers that must be done first.

### Phase 0: Foundations

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [x] | 1 | Project skeleton: uv project, folders, pytest, ruff, `.gitignore`, `.env.example`, README stub | S | none | `uv run pytest` and `uv run ruff check .` pass; first commit |
| [x] | 2 | `infra/docker-compose.yml` (Postgres, Redis, MinIO, Qdrant) and typed `Settings` | M | 1 | All four services healthy; settings tests pass |
| [x] | 3 | Core enums and Pydantic models, `GraphState` (naming conflicts with the PRD resolved in favor of `spec.md`) | M | 1 | Round-trip and bounds tests pass; JSON schemas print |
| [x] | 4 | Decision engine, test first | M | 3 | 100% coverage on `packages/decision`; every precedence case tested |
| [x] | 5 | SQLAlchemy models, Alembic migration, repositories, seed script | L | 2, 3 | Migration applies on a fresh DB; audit table rejects UPDATE and DELETE; seed is idempotent |

**Phase 0b: dataset alignment (new in v0.2).** Your four generator scripts already exist. Run these three steps, in this order, before Step 6.

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [x] | 5a | Fix and instrument `generate_docs.py` (seeded, truth values saved, expected decisions), fix `generate_unknown.py`, regenerate once, freeze | M | none | Two runs give identical checksums; `truth.json` covers every document; `expected_decision` on every entry |
| [x] | 5b | Retrofit Steps 3 to 5 to spec v0.2: new settings, model fields and enums, decision-engine variants (D1, D2), second Alembic migration (`received_at`, `claim_history` columns, `policy_exclusions`) | M | 3, 4, 5 | Old tests still pass; new tests pass; migration applies on a fresh DB and on the existing one |
| [x] | 5c | Integrate the dataset: `LabelRecord`, `labels.jsonl`, `split.json`, seed members and claim history from the patient clusters | M | 5a, 5b | Counts match (31, 30, 30, 30, 30, 4); split deterministic with no cluster in both sets; seed idempotent |

**Gate 0 (passed 2026-11-01):** blocking open questions answered or defaults accepted (PRD section 13; D1 and D2 are confirmed). Dataset frozen and committed. Tests green, repo clean.

### Phase 1: Core pipeline

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [ ] | 6 | Ingestion API: upload, list, get, MinIO storage, SHA-256 duplicate detection | L | 2, 5 | curl upload creates an object in MinIO and a row in Postgres |
| [ ] | 7 | LLM gateway with stub provider, retries, fallback, redaction, prompt loader | L | 3 | Tests pass with no API keys |
| [ ] | 8 | Classifier agent and document page renderer | M | 3, 7, 5c | Six types and low-confidence paths tested with stub |
| [ ] | 9 | OCR pre-processor (text layer, Tesseract, LLM fallback) | L | 3, 7 | Skewed sample corrected; fallback triggers; payload validates |
| [ ] | 10 | Claims agent, validators, claim standard JSON schema with required fields per document type | M | 3, 7, 9 | Validators at 95% or higher coverage; a missing required field gives `schema_valid=false` at normal confidence (so it can be rejected, not escalated) |
| [ ] | 11 | KYC agent (lookups incl. DOB plus fuzzy name, any name difference flagged, expiry and expiring-soon from `received_at`, tamper via LLM) | L | 5c, 7, 9 | Every flag tested alone and combined; works on the real dataset IDs |
| [ ] | 12 | LangGraph wiring (discharge summaries and prescriptions skip Policy, D1), node wrapper, Celery task, audit events | L | 4, 6, 8, 9, 10, 11 | Upload flows to a final status with audit and agent run rows (stubbed) |

**Gate 1:** a document uploaded through the API reaches a persisted status through the graph on stub data; failure paths route to review. Refactor and tag `v0.1-pipeline`.

### Phase 2: Coverage, fraud, decision

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [ ] | 13 | Policy ingestion: Docling, chunking, Qdrant, `POST /policies`; use the existing Gold and Silver PDFs; load their "Excluded CPT Code Ranges" table into `policy_exclusions` | L | 2, 5b, 6 | Both policies `READY`; manual query returns relevant chunks; exclusion rows loaded |
| [ ] | 14 | Policy agent: step 0 deterministic CPT exclusion lookup, then hybrid retrieval, rerank, grounded answer, citation check | L | 10, 13 | Covered, uncovered, exclusion-table hit (confidence 0.95) and no-clause cases tested |
| [ ] | 15 | Fraud agent: ten detectors (adds identity mismatch, near-threshold, date conflict, readmission), noisy-OR scoring, 4 dp rounding, risk levels | M | 5c, 10, 11 | Boundary tests at 0.30 and 0.60; property test passes; each dataset fraud scenario fires its detector |
| [ ] | 16 | Orchestrator node, justification text, full graph wiring | M | 4, 12, 14, 15 | Six scenario graph tests produce the expected decisions |
| [ ] | 17 | Audit, review queue, override, reclassify, rerun endpoints | M | 16 | Override keeps the original decision; tests pass |
| [ ] | 18 | JWT auth, RBAC, rate limiting, PHI log redaction | M | 17 | Role matrix test passes (401 and 403 cases) |

**Gate 2:** every decision branch covered by tests (AC-04); policy upload retrievable at runtime without redeploy (AC-05); full pipeline produces a decision with rule trace.

### Phase 3: Evaluation and UI

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [ ] | 19 | Dataset review and gap-filling (the generators exist from 5a): scenario coverage matrix against the spec, add missing scenarios such as a prompt-injection document and an unrelated or blank page, confirm the split. **Also add a second cluster, assigned to holdout, for each single-cluster scenario** (amount under 10k, date conflict, duplicate claim, name mismatch, code mismatch, readmission), because the holdout set currently has none of them | S | 5c | Coverage matrix has no empty row; every scenario has at least one holdout cluster; additions are deterministic; split unchanged for existing clusters |
| [ ] | 20 | Evaluation harness (runner sets `received_at`, original before duplicate), baseline run with a real model, tuning loop on dev, final numbers on holdout | L | 16, 19 | Report with all metrics, per-scenario and per-category breakdown, dev and holdout columns, sample sizes; gate script works |
| [ ] | 21 | Next.js: login, dashboard, case detail with document viewer | L | 17, 18 | Log in, list cases, open a case with agent outputs |
| [ ] | 22 | Review queue, override dialog, audit tab, policies page | L | 21 | AC-06 and AC-07 pass by hand and in Playwright |
| [ ] | 23 | README, architecture diagram, CI workflow, end-to-end walkthrough | M | 20, 22 | A fresh clone reaches a decided case by following the README |

**Gate 3 (pass threshold, AC-03):** overall weighted score at least 70% and decision correctness at least 60%; all acceptance criteria AC-01 to AC-09 checked (section 6). Tag `v1.0`.

### Phase 4: Bonus (start only after Gate 3)

| Done | Step | Deliverable | Size | Depends on | Done when |
| --- | --- | --- | --- | --- | --- |
| [ ] | 24 | WebSocket live agent status with polling fallback | M | 22 | Events arrive in order; unauthorized socket rejected |
| [ ] | 25 | ELA tamper detection in KYC | M | 11, 19 | False-positive rate reported on dataset |
| [ ] | 26 | Calibration plot and ECE in the evaluation report | S | 20 | Report includes 5-bin diagram with bin counts |
| [ ] | 27 | PDF case report endpoint and UI button | M | 22 | PDF contains case ID, outputs, decision, audit |
| [ ] | 28 | LangSmith tracing with PHI redaction, off by default | S | 12 | Disabled by default; redaction tested |
| [ ] | 29 | Spanish and Hindi OCR with fixtures | M | 9, 19 | Completeness reported per language |

## 5. Dependency overview

```
1 -> 2 -> 6 -> 13 -> 14
1 -> 3 -> 4 ------------------------------> 16 -> 17 -> 18 -> 21 -> 22 -> 23
     3 -> 7 -> 8, 9 -> 10 -> 14, 15
     2,3 -> 5 -> 5b (retrofit) -> 5c (dataset integration, needs 5a) -> 8, 11, 15, 19
     5 -> 11, 15 (via 5c)
6, 8, 9, 10, 11 (+4) -> 12 -> 16
16 + 19 -> 20 -> 23
```

Critical path: 1, 3, 7, 9, 10, 12, 14, 16, 20, 23 (5a to 5c sit before Step 6 and are short). Steps 4, 5, 8, 11, 13, 15 and 19 can be reordered or run alongside, but doing them one at a time is simpler.

## 6. Acceptance criteria tracking (from the PRD)

| ID | Criterion | Verified at step | Status |
| --- | --- | --- | --- |
| AC-01 | Upload returns a `case_id` and reaches DECIDED or NEEDS_REVIEW unaided | 12, 16 | [ ] |
| AC-02 | Evaluation script reports classification, extraction and decision metrics | 20 | [ ] |
| AC-03 | Decision correctness at least 60%; overall at least 70% | 20 | [ ] |
| AC-04 | Unit tests cover every decision branch and precedence case | 4, 16 | [ ] |
| AC-05 | Runtime policy upload retrievable without redeploy, on 2 policies | 13, 14 | [ ] |
| AC-06 | Reviewer overrides an escalated case; audit log shows it, original preserved | 17, 22 | [ ] |
| AC-07 | Every case shows per-agent outputs and a timestamped audit trail | 21, 22 | [ ] |
| AC-08 | No credentials in the repo; configuration documented | 2, 18, 23 | [ ] |
| AC-09 | README walks through one end-to-end case | 23 | [ ] |

Score weights to protect: Decision correctness 25%, Classification 20%, Extraction 20%, Policy retrieval 15%, UI 10%, Code quality 10%.

## 7. Working rhythm for each step

1. Open a new branch `step-NN-short-name`.
2. Paste the step prompt from `prompts.md`; review the plan the assistant proposes; reply OK or adjust.
3. Let it code. Run `uv run pytest` and `uv run ruff check .` (plus the web tests where relevant).
4. Run the pre-commit review prompt (spec deviations, missing tests, secrets or PHI in logs).
5. Commit with message `step NN: <title>`; merge to `main`; tick the box in section 4.
6. Update the status table in section 10 and note any new open question.

**Steps 1 to 5 are complete.** Their prompts stay in `prompts.md` marked done, for reference only; do not re-run them.

**Session start routine:** "Read CLAUDE.md, docs/spec.md, docs/adr.md and plan.md; tell me which step is next and what it needs."

## 8. Risks to the plan

| Risk | Effect | Response |
| --- | --- | --- |
| Real-model accuracy below target at Step 20 | Rework of prompts and preprocessing | Budget 20% extra time; use the per-scenario breakdown; change one thing at a time and rerun |
| Docling or Tesseract install problems on your machine | Delay at Steps 9 and 13 | Spike the installs during Phase 0; document working versions in the README |
| LLM rate limits or cost during evaluation | Slow or costly runs | Run on a 30-document set; cache by input hash; use the stub for everything except evaluation |
| Spec defaults rejected by Operations (OQ-06, OQ-15, OQ-17) | Changes to Steps 4, 12, 16 | Decision engine and routing are table-driven and unit tested; confirm before Gate 1 |
| Scope creep from bonus items | Core delayed | No bonus step starts before Gate 3 |
| Regenerating the dataset by accident | Image bytes change, so stub fixtures keyed by input hash stop matching | Freeze after 5a; commit images; the generators are not run again without a plan entry |
| Generator fonts are Windows-only | Different pixels on another OS | Generate once on the current machine and commit the output |
| Retrofit (5b) breaks Steps 3 to 5 | Regressions in finished work | Add a second migration instead of editing the first; keep old tests; run the full suite before and after |
| Amendments escalate by default (D2) | About 28% of labels are ESCALATE, inflating decision accuracy | Report accuracy per document category as well as overall |
| Small test set gives noisy metrics | Wrong tuning decisions | Report sample sizes; expand the dataset beyond 30 when tuning |
| Assistant changes unrelated files | Hidden regressions | One step per branch; review diffs; the "stop and revert" prompt in `prompts.md` |

## 9. Decisions to make early

Blocking items from the PRD (section 13), with the default this plan assumes:

| ID | Question | Default assumed | Needed by |
| --- | --- | --- | --- |
| OQ-02 | Which model and fallback | Anthropic primary, OpenAI fallback, via gateway | Step 7 (confirm current model IDs before Step 20) |
| OQ-04 | Claim submission standard | Authored `claim_submission_standard.v1.json` | Step 10 |
| OQ-05 | Routing matrix | Spec 6.2 table | Step 12 |
| OQ-06 | Rule precedence | R1 reliability, R2 fraud, R3 reject, R4 approve | Step 4 |
| OQ-08 | Member and claims data source | Seeded PostgreSQL mocks | Step 5 |
| OQ-15 | Policy amendment decisions | Always escalate unless KYC fails | Step 4 and 16 |
| OQ-17 | Policy depends on Claims | Policy runs after Claims | Step 12 |
| OQ-03, OQ-11 | Compliance, auto-reject policy | Synthetic data only; decisions are recommendations | Before any real data |
| D1 (confirmed) | Do discharge summaries and prescriptions get a coverage decision? | Decided: no, supporting documents (extraction, member match and fraud only) | Step 5b (engine tests), Step 12 (routing) |
| D2 (confirmed) | Policy amendments | Decided: always escalate unless KYC fails; report accuracy per category | Step 5c (labels), Step 20 |
| Clock (new) | Date for expiry and recency checks | `cases.received_at`; evaluation sets it from each label's `reference_date` (the dataset is dated 2025) | Step 5b, Step 11 |

**D1 and D2 are both confirmed (2026-10-31).** To reverse either later, change the matching rows in spec 6.2 and 7.8 and the expected-decision table in spec section 11 before running Step 5c.

## 10. Progress log

| Date | Step(s) completed | Notes, deviations, new questions |
| --- | --- | --- |
| 2026-10-30 | Planning (PRD, spec, ADRs, prompts, plan) | Ready to start Step 1 |
| 2026-10-31 | Steps 1 to 5 (Phase 0) | Done by you with Copilot. Step 3: spec naming won over PRD (`agent_version`, `SKIPPED`, GraphState keys `document`, `ocr`, `audit`) |
| 2026-11-01 | Steps 5a, 5b, 5c; Gate 0 passed | Dataset fixed (readmission dates, secondary ICD truth, deterministic PDFs) and frozen. Phase 0 code aligned with spec v0.2 (`medishield_test` database, second migration). 155 labels, 94 APPROVE / 43 ESCALATE / 18 REJECT; split 21 dev and 9 holdout clusters. Six single-cluster fraud scenarios are dev-only |
| 2026-11-01 | Spec v0.2.1 | `NPI_CHECKSUM` moved to `ClaimsResult.warnings` (not a KYC flag); `claim_history.kind` is TEXT plus CHECK; `policy_exclusions` lookup rule stated |
| 2026-10-31 | D1 and D2 confirmed | D1: no coverage decision for discharge summaries and prescriptions. D2: policy amendments always escalate unless KYC fails. All docs updated |
| 2026-10-31 | Docs updated to v0.2 | Dataset review found 15 mismatches; added Steps 5a to 5c; decisions D1, D2 and the clock rule added |
| | | |

## 11. Definition of done

**Per step:** code and tests committed; `uv run pytest` and `uv run ruff check .` pass; no secrets or real PHI; the step's "Done when" line is true; spec deviations either fixed or recorded in the ADR log.

**For v1 (Gate 3):** all of section 6 checked; evaluation report stored in `reports/`; README verified from a fresh clone; architecture diagram updated with the actual component and model names; `v1.0` tag created.

## 12. Next action

Phase 0 and Phase 0b (steps 1 to 5c) are done and Gate 0 has passed. Next: **Step 6 (ingestion API)**. Earlier next-step notes, kept for the record:

1. Replace the four docs in `docs/` with the v0.2 files.
2. Run **Step 5a** (fix the generator, regenerate once, freeze). Use the Step 5a prompt in `prompts.md`.
3. Then **Step 5b** (retrofit), then **Step 5c** (dataset integration), then Gate 0 and Step 6.
