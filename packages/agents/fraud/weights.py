"""Default noisy-OR weights for explainable fraud detectors."""

DETECTOR_WEIGHTS: dict[str, float] = {
    "DUPLICATE_CLAIM": 0.90,
    "FREQUENCY_SPIKE": 0.45,
    "PROVIDER_BILLING_OUTLIER": 0.40,
    "AMOUNT_OUTLIER": 0.35,
    "CODE_MISMATCH": 0.40,
    "TAMPER_SIGNAL": 0.40,
    "IDENTITY_MISMATCH": 0.50,
    "NEAR_THRESHOLD": 0.35,
    "DATE_CONFLICT": 0.45,
    "READMISSION_30D": 0.45,
}

if any(not 0.0 <= weight <= 1.0 for weight in DETECTOR_WEIGHTS.values()):
    raise ValueError("Fraud detector weights must be in [0, 1]")
