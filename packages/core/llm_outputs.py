"""Base models for untrusted provider output payloads."""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)


def _warn_unknown_fields(model_name: str, values: Any, known_fields: set[str]) -> Any:
    if isinstance(values, dict):
        unknown = sorted(str(key) for key in values if key not in known_fields)
        if unknown:
            logger.warning(
                "Ignoring unknown LLM output fields schema=%s fields=%s",
                model_name,
                unknown,
            )
    return values


class LLMOutputModel(BaseModel):
    """Base for provider response models: ignore and safely report extra keys."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def warn_unknown_fields(cls, values: Any) -> Any:
        return _warn_unknown_fields(cls.__name__, values, set(cls.model_fields))


class LLMOutputBBox(LLMOutputModel):
    text: str
    page: int
    x: float
    y: float
    w: float
    h: float


class LLMOutputOcrField(LLMOutputModel):
    key: str
    value: str
    confidence: float
    page: int
