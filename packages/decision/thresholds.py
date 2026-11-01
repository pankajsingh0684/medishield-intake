"""Immutable threshold configuration for deterministic decisions."""

from pydantic import BaseModel, ConfigDict, Field

from packages.core.config import Settings


class Thresholds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fraud_escalate: float = Field(ge=0.0, le=1.0)
    fraud_high: float = Field(ge=0.0, le=1.0)
    agent_confidence: float = Field(ge=0.0, le=1.0)
    classify_review: float = Field(ge=0.0, le=1.0)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(
            fraud_escalate=settings.threshold_fraud_escalate,
            fraud_high=settings.threshold_fraud_high,
            agent_confidence=settings.threshold_agent_confidence,
            classify_review=settings.threshold_classify_review,
        )
