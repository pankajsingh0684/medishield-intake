# Known Limitations

An honest list of what this system does not do, or does only partly, as of v1.0.

## Data and evaluation
- **Synthetic data only.** All 238 documents are generated and fictional. Results show how the system behaves on this dataset, not on real claims, and real documents (varied layouts, handwriting, poor scans) would score lower.
- **Sampled evaluation.** Because of model rate limits and time, the evaluation uses stratified samples of the dev and holdout splits and not every document. The report states each sample size. A few documents per scenario cannot show rare-case accuracy with confidence.
- **No tuning on holdout, but limited tuning iterations.** Fixes were made on dev, and holdout was run once. The numbers have wide uncertainty at these sample sizes.
- **One known label/engine divergence.** The dataset's `claim_PT_16658` is labelled REJECT, but its $9,950 total falls inside the near-threshold band, so rule R2 (fraud) escalates it first. The detector follows the specification, and the case is reported as an expected mismatch.

## Models
- **Preview vision model.** The vision step uses `qwen/qwen3.8-27b`, which the provider labels as a preview model that may change or be withdrawn. Open models can misread small print and detect tampering less reliably than frontier models.
- **Free-tier output cap.** On the free tier the vision model allows about 1,000 output tokens per minute, so OCR and extraction outputs are kept compact. Very dense forms might need to be split across calls.
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
