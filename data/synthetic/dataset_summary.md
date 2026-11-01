# MediShield Synthetic Dataset Summary

**Generated:** deterministic dataset seed 42
**Total documents:** 155  |  **Categories:** 6  |  **Case clusters:** 30  |  **Fraud clusters:** 6

---

## 1. Document Counts per Category

| Category             | Count |
|----------------------|-------|
| claim_forms          |    31 |
| id_documents         |    30 |
| discharge_summaries  |    30 |
| prescriptions        |    30 |
| policy_amendments    |    30 |
| unknown              |     4 |
| **TOTAL**            |   155 |

---

## 2. Case Cluster Map

Each cluster ID maps to one document per category linked to the same patient, 
policy number, and treatment episode.

- **C_001**: id_PT_19116, claim_PT_19116, discharge_PT_19116, rx_PT_19116, amend_PT_19116
- **C_002**: id_PT_99733, claim_PT_99733, discharge_PT_99733, rx_PT_99733, amend_PT_99733
- **C_003**: id_PT_62350, claim_PT_62350, discharge_PT_62350, rx_PT_62350, amend_PT_62350
- **C_004**: id_PT_69470, claim_PT_69470, discharge_PT_69470, rx_PT_69470, amend_PT_69470
- **C_005**: id_PT_20322, claim_PT_20322, claim_PT_20322_dup, discharge_PT_20322, rx_PT_20322, amend_PT_20322
- **C_006**: id_PT_39451, claim_PT_39451, discharge_PT_39451, rx_PT_39451, amend_PT_39451
- **C_007**: id_PT_71993, claim_PT_71993, discharge_PT_71993, rx_PT_71993, amend_PT_71993
- **C_008**: id_PT_82132, claim_PT_82132, discharge_PT_82132, rx_PT_82132, amend_PT_82132
- **C_009**: id_PT_17665, claim_PT_17665, discharge_PT_17665, rx_PT_17665, amend_PT_17665
- **C_010**: id_PT_20745, claim_PT_20745, discharge_PT_20745, rx_PT_20745, amend_PT_20745
- **C_011**: id_PT_47353, claim_PT_47353, discharge_PT_47353, rx_PT_47353, amend_PT_47353
- **C_012**: id_PT_16658, claim_PT_16658, discharge_PT_16658, rx_PT_16658, amend_PT_16658
- **C_013**: id_PT_57795, claim_PT_57795, discharge_PT_57795, rx_PT_57795, amend_PT_57795
- **C_014**: id_PT_15075, claim_PT_15075, discharge_PT_15075, rx_PT_15075, amend_PT_15075
- **C_015**: id_PT_24208, claim_PT_24208, discharge_PT_24208, rx_PT_24208, amend_PT_24208
- **C_016**: id_PT_50538, claim_PT_50538, discharge_PT_50538, rx_PT_50538, amend_PT_50538
- **C_017**: id_PT_72021, claim_PT_72021, discharge_PT_72021, rx_PT_72021, amend_PT_72021
- **C_018**: id_PT_62383, claim_PT_62383, discharge_PT_62383, rx_PT_62383, amend_PT_62383
- **C_019**: id_PT_81810, claim_PT_81810, discharge_PT_81810, rx_PT_81810, amend_PT_81810
- **C_020**: id_PT_30028, claim_PT_30028, discharge_PT_30028, rx_PT_30028, amend_PT_30028
- **C_021**: id_PT_67125, claim_PT_67125, discharge_PT_67125, rx_PT_67125, amend_PT_67125
- **C_022**: id_PT_54236, claim_PT_54236, discharge_PT_54236, rx_PT_54236, amend_PT_54236
- **C_023**: id_PT_24993, claim_PT_24993, discharge_PT_24993, rx_PT_24993, amend_PT_24993
- **C_024**: id_PT_99687, claim_PT_99687, discharge_PT_99687, rx_PT_99687, amend_PT_99687
- **C_025**: id_PT_45400, claim_PT_45400, discharge_PT_45400, rx_PT_45400, amend_PT_45400
- **C_026**: id_PT_88139, claim_PT_88139, discharge_PT_88139, rx_PT_88139, amend_PT_88139
- **C_027**: id_PT_55056, claim_PT_55056, discharge_PT_55056, rx_PT_55056, amend_PT_55056
- **C_028**: id_PT_39816, claim_PT_39816, discharge_PT_39816, rx_PT_39816, amend_PT_39816
- **C_029**: id_PT_74454, claim_PT_74454, discharge_PT_74454, rx_PT_74454, amend_PT_74454
- **C_030**: id_PT_41439, claim_PT_41439, discharge_PT_41439, rx_PT_41439, amend_PT_41439

---

## 3. Fraud-Positive Clusters

Six clusters contain deliberately injected fraud signals for pipeline testing.

| Cluster | Patient ID | Fraud Type | Signal Description |
|---------|------------|------------|-------------------|
| C_001 | PT_19116 | `readmission_30d` | Discharge summary shows a prior hospitalization ending fewer than 30 days before the current admission — trigger for readmission fraud review. |
| C_002 | PT_99733 | `date_conflict` | Prescription date is 45+ days after the claim/discharge date, creating a temporal impossibility. |
| C_003 | PT_62350 | `proc_diag_mismatch` | Maternity/obstetric CPT code (59400) billed against a non-maternity primary diagnosis (e.g., diabetes, hypertension). |
| C_004 | PT_69470 | `amount_under_10k` | Total billed amount set to $9,875.00 — just below the $10,000 automated review threshold (structuring behavior). |
| C_005 | PT_20322 | `duplicate_claim` | Two claim files submitted with the same claim number and identical service date, indicating a re-submitted or double-billed claim. |
| C_006 | PT_39451 | `name_mismatch` | See metadata. |

---

## 4. Edge Case Inventory

### 4.1 Expired ID Documents (5 clusters)

- **C_010** (PT_20745): ID expiry date set before treatment date.
- **C_011** (PT_47353): ID expiry date set before treatment date.
- **C_014** (PT_15075): ID expiry date set before treatment date.
- **C_028** (PT_39816): ID expiry date set before treatment date.
- **C_030** (PT_41439): ID expiry date set before treatment date.

### 4.2 Claims with Missing Mandatory Fields (4 clusters)

- **C_008** (PT_82132): Physician signature and rendering NPI omitted.
- **C_009** (PT_17665): Physician signature and rendering NPI omitted.
- **C_023** (PT_24993): Physician signature and rendering NPI omitted.
- **C_027** (PT_55056): Physician signature and rendering NPI omitted.

### 4.3 Uncovered Procedures (5 edge-case clusters, not fraud-labeled)

- **C_007** (PT_71993): CPT 17000 — Destruction, premalignant lesions – Aesthetic/Cosmetic (not covered under standard plan).
- **C_012** (PT_16658): CPT 17000 — Destruction, premalignant lesions – Aesthetic/Cosmetic (not covered under standard plan).
- **C_015** (PT_24208): CPT 21120 — Genioplasty – Cosmetic craniofacial surgery (not covered under standard plan).
- **C_020** (PT_30028): CPT 21120 — Genioplasty – Cosmetic craniofacial surgery (not covered under standard plan).
- **C_025** (PT_45400): CPT 21120 — Genioplasty – Cosmetic craniofacial surgery (not covered under standard plan).

### 4.4 Blurry / Low-Quality Scan Simulation (3 documents)

GaussianBlur applied at generation time; see `blur_simulated` flag in metadata.json.

---

## 5. Policy PDF Section Index (`policy/medishield_gold_plan.pdf`)

| Section | Page |
|---------|------|
| Cover Page | 1 |
| 1. Schedule of Benefits | 2 |
| 2. Definitions | 3 |
| 3. Inclusions and Exclusions | 4 |
|    3.1 Inclusions | 4 |
|    3.2 Exclusions | 4 |
| 4. Optional Riders | 5 |
| 5. Claims Procedure | 6 |
|    5.1 Cashless Workflow | 6 |
|    5.2 Reimbursement Workflow | 6 |
|    5.3 Document Checklist | 6 |
|    5.4 Grievance Contacts | 7 |
| 6. HIPAA Compliance | 8 |
| 7. Policyholder Attestation | 8 |

---

## 6. Metadata Schema (`dataset/metadata.json`)

```json
{
  "doc_id":          "claim_PT_12345",
  "category":        "claim_forms",
  "case_cluster_id": "C_001",
  "fraud_label":     true,
  "fraud_reason":    "duplicate_claim",
  "edge_flags":      [],
  "patient_id":      "PT_12345",
  "policy_number":   "MED-GLD-1234567",
  "blur_simulated":  false,
  "file_path":       "dataset/claim_forms/claim_PT_12345.png"
}
```
