# Fraud Agent Dev Check

Deterministic FraudAgent run on dev-split labels only. Scores are not tuned against this report.
Documents scored on fraud-routed types: 101; labeled fraud: 6; clean `valid_clean` claims: 16.

## Detector Results

| Detector | Fired on labeled fraud | Fired on clean |
|---|---:|---:|
| DUPLICATE_CLAIM | 1 | 0 |
| FREQUENCY_SPIKE | 0 | 0 |
| PROVIDER_BILLING_OUTLIER | 0 | 0 |
| AMOUNT_OUTLIER | 0 | 0 |
| CODE_MISMATCH | 1 | 0 |
| TAMPER_SIGNAL | 0 | 2 |
| IDENTITY_MISMATCH | 1 | 0 |
| NEAR_THRESHOLD | 1 | 1 |
| DATE_CONFLICT | 1 | 0 |
| READMISSION_30D | 1 | 0 |

## Clean Dev Claim Threshold Check

Passed: all 16 clean dev claims scored below 0.30.

Non-fraud edge scenarios are listed separately because their defined signals may fire by design:
- `claim_PT_16658` scenario=uncovered_procedure score=0.3500 detectors=NEAR_THRESHOLD

## Per-Document Results

- `id_PT_19116` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_19116` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_19116` expected=FLAGGED score=0.4500 risk=MEDIUM detectors=READMISSION_30D
- `rx_PT_19116` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_99733` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_99733` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_99733` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_99733` expected=FLAGGED score=0.4500 risk=MEDIUM detectors=DATE_CONFLICT
- `id_PT_62350` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_62350` expected=FLAGGED score=0.4000 risk=MEDIUM detectors=CODE_MISMATCH
- `discharge_PT_62350` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_62350` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_69470` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_69470` expected=FLAGGED score=0.3500 risk=MEDIUM detectors=NEAR_THRESHOLD
- `discharge_PT_69470` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_69470` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_20322` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_20322` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_20322_dup` expected=FLAGGED score=0.9000 risk=HIGH detectors=DUPLICATE_CLAIM
- `discharge_PT_20322` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_20322` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_39451` expected=FLAGGED score=0.5000 risk=MEDIUM detectors=IDENTITY_MISMATCH
- `claim_PT_39451` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_39451` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_39451` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_71993` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_71993` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_71993` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_71993` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_17665` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_17665` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_17665` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_17665` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_20745` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_20745` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_20745` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_20745` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_16658` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_16658` expected=LOW score=0.3500 risk=MEDIUM detectors=NEAR_THRESHOLD
- `discharge_PT_16658` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_16658` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_57795` expected=LOW score=0.4000 risk=MEDIUM detectors=TAMPER_SIGNAL
- `claim_PT_57795` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_57795` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_57795` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_15075` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_15075` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_15075` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_15075` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_50538` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_50538` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_50538` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_50538` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_81810` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_81810` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_81810` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_81810` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_30028` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_30028` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_30028` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_30028` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_67125` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_67125` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_67125` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_67125` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_54236` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_54236` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_54236` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_54236` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_24993` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_24993` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_24993` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_24993` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_55056` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_55056` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_55056` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_55056` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_39816` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_PT_39816` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_39816` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_39816` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_PT_74454` expected=LOW score=0.4000 risk=MEDIUM detectors=TAMPER_SIGNAL
- `claim_PT_74454` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_PT_74454` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_PT_74454` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_extra_PT_EX0031` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_extra_PT_EX0031` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_extra_PT_EX0031` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_extra_PT_EX0031` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_extra_PT_EX0033` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_extra_PT_EX0033` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_extra_PT_EX0033` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_extra_PT_EX0033` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_extra_PT_EX0035` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_extra_PT_EX0035` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_extra_PT_EX0035` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_extra_PT_EX0035` expected=LOW score=0.0000 risk=LOW detectors=none
- `id_extra_PT_EX0037` expected=LOW score=0.0000 risk=LOW detectors=none
- `claim_extra_PT_EX0037` expected=LOW score=0.0000 risk=LOW detectors=none
- `discharge_extra_PT_EX0037` expected=LOW score=0.0000 risk=LOW detectors=none
- `rx_extra_PT_EX0037` expected=LOW score=0.0000 risk=LOW detectors=none
