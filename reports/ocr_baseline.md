# OCR Baseline

Generated: 2026-11-03T02:48:51+00:00
Tesseract: 5.5.3.20260724

This report runs PDF text-layer extraction and OpenCV/Tesseract only. The vision fallback is disabled and guarded by a gateway that raises if called. The synthetic dataset is read-only.

Documents: 155 | Total processing time: 1412.87 s

## Category Summary

| Category | Documents | Mean OCR confidence | Would trigger fallback |
|---|---:|---:|---:|
| claim form | 31 | 0.870 | 31/31 (100.0%) |
| ID | 30 | 0.848 | 25/30 (83.3%) |
| discharge summary | 30 | 0.825 | 30/30 (100.0%) |
| prescription | 30 | 0.786 | 30/30 (100.0%) |
| amendment | 30 | 0.803 | 30/30 (100.0%) |
| unknown | 4 | 0.512 | 4/4 (100.0%) |

Mean confidence is the text-layer payload confidence for Tier 1 and the word-weighted Tesseract confidence for Tier 2. Fallback share applies the current OCR trigger: mean confidence below 0.70 or no extracted key field.

## Exact-Match Rates

Rates use only documents in that category whose truth record contains the field. Null truth values are compared as expected absence. Code lists are compared as ordered, de-duplicated uppercase lists; dates and amounts are normalized before exact comparison.

| Category | Truth field | Exact | Applicable | Rate |
|---|---|---:|---:|---:|
| claim form | `claim_amount` | 12 | 31 | 38.7% |
| claim form | `cpt_codes` | 0 | 31 | 0.0% |
| claim form | `icd10_codes` | 14 | 31 | 45.2% |
| claim form | `provider_npi` | 31 | 31 | 100.0% |
| claim form | `service_date` | 0 | 31 | 0.0% |
| ID | `printed_name` | 0 | 30 | 0.0% |
| ID | `printed_expiry_date` | 12 | 30 | 40.0% |
| discharge summary | `cpt_codes` | 14 | 30 | 46.7% |
| discharge summary | `icd10_codes` | 5 | 30 | 16.7% |
| discharge summary | `admit_date` | 13 | 30 | 43.3% |
| discharge summary | `discharge_date` | 10 | 30 | 33.3% |
| prescription | `rx_date` | 22 | 30 | 73.3% |

## Ten Worst Documents

Ranked by number of wrong/missing truth fields, then error rate, then lower OCR confidence. A missing prediction is shown as `null`.

| doc_id | Category | Confidence | Wrong or missing fields |
|---|---|---:|---|
| `discharge_PT_45400` | discharge summary | 0.709 | `cpt_codes` expected ["21120", "29827"], got ["84756", "29827"]<br>`icd10_codes` expected ["F32.1", "G43.909"], got ["G43"]<br>`admit_date` expected "2025-02-14", got null<br>`discharge_date` expected "2025-02-19", got "92/14/2996" |
| `discharge_PT_17665` | discharge summary | 0.720 | `cpt_codes` expected ["29827", "90837", "47562"], got ["60657", "17665", "29827", "90837", "47562"]<br>`icd10_codes` expected ["K35.80", "M54.5"], got ["K35", "M54", "S18"]<br>`admit_date` expected "2025-05-26", got "95/26/2926"<br>`discharge_date` expected "2025-05-31", got "95/26/2926" |
| `discharge_PT_67125` | discharge summary | 0.753 | `cpt_codes` expected ["43239", "90837", "27447"], got ["72934", "43239", "P9002", "90837", "27447"]<br>`icd10_codes` expected ["K21.0", "K35.80"], got ["K21.0", "K35"]<br>`admit_date` expected "2025-01-12", got "91/12/2026"<br>`discharge_date` expected "2025-01-14", got "91/12/2026" |
| `discharge_PT_69470` | discharge summary | 0.761 | `cpt_codes` expected ["71046", "47562", "90837", "99284"], got ["81697", "72934", "71046", "47562", "30837", "99284"]<br>`icd10_codes` expected ["F32.1", "J01.90"], got ["F32"]<br>`admit_date` expected "2025-09-09", got "99/09/2925"<br>`discharge_date` expected "2025-09-14", got "99/09/2925" |
| `discharge_PT_41439` | discharge summary | 0.763 | `cpt_codes` expected ["27447", "99214", "71046", "44970"], got ["81897", "27447", "71046", "44979"]<br>`icd10_codes` expected ["K35.80", "J01.90"], got ["K35.80"]<br>`admit_date` expected "2025-05-28", got "2026-05-28"<br>`discharge_date` expected "2025-05-31", got "2026-05-28" |
| `discharge_PT_16658` | discharge summary | 0.771 | `cpt_codes` expected ["17000", "44970"], got ["60637", "17000", "44970"]<br>`icd10_codes` expected ["G43.909", "M75.100"], got ["G43", "M75"]<br>`admit_date` expected "2025-05-10", got null<br>`discharge_date` expected "2025-05-13", got "2096-05-13" |
| `discharge_PT_99687` | discharge summary | 0.838 | `cpt_codes` expected ["44970", "99215", "33533", "29827"], got ["60153", "44970", "99215", "33533", "29827"]<br>`icd10_codes` expected ["I25.10", "M75.100"], got ["M75"]<br>`admit_date` expected "2025-10-22", got null<br>`discharge_date` expected "2025-10-26", got "1989-05-25" |
| `discharge_PT_30028` | discharge summary | 0.928 | `cpt_codes` expected ["21120", "71250"], got []<br>`icd10_codes` expected ["K35.80", "I25.10"], got ["K35.80"]<br>`admit_date` expected "2025-12-10", got "42/10/2025"<br>`discharge_date` expected "2025-12-14", got "42/14/2025" |
| `claim_PT_30028` | claim form | 0.793 | `claim_amount` expected "8050.00", got "8.00"<br>`cpt_codes` expected ["21120", "71250"], got ["00020", "21120", "71250"]<br>`icd10_codes` expected ["K35.80"], got []<br>`service_date` expected "2025-12-10", got null |
| `claim_PT_39816` | claim form | 0.847 | `claim_amount` expected "132645.00", got null<br>`cpt_codes` expected ["33533", "72148", "27447", "93000"], got ["60453", "80236", "30057", "33533"]<br>`icd10_codes` expected ["K35.80", "J18.9"], got ["K35.80"]<br>`service_date` expected "2025-04-24", got null |

## Runtime Per Document

| doc_id | Category | Tier | Status | Seconds |
|---|---|---|---|---:|
| `id_PT_19116` | ID | Tesseract | LOW CONFIDENCE | 3.459 |
| `claim_PT_19116` | claim form | Tesseract | LOW CONFIDENCE | 9.784 |
| `discharge_PT_19116` | discharge summary | Tesseract | LOW CONFIDENCE | 16.638 |
| `rx_PT_19116` | prescription | Tesseract | LOW CONFIDENCE | 4.429 |
| `amend_PT_19116` | amendment | Tesseract | OK | 8.743 |
| `id_PT_99733` | ID | Tesseract | LOW CONFIDENCE | 1.563 |
| `claim_PT_99733` | claim form | Tesseract | LOW CONFIDENCE | 10.733 |
| `discharge_PT_99733` | discharge summary | Tesseract | LOW CONFIDENCE | 7.433 |
| `rx_PT_99733` | prescription | Tesseract | LOW CONFIDENCE | 4.364 |
| `amend_PT_99733` | amendment | Tesseract | OK | 6.991 |
| `id_PT_62350` | ID | Tesseract | LOW CONFIDENCE | 2.813 |
| `claim_PT_62350` | claim form | Tesseract | LOW CONFIDENCE | 9.348 |
| `discharge_PT_62350` | discharge summary | Tesseract | LOW CONFIDENCE | 7.713 |
| `rx_PT_62350` | prescription | Tesseract | LOW CONFIDENCE | 6.292 |
| `amend_PT_62350` | amendment | Tesseract | OK | 12.393 |
| `id_PT_69470` | ID | Tesseract | LOW CONFIDENCE | 1.986 |
| `claim_PT_69470` | claim form | Tesseract | LOW CONFIDENCE | 51.727 |
| `discharge_PT_69470` | discharge summary | Tesseract | LOW CONFIDENCE | 10.563 |
| `rx_PT_69470` | prescription | Tesseract | LOW CONFIDENCE | 15.630 |
| `amend_PT_69470` | amendment | Tesseract | OK | 16.979 |
| `id_PT_20322` | ID | Tesseract | LOW CONFIDENCE | 2.739 |
| `claim_PT_20322` | claim form | Tesseract | LOW CONFIDENCE | 22.508 |
| `claim_PT_20322_dup` | claim form | Tesseract | LOW CONFIDENCE | 22.978 |
| `discharge_PT_20322` | discharge summary | Tesseract | LOW CONFIDENCE | 6.425 |
| `rx_PT_20322` | prescription | Tesseract | LOW CONFIDENCE | 3.421 |
| `amend_PT_20322` | amendment | Tesseract | OK | 5.788 |
| `id_PT_39451` | ID | Tesseract | OK | 1.050 |
| `claim_PT_39451` | claim form | Tesseract | LOW CONFIDENCE | 10.541 |
| `discharge_PT_39451` | discharge summary | Tesseract | LOW CONFIDENCE | 7.081 |
| `rx_PT_39451` | prescription | Tesseract | LOW CONFIDENCE | 4.934 |
| `amend_PT_39451` | amendment | Tesseract | OK | 24.736 |
| `id_PT_71993` | ID | Tesseract | LOW CONFIDENCE | 2.774 |
| `claim_PT_71993` | claim form | Tesseract | LOW CONFIDENCE | 5.109 |
| `discharge_PT_71993` | discharge summary | Tesseract | LOW CONFIDENCE | 16.101 |
| `rx_PT_71993` | prescription | Tesseract | LOW CONFIDENCE | 4.302 |
| `amend_PT_71993` | amendment | Tesseract | OK | 7.573 |
| `id_PT_82132` | ID | Tesseract | LOW CONFIDENCE | 1.420 |
| `claim_PT_82132` | claim form | Tesseract | LOW CONFIDENCE | 14.453 |
| `discharge_PT_82132` | discharge summary | Tesseract | LOW CONFIDENCE | 9.923 |
| `rx_PT_82132` | prescription | Tesseract | LOW CONFIDENCE | 4.926 |
| `amend_PT_82132` | amendment | Tesseract | OK | 23.378 |
| `id_PT_17665` | ID | Tesseract | LOW CONFIDENCE | 1.684 |
| `claim_PT_17665` | claim form | Tesseract | LOW CONFIDENCE | 9.823 |
| `discharge_PT_17665` | discharge summary | Tesseract | LOW CONFIDENCE | 7.024 |
| `rx_PT_17665` | prescription | Tesseract | LOW CONFIDENCE | 8.955 |
| `amend_PT_17665` | amendment | Tesseract | OK | 17.587 |
| `id_PT_20745` | ID | Tesseract | LOW CONFIDENCE | 2.316 |
| `claim_PT_20745` | claim form | Tesseract | LOW CONFIDENCE | 5.044 |
| `discharge_PT_20745` | discharge summary | Tesseract | LOW CONFIDENCE | 6.488 |
| `rx_PT_20745` | prescription | Tesseract | LOW CONFIDENCE | 11.039 |
| `amend_PT_20745` | amendment | Tesseract | OK | 13.039 |
| `id_PT_47353` | ID | Tesseract | OK | 1.785 |
| `claim_PT_47353` | claim form | Tesseract | LOW CONFIDENCE | 14.808 |
| `discharge_PT_47353` | discharge summary | Tesseract | LOW CONFIDENCE | 8.297 |
| `rx_PT_47353` | prescription | Tesseract | LOW CONFIDENCE | 15.019 |
| `amend_PT_47353` | amendment | Tesseract | OK | 8.565 |
| `id_PT_16658` | ID | Tesseract | LOW CONFIDENCE | 1.836 |
| `claim_PT_16658` | claim form | Tesseract | LOW CONFIDENCE | 22.039 |
| `discharge_PT_16658` | discharge summary | Tesseract | LOW CONFIDENCE | 6.538 |
| `rx_PT_16658` | prescription | Tesseract | LOW CONFIDENCE | 3.752 |
| `amend_PT_16658` | amendment | Tesseract | OK | 6.142 |
| `id_PT_57795` | ID | Tesseract | OK | 1.081 |
| `claim_PT_57795` | claim form | Tesseract | LOW CONFIDENCE | 4.961 |
| `discharge_PT_57795` | discharge summary | Tesseract | LOW CONFIDENCE | 6.712 |
| `rx_PT_57795` | prescription | Tesseract | LOW CONFIDENCE | 3.986 |
| `amend_PT_57795` | amendment | Tesseract | OK | 18.311 |
| `id_PT_15075` | ID | Tesseract | LOW CONFIDENCE | 1.673 |
| `claim_PT_15075` | claim form | Tesseract | LOW CONFIDENCE | 13.397 |
| `discharge_PT_15075` | discharge summary | Tesseract | LOW CONFIDENCE | 6.895 |
| `rx_PT_15075` | prescription | Tesseract | LOW CONFIDENCE | 3.887 |
| `amend_PT_15075` | amendment | Tesseract | OK | 9.173 |
| `id_PT_24208` | ID | Tesseract | LOW CONFIDENCE | 2.090 |
| `claim_PT_24208` | claim form | Tesseract | LOW CONFIDENCE | 10.687 |
| `discharge_PT_24208` | discharge summary | Tesseract | LOW CONFIDENCE | 7.200 |
| `rx_PT_24208` | prescription | Tesseract | LOW CONFIDENCE | 3.912 |
| `amend_PT_24208` | amendment | Tesseract | OK | 23.723 |
| `id_PT_50538` | ID | Tesseract | LOW CONFIDENCE | 1.140 |
| `claim_PT_50538` | claim form | Tesseract | LOW CONFIDENCE | 10.374 |
| `discharge_PT_50538` | discharge summary | Tesseract | LOW CONFIDENCE | 7.423 |
| `rx_PT_50538` | prescription | Tesseract | LOW CONFIDENCE | 8.303 |
| `amend_PT_50538` | amendment | Tesseract | OK | 21.959 |
| `id_PT_72021` | ID | Tesseract | LOW CONFIDENCE | 1.529 |
| `claim_PT_72021` | claim form | Tesseract | LOW CONFIDENCE | 22.575 |
| `discharge_PT_72021` | discharge summary | Tesseract | LOW CONFIDENCE | 16.134 |
| `rx_PT_72021` | prescription | Tesseract | LOW CONFIDENCE | 8.432 |
| `amend_PT_72021` | amendment | Tesseract | OK | 18.422 |
| `id_PT_62383` | ID | Tesseract | LOW CONFIDENCE | 2.781 |
| `claim_PT_62383` | claim form | Tesseract | LOW CONFIDENCE | 10.977 |
| `discharge_PT_62383` | discharge summary | Tesseract | LOW CONFIDENCE | 6.927 |
| `rx_PT_62383` | prescription | Tesseract | LOW CONFIDENCE | 5.495 |
| `amend_PT_62383` | amendment | Tesseract | OK | 28.548 |
| `id_PT_81810` | ID | Tesseract | LOW CONFIDENCE | 1.942 |
| `claim_PT_81810` | claim form | Tesseract | LOW CONFIDENCE | 6.098 |
| `discharge_PT_81810` | discharge summary | Tesseract | LOW CONFIDENCE | 17.248 |
| `rx_PT_81810` | prescription | Tesseract | LOW CONFIDENCE | 8.808 |
| `amend_PT_81810` | amendment | Tesseract | OK | 5.604 |
| `id_PT_30028` | ID | Tesseract | LOW CONFIDENCE | 2.568 |
| `claim_PT_30028` | claim form | Tesseract | LOW CONFIDENCE | 20.872 |
| `discharge_PT_30028` | discharge summary | Tesseract | LOW CONFIDENCE | 6.402 |
| `rx_PT_30028` | prescription | Tesseract | LOW CONFIDENCE | 3.381 |
| `amend_PT_30028` | amendment | Tesseract | OK | 7.023 |
| `id_PT_67125` | ID | Tesseract | OK | 1.669 |
| `claim_PT_67125` | claim form | Tesseract | LOW CONFIDENCE | 10.340 |
| `discharge_PT_67125` | discharge summary | Tesseract | LOW CONFIDENCE | 7.810 |
| `rx_PT_67125` | prescription | Tesseract | LOW CONFIDENCE | 3.638 |
| `amend_PT_67125` | amendment | Tesseract | OK | 20.103 |
| `id_PT_54236` | ID | Tesseract | LOW CONFIDENCE | 1.587 |
| `claim_PT_54236` | claim form | Tesseract | LOW CONFIDENCE | 5.425 |
| `discharge_PT_54236` | discharge summary | Tesseract | LOW CONFIDENCE | 7.145 |
| `rx_PT_54236` | prescription | Tesseract | LOW CONFIDENCE | 4.598 |
| `amend_PT_54236` | amendment | Tesseract | OK | 22.136 |
| `id_PT_24993` | ID | Tesseract | LOW CONFIDENCE | 1.118 |
| `claim_PT_24993` | claim form | Tesseract | LOW CONFIDENCE | 22.111 |
| `discharge_PT_24993` | discharge summary | Tesseract | LOW CONFIDENCE | 6.545 |
| `rx_PT_24993` | prescription | Tesseract | LOW CONFIDENCE | 3.640 |
| `amend_PT_24993` | amendment | Tesseract | OK | 9.185 |
| `id_PT_99687` | ID | Tesseract | LOW CONFIDENCE | 2.656 |
| `claim_PT_99687` | claim form | Tesseract | LOW CONFIDENCE | 25.409 |
| `discharge_PT_99687` | discharge summary | Tesseract | LOW CONFIDENCE | 6.980 |
| `rx_PT_99687` | prescription | Tesseract | LOW CONFIDENCE | 3.677 |
| `amend_PT_99687` | amendment | Tesseract | OK | 7.434 |
| `id_PT_45400` | ID | Tesseract | LOW CONFIDENCE | 1.300 |
| `claim_PT_45400` | claim form | Tesseract | LOW CONFIDENCE | 4.823 |
| `discharge_PT_45400` | discharge summary | Tesseract | LOW CONFIDENCE | 6.774 |
| `rx_PT_45400` | prescription | Tesseract | LOW CONFIDENCE | 4.623 |
| `amend_PT_45400` | amendment | Tesseract | LOW CONFIDENCE | 17.559 |
| `id_PT_88139` | ID | Tesseract | LOW CONFIDENCE | 2.751 |
| `claim_PT_88139` | claim form | Tesseract | LOW CONFIDENCE | 23.601 |
| `discharge_PT_88139` | discharge summary | Tesseract | LOW CONFIDENCE | 14.668 |
| `rx_PT_88139` | prescription | Tesseract | LOW CONFIDENCE | 5.571 |
| `amend_PT_88139` | amendment | Tesseract | OK | 6.426 |
| `id_PT_55056` | ID | Tesseract | LOW CONFIDENCE | 1.562 |
| `claim_PT_55056` | claim form | Tesseract | LOW CONFIDENCE | 10.349 |
| `discharge_PT_55056` | discharge summary | Tesseract | LOW CONFIDENCE | 7.154 |
| `rx_PT_55056` | prescription | Tesseract | LOW CONFIDENCE | 9.129 |
| `amend_PT_55056` | amendment | Tesseract | OK | 7.147 |
| `id_PT_39816` | ID | Tesseract | LOW CONFIDENCE | 1.202 |
| `claim_PT_39816` | claim form | Tesseract | LOW CONFIDENCE | 11.819 |
| `discharge_PT_39816` | discharge summary | Tesseract | LOW CONFIDENCE | 15.782 |
| `rx_PT_39816` | prescription | Tesseract | LOW CONFIDENCE | 9.591 |
| `amend_PT_39816` | amendment | Tesseract | LOW CONFIDENCE | 19.379 |
| `id_PT_74454` | ID | Tesseract | OK | 1.086 |
| `claim_PT_74454` | claim form | Tesseract | LOW CONFIDENCE | 10.179 |
| `discharge_PT_74454` | discharge summary | Tesseract | LOW CONFIDENCE | 14.719 |
| `rx_PT_74454` | prescription | Tesseract | LOW CONFIDENCE | 3.908 |
| `amend_PT_74454` | amendment | Tesseract | OK | 5.963 |
| `id_PT_41439` | ID | Tesseract | LOW CONFIDENCE | 2.447 |
| `claim_PT_41439` | claim form | Tesseract | LOW CONFIDENCE | 10.303 |
| `discharge_PT_41439` | discharge summary | Tesseract | LOW CONFIDENCE | 6.928 |
| `rx_PT_41439` | prescription | Tesseract | LOW CONFIDENCE | 9.631 |
| `amend_PT_41439` | amendment | Tesseract | OK | 25.058 |
| `unknown_blurry_scan_001` | unknown | Tesseract | LOW CONFIDENCE | 3.164 |
| `unknown_bank_statement_001` | unknown | Tesseract | OK | 4.443 |
| `unknown_utility_bill_001` | unknown | Tesseract | OK | 4.078 |
| `unknown_blank_scan_001` | unknown | Tesseract | NO TEXT | 4.305 |

Total runtime: **1412.867 seconds**
