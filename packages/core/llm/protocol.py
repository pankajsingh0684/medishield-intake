"""Types and protocols shared by LLM providers and callers."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)
Message = Mapping[str, str]


@dataclass(frozen=True)
class ProviderResponse:
    content: Any
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: Sequence[Message],
        images: Sequence[bytes],
        schema: type[BaseModel],
        temperature: float = 0,
        max_tokens: int = 4096,
        request_key: str | None = None,
        repair_hint: str | None = None,
    ) -> ProviderResponse: ...

    def close(self) -> None: ...


class LLMGateway(Protocol):
    def complete_json(
        self,
        model: str,
        system: str,
        messages: Sequence[Message],
        images: Sequence[bytes] | None,
        schema: type[ModelT],
        *,
        prompt_name: str = "default",
        prompt_version: str | None = None,
        temperature: float = 0,
        max_tokens: int = 4096,
    ) -> ModelT: ...


class LLMError(RuntimeError):
    """Base class for safe, user-facing LLM gateway failures."""


class LLMProviderError(LLMError):
    """A provider request failed without exposing its response body."""


class RetryableLLMError(LLMProviderError):
    """A provider returned a transient status or transport failure."""


class FixtureNotFoundError(LLMError):
    """No offline fixture exists for the canonical request key."""


class LLMSchemaError(LLMError):
    """The provider response failed schema validation after one correction retry."""
