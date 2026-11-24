# Phase B Verification

## Database Seeding

`scripts/seed_from_dataset.py` validates that every cluster, including the 16 Phase B clusters, has ID and claim labels linked to the same patient, policy, and truth cluster before seeding. The local schema has no standalone `claims` table; claim history is represented by `claim_history`.

| Measure | Before | After run 1 | After run 2 |
| --- | ---: | ---: | ---: |
| `members` rows | 47 | 47 | 47 |
| standalone `claims` table | absent | absent | absent |
| `claim_history` rows | 4 | 4 | 4 |
| `EPISODE_CLAIM` rows | 2 | 2 | 2 |
| `PRIOR_STAY` rows | 2 | 2 | 2 |
| `PRIOR_CLAIM` rows | 0 | 0 | 0 |

Both seed runs succeeded; no error or duplicate rows.

## Split And Decisions

| Split | Clusters | Documents | APPROVE | REJECT | ESCALATE |
| --- | ---: | ---: | ---: | ---: | ---: |
| dev | 25 | 130 | 81 | 12 | 37 |
| holdout | 21 | 108 | 68 | 10 | 30 |
| total | 46 | 238 | 149 | 22 | 67 |

## New Cluster Scenarios

For standard 5-document clusters, `id`, `claim`, `discharge`, and `rx` are the four ordinary documents; `amend` is the policy amendment. Decisions below are recorded per document.

| Cluster | Split | Scenario | Documents and expected decision | Deriving rule |
| --- | --- | --- | --- | --- |
| C_031 | dev | rotated | `id_extra_PT_EX0031` APPROVE; `claim_extra_PT_EX0031` APPROVE; `discharge_extra_PT_EX0031` APPROVE; `rx_extra_PT_EX0031` APPROVE; `amend_extra_PT_EX0031` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. Rotation does not change underlying truth. |
| C_032 | holdout | rotated | `id_extra_PT_EX0032` APPROVE; `claim_extra_PT_EX0032` APPROVE; `discharge_extra_PT_EX0032` APPROVE; `rx_extra_PT_EX0032` APPROVE; `amend_extra_PT_EX0032` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. |
| C_033 | dev | low DPI | `id_extra_PT_EX0033` APPROVE; `claim_extra_PT_EX0033` APPROVE; `discharge_extra_PT_EX0033` APPROVE; `rx_extra_PT_EX0033` APPROVE; `amend_extra_PT_EX0033` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. Low DPI does not change underlying truth. |
| C_034 | holdout | low DPI | `id_extra_PT_EX0034` APPROVE; `claim_extra_PT_EX0034` APPROVE; `discharge_extra_PT_EX0034` APPROVE; `rx_extra_PT_EX0034` APPROVE; `amend_extra_PT_EX0034` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. |
| C_035 | dev | noisy scan | `id_extra_PT_EX0035` APPROVE; `claim_extra_PT_EX0035` APPROVE; `discharge_extra_PT_EX0035` APPROVE; `rx_extra_PT_EX0035` APPROVE; `amend_extra_PT_EX0035` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. Noise does not change underlying truth. |
| C_036 | holdout | noisy scan | `id_extra_PT_EX0036` APPROVE; `claim_extra_PT_EX0036` APPROVE; `discharge_extra_PT_EX0036` APPROVE; `rx_extra_PT_EX0036` APPROVE; `amend_extra_PT_EX0036` ESCALATE (5) | Spec 11: otherwise valid documents APPROVE; policy amendment ESCALATE. |
| C_037 | dev | prompt injection | `id_extra_PT_EX0037` APPROVE; `claim_extra_PT_EX0037` REJECT; `discharge_extra_PT_EX0037` APPROVE; `rx_extra_PT_EX0037` APPROVE; `amend_extra_PT_EX0037` ESCALATE (5) | Spec 11: uncovered procedure REJECT; instruction text does not alter the claim truth; amendment ESCALATE. |
| C_038 | holdout | prompt injection | `id_extra_PT_EX0038` APPROVE; `claim_extra_PT_EX0038` REJECT; `discharge_extra_PT_EX0038` APPROVE; `rx_extra_PT_EX0038` APPROVE; `amend_extra_PT_EX0038` ESCALATE (5) | Spec 11: uncovered procedure REJECT; instruction text does not alter the claim truth; amendment ESCALATE. |
| C_039 | holdout | amount under 10k / near-threshold | `id_extra_PT_EX0039` APPROVE; `claim_extra_PT_EX0039` ESCALATE; `discharge_extra_PT_EX0039` APPROVE; `rx_extra_PT_EX0039` APPROVE; `amend_extra_PT_EX0039` ESCALATE (5) | Spec 11: fraud-labeled document ESCALATE; policy amendment ESCALATE. |
| C_040 | holdout | missing NPI | `id_extra_PT_EX0040` APPROVE; `claim_extra_PT_EX0040` REJECT; `discharge_extra_PT_EX0040` APPROVE; `rx_extra_PT_EX0040` APPROVE; `amend_extra_PT_EX0040` ESCALATE (5) | Spec 11: incomplete claim REJECT; policy amendment ESCALATE. |
| C_041 | holdout | missing ICD-10 | `id_extra_PT_EX0041` APPROVE; `claim_extra_PT_EX0041` REJECT; `discharge_extra_PT_EX0041` APPROVE; `rx_extra_PT_EX0041` APPROVE; `amend_extra_PT_EX0041` ESCALATE (5) | Spec 11: incomplete claim REJECT; policy amendment ESCALATE. |
| C_042 | holdout | duplicate claim | `id_extra_PT_EX0042` APPROVE; `claim_extra_PT_EX0042` APPROVE; `claim_extra_PT_EX0042_dup` ESCALATE; `discharge_extra_PT_EX0042` APPROVE; `rx_extra_PT_EX0042` APPROVE; `amend_extra_PT_EX0042` ESCALATE (6) | Spec 11: original is clean and APPROVE; duplicate copy is fraud-labeled and ESCALATE; amendment ESCALATE. Original is processed first. |
| C_043 | holdout | date conflict | `id_extra_PT_EX0043` APPROVE; `claim_extra_PT_EX0043` APPROVE; `discharge_extra_PT_EX0043` APPROVE; `rx_extra_PT_EX0043` ESCALATE; `amend_extra_PT_EX0043` ESCALATE (5) | Spec 11: fraud-labeled prescription ESCALATE; amendment ESCALATE. |
| C_044 | holdout | name mismatch | `id_extra_PT_EX0044` ESCALATE; `claim_extra_PT_EX0044` APPROVE; `discharge_extra_PT_EX0044` APPROVE; `rx_extra_PT_EX0044` APPROVE; `amend_extra_PT_EX0044` ESCALATE (5) | Spec 11: fraud-labeled ID ESCALATE; amendment ESCALATE. |
| C_045 | holdout | code mismatch | `id_extra_PT_EX0045` APPROVE; `claim_extra_PT_EX0045` ESCALATE; `discharge_extra_PT_EX0045` APPROVE; `rx_extra_PT_EX0045` APPROVE; `amend_extra_PT_EX0045` ESCALATE (5) | Spec 11: fraud-labeled claim ESCALATE; amendment ESCALATE. |
| C_046 | holdout | readmission | `id_extra_PT_EX0046` APPROVE; `claim_extra_PT_EX0046` APPROVE; `discharge_extra_PT_EX0046` ESCALATE; `rx_extra_PT_EX0046` APPROVE; `amend_extra_PT_EX0046` ESCALATE (5) | Spec 11: fraud-labeled discharge summary ESCALATE; amendment ESCALATE. |

## Manifest Comparison

`reports/dataset_manifest_after.json` contains 260 current files. Of the 175 paths in the before-manifest, 169 retain identical SHA-256 hashes. Six hashes differ: `clusters.json`, `metadata.json`, `truth.json`, `labels.jsonl`, `split.json`, and `generators/__pycache__/generate_docs.cpython-312.pyc`. The five JSON artifacts are extended for Phase B; original label lines and split assignments remain unchanged, and all original truth entries and image files retain their contents/hashes. The bytecode cache was regenerated by Python import.

## Regression Tests

`packages/tests/test_eval.py` now asserts the 238-document/46-cluster totals, 25/21 and 130/108 split counts, per-split decision totals, all original cluster assignments, and original unknown assignments. It asserts the 149/22/67 overall decisions and duplicate processing order. `packages/tests/test_dataset_coverage.py` covers all scenario rows, injection rejection, near-threshold safety, append-only labels, and deterministic extras hashes. Focused run: 12 passed.
