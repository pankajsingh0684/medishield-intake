# Policy Retrieval Calibration

Retrieval-only calibration; no LLM decisions or deterministic exclusion short-circuiting were applied.
Labels are `coverage_expected` on dev-split `CLAIM_FORM` rows in `labels.jsonl`.
Each claim score is the maximum top reranker score across its per-CPT and per-ICD-10 queries; query-level distributions are also shown.
The real `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker was loaded by this script only; scores are sigmoid-normalized to [0, 1].
Threshold counts are counts below the threshold, not recommended changes.

## Sample Confidence Trace

For `PT_19116` / CPT `90837`, deterministic stub reranker score = `0.428571`; its matching stub fixture certainty = `0.428571`. Confidence is their minimum, `0.428571` (displayed as `0.43`). The fixture certainty was generated from the deterministic reranker score, so the value originated in the stub reranker and was mirrored by the fixture; it is not a real cross-encoder or model judgment.

## Claim-Level Scores

Expected covered (19 claims): n=19, min=0.000482, median=0.001487, max=0.168192, <0.35=19, <0.60=19
Expected not covered (3 claims): n=3, min=0.021401, median=0.021401, max=0.042769, <0.35=3, <0.60=3

## Per-Code Query Scores

Queries from expected-covered claims: n=79, min=0.000037, median=0.000803, max=0.168192, <0.35=79, <0.60=79
Queries from expected-not-covered claims: n=10, min=0.000045, median=0.001042, max=0.042769, <0.35=10, <0.60=10

## Claims Below 0.35

- `claim_PT_15075` (claim top=0.001479; expected covered), CPT codes: 43239, 47562, 27447
- `claim_PT_17665` (claim top=0.001479; expected covered), CPT codes: 29827, 90837, 47562
- `claim_PT_19116` (claim top=0.001145; expected covered), CPT codes: 90837, 93000
- `claim_PT_20322` (claim top=0.001711; expected covered), CPT codes: 70553, 93000
- `claim_PT_20322_dup` (claim top=0.001711; expected covered), CPT codes: 70553, 93000
- `claim_PT_20745` (claim top=0.001487; expected covered), CPT codes: 36415, 71046
- `claim_PT_24993` (claim top=0.000482; expected covered), CPT codes: 27447, 85025
- `claim_PT_39451` (claim top=0.001479; expected covered), CPT codes: 36415, 47562, 43239
- `claim_PT_39816` (claim top=0.002280; expected covered), CPT codes: 33533, 72148, 27447, 93000
- `claim_PT_50538` (claim top=0.001487; expected covered), CPT codes: 27447, 71250, 47562
- `claim_PT_54236` (claim top=0.002280; expected covered), CPT codes: 80053, 99214, 99284
- `claim_PT_55056` (claim top=0.001013; expected covered), CPT codes: 29827, 27447, 93000
- `claim_PT_57795` (claim top=0.000994; expected covered), CPT codes: 70553, 33533
- `claim_PT_62350` (claim top=0.168192; expected covered), CPT codes: 59400, 27447
- `claim_PT_67125` (claim top=0.001097; expected covered), CPT codes: 43239, 90837, 27447
- `claim_PT_69470` (claim top=0.016961; expected covered), CPT codes: 71046, 47562, 90837, 99284, 99999
- `claim_PT_74454` (claim top=0.002280; expected covered), CPT codes: 99214, 99284
- `claim_PT_81810` (claim top=0.001487; expected covered), CPT codes: 90837, 27447, 71250, 99291
- `claim_PT_99733` (claim top=0.001160; expected covered), CPT codes: 80053, 90837, 27447, 99291
- `claim_PT_16658` (claim top=0.021401; expected not covered), CPT codes: 17000, 44970
- `claim_PT_30028` (claim top=0.042769; expected not covered), CPT codes: 21120, 71250
- `claim_PT_71993` (claim top=0.021401; expected not covered), CPT codes: 17000, 93306

## Per-Claim Detail

### Expected Covered
- `claim_PT_15075`: claim top=0.001479; CPT 43239=0.000180, CPT 47562=0.001479, CPT 27447=0.000482, ICD-10 G43.909=0.000045
- `claim_PT_17665`: claim top=0.001479; CPT 29827=0.000304, CPT 90837=0.000997, CPT 47562=0.001479, ICD-10 K35.80=0.000936
- `claim_PT_19116`: claim top=0.001145; CPT 90837=0.000997, CPT 93000=0.000093, ICD-10 I25.10=0.001145, ICD-10 G43.909=0.000045
- `claim_PT_20322`: claim top=0.001711; CPT 70553=0.000304, CPT 93000=0.000093, ICD-10 E11.9=0.001711
- `claim_PT_20322_dup`: claim top=0.001711; CPT 70553=0.000304, CPT 93000=0.000093, ICD-10 E11.9=0.001711
- `claim_PT_20745`: claim top=0.001487; CPT 36415=0.000114, CPT 71046=0.000072, ICD-10 F32.1=0.001487, ICD-10 S52.501A=0.001160
- `claim_PT_24993`: claim top=0.000482; CPT 27447=0.000482, CPT 85025=0.000048
- `claim_PT_39451`: claim top=0.001479; CPT 36415=0.000114, CPT 47562=0.001479, CPT 43239=0.000180, ICD-10 G43.909=0.000045
- `claim_PT_39816`: claim top=0.002280; CPT 33533=0.000994, CPT 72148=0.000121, CPT 27447=0.000482, CPT 93000=0.000093, ICD-10 K35.80=0.000936, ICD-10 J18.9=0.002280
- `claim_PT_50538`: claim top=0.001487; CPT 27447=0.000482, CPT 71250=0.000213, CPT 47562=0.001479, ICD-10 F32.1=0.001487, ICD-10 N39.0=0.000037
- `claim_PT_54236`: claim top=0.002280; CPT 80053=0.000143, CPT 99214=0.000803, CPT 99284=0.001745, ICD-10 M75.100=0.000943, ICD-10 J18.9=0.002280
- `claim_PT_55056`: claim top=0.001013; CPT 29827=0.000304, CPT 27447=0.000482, CPT 93000=0.000093, ICD-10 M54.5=0.001013
- `claim_PT_57795`: claim top=0.000994; CPT 70553=0.000304, CPT 33533=0.000994, ICD-10 N39.0=0.000037, ICD-10 K35.80=0.000936
- `claim_PT_62350`: claim top=0.168192; CPT 59400=0.168192, CPT 27447=0.000482, ICD-10 K35.80=0.000936
- `claim_PT_67125`: claim top=0.001097; CPT 43239=0.000180, CPT 90837=0.000997, CPT 27447=0.000482, ICD-10 K21.0=0.001097
- `claim_PT_69470`: claim top=0.016961; CPT 71046=0.000072, CPT 47562=0.001479, CPT 90837=0.000997, CPT 99284=0.001745, CPT 99999=0.016961, ICD-10 F32.1=0.001487
- `claim_PT_74454`: claim top=0.002280; CPT 99214=0.000803, CPT 99284=0.001745, ICD-10 J18.9=0.002280
- `claim_PT_81810`: claim top=0.001487; CPT 90837=0.000997, CPT 27447=0.000482, CPT 71250=0.000213, CPT 99291=0.000385, ICD-10 F32.1=0.001487, ICD-10 M75.100=0.000943
- `claim_PT_99733`: claim top=0.001160; CPT 80053=0.000143, CPT 90837=0.000997, CPT 27447=0.000482, CPT 99291=0.000385, ICD-10 S52.501A=0.001160
### Expected Not Covered
- `claim_PT_16658`: claim top=0.021401; CPT 17000=0.021401, CPT 44970=0.001804, ICD-10 G43.909=0.000045
- `claim_PT_30028`: claim top=0.042769; CPT 21120=0.042769, CPT 71250=0.000213, ICD-10 K35.80=0.000936
- `claim_PT_71993`: claim top=0.021401; CPT 17000=0.021401, CPT 93306=0.001071, ICD-10 K35.80=0.000936, ICD-10 M54.5=0.001013

## Round 2: Clause Recall and Query Templates

Experiment only; no source code, thresholds, prompt, or fixtures were changed. The cohort is all 22 dev-split Gold claims with boolean `coverage_expected` labels (19 covered, 3 not covered). For a covered claim, the representative decision code is its first CPT and its support clause is the Gold inclusion chunk on page 6, annotated to the service-category wording listed below. For a not-covered claim, the representative code is the first CPT matching an explicit policy exclusion and the support clause is the exact exclusion-table row in the page 8 chunk. Each query produced separate dense and sparse top-eight sets, RRF fusion, then reranking of the first eight fused candidates. `H8/rank` means whether the annotated clause appears in hybrid top eight and its one-based rerank position within those eight.

| Template | Median top rerank score | Recall@8 | Top-1 hit | Top-5 hit |
|---|---:|---:|---:|---:|
| (a) `coverage for CPT {code} {description}` | 0.000304 | 18/22 (81.8%) | 13/22 (59.1%) | 18/22 (81.8%) |
| (b) `{description} covered service` | 0.004064 | 22/22 (100%) | 10/22 (45.5%) | 22/22 (100%) |
| (c) `Is {description} a covered benefit under the policy?` | 0.002859 | 22/22 (100%) | 9/22 (40.9%) | 22/22 (100%) |

By label group: (a) covered recall@8 15/19, top-1 11/19, top-5 15/19; uncovered 3/3, 2/3, 3/3. (b) covered 19/19, 8/19, 19/19; uncovered 3/3, 2/3, 3/3. (c) covered 19/19, 9/19, 19/19; uncovered 3/3, 0/3, 3/3. Template (b) wins the median top score tie-break while matching (c)'s top-five hit rate.

| Dev claim | Expected | Target CPT and support phrase/range | (a) H8/rank | (b) H8/rank | (c) H8/rank | (b) Platt target |
|---|---|---|---:|---:|---:|---:|
| `claim_PT_15075` | Covered | 43239, Surgical services | Y/1 | Y/2 | Y/2 | 0.269512 |
| `claim_PT_16658` | Not covered | 17000, 17000-17999 row | Y/1 | Y/1 | Y/5 | 0.360280 |
| `claim_PT_17665` | Covered | 29827, Surgical services | Y/4 | Y/2 | Y/2 | 0.091880 |
| `claim_PT_19116` | Covered | 90837, Mental health and substance use | Y/1 | Y/1 | Y/1 | 0.486813 |
| `claim_PT_20322` | Covered | 70553, Diagnostic imaging | Y/1 | Y/2 | Y/1 | 0.468339 |
| `claim_PT_20322_dup` | Covered | 70553, Diagnostic imaging | Y/1 | Y/2 | Y/1 | 0.468339 |
| `claim_PT_20745` | Covered | 36415, Diagnostic services | N/— | Y/1 | Y/2 | 0.267525 |
| `claim_PT_24993` | Covered | 27447, Surgical services | N/— | Y/2 | Y/2 | 0.164488 |
| `claim_PT_30028` | Not covered | 21120, 21120-21299 row | Y/2 | Y/2 | Y/5 | 0.058137 |
| `claim_PT_39451` | Covered | 36415, Diagnostic services | N/— | Y/1 | Y/2 | 0.267525 |
| `claim_PT_39816` | Covered | 33533, Surgical services | Y/3 | Y/3 | Y/3 | 0.133961 |
| `claim_PT_50538` | Covered | 27447, Surgical services | N/— | Y/2 | Y/2 | 0.164488 |
| `claim_PT_54236` | Covered | 80053, Diagnostic services | Y/1 | Y/1 | Y/1 | 0.492487 |
| `claim_PT_55056` | Covered | 29827, Surgical services | Y/4 | Y/2 | Y/2 | 0.091880 |
| `claim_PT_57795` | Covered | 70553, Diagnostic imaging | Y/1 | Y/2 | Y/1 | 0.468339 |
| `claim_PT_62350` | Covered | 59400, Maternity care | Y/2 | Y/2 | Y/3 | 0.683995 |
| `claim_PT_67125` | Covered | 43239, Surgical services | Y/1 | Y/2 | Y/2 | 0.269512 |
| `claim_PT_69470` | Covered | 71046, Diagnostic imaging | Y/1 | Y/1 | Y/1 | 0.218972 |
| `claim_PT_71993` | Not covered | 17000, 17000-17999 row | Y/1 | Y/1 | Y/5 | 0.360280 |
| `claim_PT_74454` | Covered | 99214, Outpatient physician visits | Y/1 | Y/1 | Y/1 | 0.457489 |
| `claim_PT_81810` | Covered | 90837, Mental health and substance use | Y/1 | Y/1 | Y/1 | 0.486813 |
| `claim_PT_99733` | Covered | 80053, Diagnostic services | Y/1 | Y/1 | Y/1 | 0.492487 |

### Best-Template Scores and Calibration

For template (b), the annotated relevant-target sigmoid-score distribution (directly scored even if retrieval missed it) is `n=22, min=0.000021, median=0.001071, max=0.019737`. The 154 non-target chunks among the hybrid top-eight candidate sets have `n=154, min=0.000010, median=0.000012, max=0.549685`. The latter includes a high-scoring irrelevant candidate, so the raw scores overlap and do not cleanly separate relevant from irrelevant evidence.

Dev-only monotonic Platt proposal: `p = sigmoid(0.516808 * raw_logit + 2.790506)`. Fit used the 22 annotated target pairs as positives and 154 non-target top-eight candidates as negatives (176 pairs total); it is in-sample and not applied. Calibrated relevant target values (claim order above) are shown in the last table column: distribution `min=0.058137, median=0.314896, max=0.683995`. Calibrated non-target distribution is `min=0.041527, median=0.044378, max=0.947527`; the overlap and high irrelevant outlier mean this fit is not a clean separator and requires more labeled data before use.

### Top-Eight Misses and Causes

Under current template (a), the relevant inclusion chunk is absent for `claim_PT_20745` (36415, Diagnostic services), `claim_PT_24993` (27447, Surgical services), `claim_PT_39451` (36415, Diagnostic services), and `claim_PT_50538` (27447, Surgical services). It is the same intact, broad inclusion chunk on page 6, not a split/missing chunk; the text names service categories rather than CPT codes, so code-bearing phrasing does not align well with its wording. Description-plus-“covered service” and the natural question retrieve it for all four. No annotated clause is absent under templates (b) or (c). The uncovered support is a code-only table: exact CPT wording helps template (a), while description/question variants still recall its row but can rank it as low as fifth.
