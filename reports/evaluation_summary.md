# Evaluation Summary

All runs use the real providers (Groq: `openai/gpt-oss-120b` for text, `qwen/qwen3.8-27b` for vision) on the synthetic dataset (238 documents, 46 patient clusters). Dev split: 130 documents. Holdout split: 108 documents. Full per-run reports are in `reports/`.

## Results

| Run | Split | Documents | Decision correctness | Weighted score* | Notes |
| --- | --- | --- | --- | --- | --- |
| `20261126T043835Z-c93a941c` | dev (stratified) | 40 | 0.700 (28/40) | 0.873 | Before the policy, KYC and UNKNOWN fixes |
| `20261126T081311Z-3b6ad487` | dev (stratified) | 40 | 0.950 (38/40) | 0.969 | After those fixes |
| `20261126T092752Z-b969ac8e` | holdout (full) | 108 | **0.861 (93/108)** | 0.935 | **The independent holdout result**, run once |
| `20261126T121818Z-9f11f93d` | dev (stratified) | 40 | 0.950 (38/40) | 0.969 | Regression check after the generic fixes |
| `20261126T125002Z-f3788ff7` | holdout (full) | 108 | 0.898 (97/108) | 0.949 | **Post-fix re-run, not independent** (see below) |

\*Automated weighted score: classification 20%, extraction 20% and decision 25%, renormalised to 100%. Retrieval review is manual (a review sheet is written with each run) and UI and code quality are unscored.

**How to read the holdout numbers.** The first holdout run (0.861) was done once, after all tuning on dev. The fixes that followed (placeholder values, NPI normalisation, expiry check on ID documents only, DOB precedence, admit/discharge date checks, duplicate lookup, larger retry cap) were chosen after studying the failures of that run, so the second run (0.898) is not independent evidence. It shows the effect of the fixes, not expected performance on new data. Quote 0.861 as the unbiased figure.

## Post-fix holdout (108 documents)

- Classification accuracy 1.000 (108/108). Extraction completeness 0.963 (103/107). Latency p50 7.4 s, p95 35.6 s (mostly cached calls).
- Confusion matrix (expected -> actual): APPROVE 61 correct, 7 escalated; ESCALATE 27 correct, 3 approved; REJECT 9 correct, 1 escalated.
- By document category: policy amendments 21/21, prescriptions 21/21, discharge summaries 20/21, claim forms 20/22, ID documents 13/21.
- Calibration is poor (ECE 0.30): the agents' confidences are not calibrated, and many low-confidence answers (0.3) are in fact correct escalations.

### The 11 remaining misses

| Group | Count | Documents | Safety |
| --- | --- | --- | --- |
| ID documents where KYC fails at low confidence (vision model misread the date of birth or name) | 7 | five `id_extra_*` documents, `id_PT_99687`, `id_PT_47353` | Safe: a human reviews them |
| Approved when a human should have reviewed | 3 | `id_PT_62383` (tampered ID not detected), `claim_extra_PT_EX0042_dup` (duplicate not detected), `discharge_extra_PT_EX0046` (30-day readmission not detected) | **Not safe.** These are false approvals (2.8% of documents). |
| Policy coverage undetermined plus fraud score 0.35 | 1 | `claim_PT_99687` | Safe |

The duplicate and readmission detectors depend on prior-claim history. Seeded history exists only for scenario-specific cases, and both documents show a fraud score of 0.0, so these detectors did not fire in the evaluation. This is the main open issue.

## Dev (40-document stratified sample)

After the first round of fixes the sample reached 0.950 and stayed there after the generic fixes. Two documents remain wrong, both because the Policy agent could not verify a citation (confidence 0.3 and escalation): `claim_PT_20322` (expected APPROVE) and `claim_PT_55056` (expected REJECT for an invalid schema, but rule R1 escalates first). Dev results are optimistic, because the failures were studied and fixed on this split.

## Known divergence KD-1

`claim_PT_16658` is labelled REJECT, but its $9,950 total is in the near-threshold band, so rule R2 (fraud) escalates it before R3 can reject. The engine follows the specification, and the case is reported as an expected mismatch. It was not in the dev sample.

## Retrieval

A review sheet (`*_retrieval.csv`) is written for each run for manual scoring of retrieved policy clauses. This review was not scored for v1.0 (state the result here if you complete it).

## Cost and throughput

The whole evaluation (all runs above plus the earlier development runs) used about 1.24 million tokens in 24 hours on the Groq pay-as-you-go tier, roughly $1 to $2 in total, with no rate-limit errors after the move off the free tier. A cold run of the full holdout takes about 30 to 45 minutes. Responses are cached by input hash, so reruns are fast and cheap.
