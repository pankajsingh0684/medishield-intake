# Known Limitations

An honest list of what this system does not do, or does only partly, as of v1.0.

## Data and evaluation
- **Synthetic data only.** All 238 documents are generated and fictional. Results show how the system behaves on this dataset, not on real claims, and real documents (varied layouts, handwriting, poor scans) would score lower.
- **Sampled dev evaluation, full holdout.** Dev results come from a 40-document stratified sample of 130 documents, so they are optimistic and each scenario has only one or two documents. The holdout was run in full (108 documents). The unbiased holdout result is 0.861 decision correctness; a later run after fixes reached 0.898 but is not independent, because the fixes were chosen after studying its failures. See `reports/evaluation_summary.md`.
- **Three false approvals on holdout (2.8%).** A tampered ID, a duplicate claim and a 30-day readmission were approved when they should have gone to a human. Duplicate and readmission detection depend on prior-claim history, which is seeded only for scenario-specific cases, so these detectors did not fire for the extra patient cluster.
- **ID documents are the weakest category (13/21 on holdout).** The vision model sometimes misreads dates of birth or names, and KYC then fails at low confidence and escalates. This is the safe direction (a human reviews), but it adds reviewer work.
- **About one in five coverage lookups ends as "undetermined".** When the Policy agent cannot find a verifiable citation, the case escalates. This is safe but conservative.
- **One known label/engine divergence.** The dataset's `claim_PT_16658` is labelled REJECT, but its $9,950 total falls inside the near-threshold band, so rule R2 (fraud) escalates it first. The detector follows the specification, and the case is reported as an expected mismatch.

## Models
- **Preview vision model.** The vision step uses `qwen/qwen3.8-27b`, which the provider labels as a preview model that may change or be withdrawn. Open models can misread small print and detect tampering less reliably than frontier models.
- **Compact vision outputs.** OCR and extraction prompts were kept compact to fit the free tier's output limits. Very dense forms can still be truncated (one occurred in an earlier run and is now retried with a larger cap); splitting them across calls is a possible improvement.
- **Self-reported confidence is uncalibrated.** The Policy agent's confidence relies on the model's own certainty, which is not calibrated, and low values escalate to a human.
- **Government ID numbers are not member IDs.** The system looks members up by member ID, policy number, or date of birth plus a fuzzy name. It does not validate government ID numbers against any registry.

## Functional scope
- **Coverage decisions use procedure codes only.** Diagnosis codes (ICD-10) are not sent to the LLM, and diagnosis-based exclusions are out of scope for v1. Only CPT ranges are excluded deterministically.
- **Two sample policies.** The Policy agent works against two synthetic policies (Gold and Silver). Adding policies works through the ingestion endpoint, but it was tested only with these two.
- **Amendments always escalate** (by design), so amendment accuracy is a measure of routing, not of understanding the amendment.
- **Fraud history is seeded.** Duplicate, frequency and readmission checks use seeded prior-claim history, and there is no live claims system behind them.
- **Tamper detection is a vision-model judgement.** There is no forensic analysis such as error-level analysis in v1 (an optional extension).
- **Single language, single region.** Documents are English and US-style (CPT, ICD-10, NPI); other formats are not handled.

## Platform
- **Not production hardened.** There is no high-availability deployment, no secrets manager, no external identity provider, and local passwords for seeded users. Rate limiting is per process.
- **Polling, not live updates.** The UI refreshes by polling. WebSocket live updates were not built.
- **Document viewer is plain.** Images support zoom, and PDFs open in the browser's own viewer.
- **Local resource use.** Docling and the embedding model run locally and need a reasonably capable machine; first use downloads models.
- **PHI handling.** The log-redaction filter works on structured fields (for example `member_id=...`) and cannot catch a name written in free text. Real PHI must not be used without a data-processing agreement with the model provider.

## Possible next steps
- Evaluate on the full dev and holdout splits and on real, de-identified documents.
- Calibrate agent confidences against outcomes.
- Add a stronger vision model or a second provider as a fallback.
- Add diagnosis-based exclusions, live status updates and a production deployment setup.
