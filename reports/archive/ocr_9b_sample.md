# OCR 9b Sample (dev split only)

Generated: 2026-11-03T17:56:54+00:00
Tesseract: 5.5.3.20260724 | OCR code version: 1.1.0

This report runs PDF text-layer extraction and OpenCV/Tesseract only. The vision fallback is disabled and guarded by a gateway that raises if called. The synthetic dataset is read-only.

Documents: 20 | Total processing time: 195.94 s

## Category Summary

| Category | Documents | Mean OCR confidence | Would trigger fallback |
|---|---:|---:|---:|
| claim form | 4 | 0.880 | 4/4 (100.0%) |
| ID | 4 | 0.808 | 4/4 (100.0%) |
| discharge summary | 4 | 0.847 | 4/4 (100.0%) |
| prescription | 4 | 0.828 | 4/4 (100.0%) |
| amendment | 4 | 0.793 | 4/4 (100.0%) |
| unknown | 0 | 0.000 | 0/0 (0.0%) |

Mean confidence is the text-layer payload confidence for Tier 1 and the word-weighted Tesseract confidence for Tier 2. Fallback share applies the current OCR trigger: mean confidence below 0.70 or no extracted key field.

## Exact-Match Rates

Rates use only documents in that category whose truth record contains the field. Null truth values are compared as expected absence. Code lists are compared as ordered, de-duplicated uppercase lists; dates and amounts are normalized before exact comparison.

| Category | Truth field | Exact | Wrong | Missing | Applicable | Rate |
|---|---|---:|---:|---:|---:|---:|
| claim form | `claim_amount` | 1 | 0 | 3 | 4 | 25.0% |
| claim form | `cpt_codes` | 1 | 3 | 0 | 4 | 25.0% |
| claim form | `icd10_codes` | 2 | 1 | 1 | 4 | 50.0% |
| claim form | `provider_npi` | 4 | 0 | 0 | 4 | 100.0% |
| claim form | `service_date` | 0 | 0 | 4 | 4 | 0.0% |
| ID | `printed_name` | 0 | 3 | 1 | 4 | 0.0% |
| ID | `printed_expiry_date` | 2 | 0 | 2 | 4 | 50.0% |
| discharge summary | `cpt_codes` | 2 | 1 | 1 | 4 | 50.0% |
| discharge summary | `icd10_codes` | 1 | 3 | 0 | 4 | 25.0% |
| discharge summary | `admit_date` | 1 | 0 | 3 | 4 | 25.0% |
| discharge summary | `discharge_date` | 1 | 0 | 3 | 4 | 25.0% |
| prescription | `rx_date` | 3 | 0 | 1 | 4 | 75.0% |

## Dropped Values

Extracted values that failed their validator (or a code exclusion rule) and were dropped instead of reported. A dropped value cannot win the fallback merge.

| Field | Dropped |
|---|---:|
| `cpt_codes` | 0 |
| `icd10_codes` | 0 |
| `claim_amount` | 0 |
| `service_date` | 0 |
| `printed_expiry_date` | 0 |
| `dob` | 1 |
| `provider_npi` | 0 |
| `admit_date` | 2 |
| `discharge_date` | 3 |
| `rx_date` | 0 |
| `discharge before admit (pairs)` | 0 |

## Before and After (changed fields only)

Wrong = a non-empty value that differs from truth; missing = nothing extracted.

| Field | Exact | Wrong | Missing | Applicable |
|---|---:|---:|---:|---:|
| `claim_amount` | 1 -> 1 | 0 -> 0 | 3 -> 3 | 4 |
| `cpt_codes` | 2 -> 3 | 5 -> 4 | 1 -> 1 | 8 |
| `icd10_codes` | 2 -> 3 | 5 -> 4 | 1 -> 1 | 8 |
| `service_date` | 0 -> 0 | 0 -> 0 | 4 -> 4 | 4 |
| `printed_expiry_date` | 2 -> 2 | 0 -> 0 | 2 -> 2 | 4 |
| `admit_date` | 1 -> 1 | 2 -> 0 | 1 -> 3 | 4 |
| `discharge_date` | 1 -> 1 | 3 -> 0 | 0 -> 3 | 4 |
| `rx_date` | 3 -> 3 | 0 -> 0 | 1 -> 1 | 4 |
| **total wrong** | | 15 -> 8 | | |

## Ten Worst Documents

Ranked by number of wrong/missing truth fields, then error rate, then lower OCR confidence. A missing prediction is shown as `null`.

| doc_id | Category | Confidence | Wrong or missing fields |
|---|---|---:|---|
| `discharge_PT_69470` | discharge summary | 0.761 | `cpt_codes` expected ["71046", "47562", "90837", "99284"], got ["71046", "47562", "30837", "99284"]<br>`icd10_codes` expected ["F32.1", "J01.90"], got ["F32"]<br>`admit_date` expected "2025-09-09", got null<br>`discharge_date` expected "2025-09-14", got null |
| `discharge_PT_30028` | discharge summary | 0.928 | `cpt_codes` expected ["21120", "71250"], got []<br>`icd10_codes` expected ["K35.80", "I25.10"], got ["K35.80"]<br>`admit_date` expected "2025-12-10", got null<br>`discharge_date` expected "2025-12-14", got null |
| `claim_PT_71993` | claim form | 0.888 | `claim_amount` expected "6400.00", got null<br>`cpt_codes` expected ["17000", "93306"], got ["17000"]<br>`icd10_codes` expected ["K35.80", "M54.5"], got ["K35.80"]<br>`service_date` expected "2025-02-17", got null |
| `claim_PT_19116` | claim form | 0.909 | `claim_amount` expected "4095.00", got null<br>`cpt_codes` expected ["90837", "93000"], got ["90837", "00001"]<br>`icd10_codes` expected ["I25.10", "G43.909"], got []<br>`service_date` expected "2025-12-15", got null |
| `discharge_PT_74454` | discharge summary | 0.782 | `icd10_codes` expected ["J18.9", "I25.10"], got ["J18.9"]<br>`admit_date` expected "2025-08-16", got null<br>`discharge_date` expected "2025-08-18", got null |
| `claim_PT_50538` | claim form | 0.903 | `claim_amount` expected "65500.00", got null<br>`cpt_codes` expected ["27447", "71250", "47562"], got ["27447", "00016"]<br>`service_date` expected "2025-06-14", got null |
| `id_PT_39816` | ID | 0.865 | `printed_name` expected "NANCY MARTIN L.", got "NANCY MARTIN"<br>`printed_expiry_date` expected "2025-03-28", got null |
| `id_PT_54236` | ID | 0.905 | `printed_name` expected "Margaret Lee K.", got null<br>`printed_expiry_date` expected "2025-11-28", got null |
| `rx_PT_19116` | prescription | 0.702 | `rx_date` expected "2025-12-17", got null |
| `id_PT_20322` | ID | 0.537 | `printed_name` expected "SARAH WHITE Q.", got "SARAH WHITE" |

## Runtime Per Document

| doc_id | Category | Tier | Status | Seconds |
|---|---|---|---|---:|
| `claim_PT_19116` | claim form | Tesseract | LOW CONFIDENCE | 10.079 |
| `rx_PT_19116` | prescription | Tesseract | LOW CONFIDENCE | 4.362 |
| `rx_PT_62350` | prescription | Tesseract | LOW CONFIDENCE | 4.417 |
| `discharge_PT_69470` | discharge summary | Tesseract | LOW CONFIDENCE | 7.749 |
| `id_PT_20322` | ID | Tesseract | LOW CONFIDENCE | 2.891 |
| `claim_PT_71993` | claim form | Tesseract | LOW CONFIDENCE | 5.978 |
| `claim_PT_16658` | claim form | Tesseract | LOW CONFIDENCE | 22.390 |
| `discharge_PT_57795` | discharge summary | Tesseract | LOW CONFIDENCE | 7.800 |
| `amend_PT_57795` | amendment | Tesseract | OK | 20.301 |
| `rx_PT_15075` | prescription | Tesseract | LOW CONFIDENCE | 5.945 |
| `claim_PT_50538` | claim form | Tesseract | LOW CONFIDENCE | 18.356 |
| `id_PT_30028` | ID | Tesseract | LOW CONFIDENCE | 5.806 |
| `discharge_PT_30028` | discharge summary | Tesseract | LOW CONFIDENCE | 9.561 |
| `amend_PT_30028` | amendment | Tesseract | OK | 8.303 |
| `rx_PT_67125` | prescription | Tesseract | LOW CONFIDENCE | 3.890 |
| `amend_PT_67125` | amendment | Tesseract | OK | 19.724 |
| `id_PT_54236` | ID | Tesseract | LOW CONFIDENCE | 1.651 |
| `id_PT_39816` | ID | Tesseract | LOW CONFIDENCE | 1.250 |
| `amend_PT_39816` | amendment | Tesseract | LOW CONFIDENCE | 19.698 |
| `discharge_PT_74454` | discharge summary | Tesseract | LOW CONFIDENCE | 15.783 |

Total runtime: **195.940 seconds**
