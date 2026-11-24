"""Schema-validating gateway, offline fixture provider, and settings factory."""

import hashlib
import json
import logging
import math
import random
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from packages.core.config import Settings
from packages.core.llm.fixtures import FixtureStore, fixture_key
from packages.core.llm.protocol import (
    FixtureNotFoundError,
    LLMError,
    LLMProvider,
    LLMSchemaError,
    ProviderResponse,
    RetryableLLMError,
)
from packages.core.llm.protocol import LLMProviderError as ProviderFailure
from packages.core.llm.providers import (
    AnthropicProvider,
    GroqDailyTokenBudget,
    GroqProvider,
    GroqRateLimitError,
    OpenAIProvider,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
logger = logging.getLogger(__name__)
DEFAULT_FIXTURE_DIR = Path("data/fixtures/llm")


class StubProvider:
    """Returns a response fixture for the canonical prompt and input key."""

    name = "stub"

    def __init__(self, fixtures: FixtureStore) -> None:
        self.fixtures = fixtures

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes],
        schema: type[BaseModel],
        temperature: float = 0,
        max_tokens: int = 4096,
        request_key: str | None = None,
        repair_hint: str | None = None,
    ) -> ProviderResponse:
        del model, system, messages, images, schema, temperature, max_tokens, repair_hint
        if request_key is None:
            raise ProviderFailure("Stub provider requires a deterministic fixture key")
        return ProviderResponse(self.fixtures.read(request_key))

    def close(self) -> None:
        return None


class Gateway:
    """Runs provider calls with schema validation, bounded retries, and safe logs."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_provider: LLMProvider | None = None,
        fallback_model: str | None = None,
        fixtures: FixtureStore | None = None,
        record_fixtures: bool = False,
        timeout: float = 90,
        max_provider_attempts: int = 2,
        retry_base_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
        response_cache: Any | None = None,
        cache_hits: int = 0,
        debug_raw: bool = False,
    ) -> None:
        self.provider = provider
        self.fallback_provider = fallback_provider
        self.fallback_model = fallback_model
        self.fixtures = fixtures
        self.record_fixtures = record_fixtures
        self.timeout = timeout
        self.max_provider_attempts = max_provider_attempts
        self.retry_base_seconds = retry_base_seconds
        self.sleeper = sleeper
        self.jitter = jitter or (lambda maximum: random.uniform(0, maximum))
        self.response_cache = response_cache
        self.cache_hits = cache_hits
        self.debug_raw = debug_raw
        self._usage_lock = threading.Lock()
        self._prompt_usage: dict[str, dict[str, Any]] = {}

    def complete_json(
        self,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes] | None,
        schema: type[ModelT],
        *,
        prompt_name: str = "default",
        prompt_version: str | None = None,
        temperature: float = 0,
        max_tokens: int = 4096,
    ) -> ModelT:
        started = time.monotonic()
        image_bytes = tuple(images or ())
        canonical_messages = [
            {"role": str(message.get("role", "user")), "content": str(message.get("content", ""))}
            for message in messages
        ]
        key = fixture_key(prompt_name, canonical_messages, image_bytes)
        cache_key = (
            self.response_cache.key_for(
                system,
                canonical_messages,
                image_bytes,
                prompt_name,
                prompt_version,
                self.provider.name,
                model,
            )
            if self.response_cache is not None
            else None
        )
        cached_content = (
            self.response_cache.read(cache_key)
            if self.response_cache is not None and cache_key is not None
            else None
        )
        if cached_content is not None:
            with self._usage_lock:
                self.cache_hits += 1
            status = "cached"
        else:
            status = "live"
        with self._usage_lock:
            entry = self._prompt_usage.setdefault(
                prompt_name,
                {
                    "live_calls": 0,
                    "cached_calls": 0,
                    "estimated_input_tokens": {"live": 0, "cached": 0},
                    "estimated_output_tokens": {"live": 0, "cached": 0},
                },
            )
            entry[f"{status}_calls"] += 1
            estimated_input = math.ceil(
                (
                    len(system)
                    + sum(len(str(message.get("content", ""))) for message in canonical_messages)
                )
                / 4
            ) + 2048 * len(image_bytes)
            entry["estimated_input_tokens"][status] += estimated_input
            entry["estimated_output_tokens"][status] += max_tokens
        repair_hint: str | None = None
        tokens: tuple[int | None, int | None] = (None, None)
        selected_provider = self.provider
        selected_model = model
        debug_diagnostics: list[str] = []
        try:
            if cached_content is not None:
                response = ProviderResponse(cached_content)
            else:
                response, selected_provider, selected_model = self._fetch_with_fallback(
                    model=model,
                    system=system,
                    messages=canonical_messages,
                    images=image_bytes,
                    schema=schema,
                    request_key=key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            if response.finish_reason == "length":
                original_response = response
                original_max_tokens = max_tokens
                if self.debug_raw:
                    diagnostic = self._raw_failure_diagnostic(
                        original_response,
                        f"truncated at max_tokens={original_max_tokens}",
                        selected_provider,
                        attempt=1,
                    )
                    debug_diagnostics.append(diagnostic)
                    logger.error("LLM_DEBUG_RAW %s", diagnostic)
                max_tokens = max(max_tokens * 2, max_tokens + 1000)
                response = self._call_with_retries(
                    selected_provider,
                    model=selected_model,
                    system=system,
                    messages=canonical_messages,
                    images=image_bytes,
                    schema=schema,
                    request_key=key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if response.finish_reason == "length":
                    if self.debug_raw:
                        diagnostic = self._raw_failure_diagnostic(
                            response,
                            f"truncated at max_tokens={max_tokens}",
                            selected_provider,
                            attempt=2,
                        )
                        debug_diagnostics.append(diagnostic)
                        logger.error("LLM_DEBUG_RAW %s", diagnostic)
                    raise LLMSchemaError(
                        "Provider response truncated (finish_reason=length) at both "
                        f"max_tokens={original_max_tokens} and max_tokens={max_tokens}"
                        + ("\n" + "\n".join(debug_diagnostics) if debug_diagnostics else "")
                    )
            for schema_attempt in range(2):
                try:
                    result = schema.model_validate(self._decode_content(response.content))
                except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
                    if self.debug_raw:
                        diagnostic = self._raw_failure_diagnostic(
                            response,
                            str(error),
                            selected_provider,
                            attempt=schema_attempt + 1,
                        )
                        debug_diagnostics.append(diagnostic)
                        logger.error("LLM_DEBUG_RAW %s", diagnostic)
                    if schema_attempt == 1:
                        raise LLMSchemaError(
                            f"Response did not match {schema.__name__} after one correction retry"
                            + ("\n" + "\n".join(debug_diagnostics) if debug_diagnostics else "")
                        ) from error
                    repair_hint = self._schema_repair_hint(schema)
                    response = self._call_with_retries(
                        selected_provider,
                        model=selected_model,
                        system=system,
                        messages=canonical_messages,
                        images=image_bytes,
                        schema=schema,
                        request_key=key,
                        repair_hint=repair_hint,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    continue
                tokens = (response.input_tokens, response.output_tokens)
                if self.record_fixtures and self.fixtures and selected_provider.name != "stub":
                    self.fixtures.write(key, result.model_dump(mode="json"))
                if self.response_cache is not None and cache_key is not None:
                    self.response_cache.write(cache_key, response.content)
                if "raw_response_ref" in schema.model_fields:
                    result = result.model_copy(
                        update={"raw_response_ref": self._response_reference(response.content)}
                    )
                return result
            raise LLMSchemaError(f"Response did not match {schema.__name__}")
        except FixtureNotFoundError:
            raise
        except LLMError as error:
            logger.warning(
                "LLM completion failed provider=%s model=%s prompt=%s prompt_version=%s error=%s",
                selected_provider.name,
                selected_model,
                prompt_name,
                prompt_version or "unspecified",
                type(error).__name__,
            )
            raise
        finally:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            logger.info(
                "LLM completion provider=%s model=%s prompt=%s prompt_version=%s "
                "input_tokens=%s output_tokens=%s latency_ms=%d",
                selected_provider.name,
                selected_model,
                prompt_name,
                prompt_version or "unspecified",
                tokens[0],
                tokens[1],
                elapsed_ms,
            )

    def _fetch_with_fallback(
        self,
        *,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes],
        schema: type[BaseModel],
        request_key: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[ProviderResponse, LLMProvider, str]:
        try:
            return (
                self._call_with_retries(
                    self.provider,
                    model=model,
                    system=system,
                    messages=messages,
                    images=images,
                    schema=schema,
                    request_key=request_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                self.provider,
                model,
            )
        except (RetryableLLMError, ProviderFailure):
            if self.fallback_provider is None:
                raise
            fallback_model = self.fallback_model or model
            try:
                response = self._call_with_retries(
                    self.fallback_provider,
                    model=fallback_model,
                    system=system,
                    messages=messages,
                    images=images,
                    schema=schema,
                    request_key=request_key,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except ProviderFailure as fallback_error:
                raise ProviderFailure("Primary and fallback providers failed") from fallback_error
            logger.warning(
                "LLM fallback used primary=%s fallback=%s model=%s",
                self.provider.name,
                self.fallback_provider.name,
                fallback_model,
            )
            return response, self.fallback_provider, fallback_model

    def _call_with_retries(
        self,
        provider: LLMProvider,
        *,
        model: str,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes],
        schema: type[BaseModel],
        request_key: str,
        temperature: float = 0,
        max_tokens: int = 4096,
        repair_hint: str | None = None,
    ) -> ProviderResponse:
        for attempt in range(self.max_provider_attempts):
            try:
                return provider.complete(
                    model=model,
                    system=system,
                    messages=messages,
                    images=images,
                    schema=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    request_key=request_key,
                    repair_hint=repair_hint,
                )
            except RetryableLLMError as error:
                if isinstance(error, GroqRateLimitError):
                    raise
                if attempt + 1 == self.max_provider_attempts:
                    raise
                delay_cap = self.retry_base_seconds * (2**attempt)
                self.sleeper(self.jitter(delay_cap))
        raise ProviderFailure("Provider request attempts exhausted")

    @staticmethod
    def _decode_content(content: Any) -> Any:
        if isinstance(content, str):
            cleaned = re.sub(
                r"<think\b[^>]*>.*?</think\s*>",
                "",
                content,
                flags=re.IGNORECASE | re.DOTALL,
            ).strip()
            fenced = re.fullmatch(
                r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.IGNORECASE | re.DOTALL
            )
            if fenced is not None:
                cleaned = fenced.group(1).strip()
            return json.loads(cleaned)
        if isinstance(content, (dict, list)):
            return content
        raise TypeError("Provider response must be JSON text or an object")

    @staticmethod
    def _raw_failure_diagnostic(
        response: ProviderResponse,
        validation_error: str,
        provider: LLMProvider,
        *,
        attempt: int,
    ) -> str:
        raw_reply = (
            response.content if isinstance(response.content, str) else json.dumps(response.content)
        )
        api_key = getattr(provider, "api_key", None)
        if api_key:
            raw_reply = raw_reply.replace(api_key, "[REDACTED]")
            validation_error = validation_error.replace(api_key, "[REDACTED]")
        diagnostic = (
            f"attempt={attempt} finish_reason={response.finish_reason!r} "
            f"usage={{'input_tokens': {response.input_tokens}, "
            f"'output_tokens': {response.output_tokens}}} "
            f"validation_error={validation_error} raw_reply_first_800={raw_reply[:800]!r}"
        )
        return diagnostic

    @staticmethod
    def _response_reference(content: Any) -> str:
        if isinstance(content, str):
            encoded = content.encode("utf-8")
        else:
            encoded = json.dumps(
                content,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @staticmethod
    def _schema_repair_hint(schema: type[BaseModel]) -> str:
        fields = ", ".join(sorted(schema.model_fields))
        return (
            "Your previous reply did not match the schema. Return ONLY the corrected JSON object, "
            f"with exactly these fields: {fields}. Do not return error messages."
        )

    def close(self) -> None:
        self.provider.close()
        if self.fallback_provider is not None and self.fallback_provider is not self.provider:
            self.fallback_provider.close()

    def usage_summary(self) -> dict[str, Any]:
        provider_summary = getattr(self.provider, "usage_summary", None)
        summary = provider_summary() if provider_summary is not None else {}
        with self._usage_lock:
            cache_hits = self.cache_hits
            prompt_usage = {
                name: {
                    "live": {
                        "calls": values["live_calls"],
                        "estimated_input_tokens": values["estimated_input_tokens"]["live"],
                        "estimated_output_tokens": values["estimated_output_tokens"]["live"],
                    },
                    "cached": {
                        "calls": values["cached_calls"],
                        "estimated_input_tokens": values["estimated_input_tokens"]["cached"],
                        "estimated_output_tokens": values["estimated_output_tokens"]["cached"],
                    },
                }
                for name, values in self._prompt_usage.items()
            }
        return {**summary, "cache_hits": cache_hits, "usage_by_prompt": prompt_usage}


def _provider(
    name: str,
    settings: Settings,
    timeout: float,
    *,
    sleeper: Callable[[float], None],
    daily_budget: GroqDailyTokenBudget | None,
) -> LLMProvider:
    if name == "stub":
        return StubProvider(FixtureStore(DEFAULT_FIXTURE_DIR))
    if name == "groq":
        if settings.groq_api_key is None:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return GroqProvider(
            api_key=settings.groq_api_key.get_secret_value(),
            timeout=timeout,
            rpm_limit=settings.groq_rpm_limit,
            tpm_limit=settings.groq_tpm_limit,
            daily_budget=daily_budget,
            sleeper=sleeper,
        )
    if name == "anthropic":
        if settings.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=timeout
        )
    if name == "openai":
        if settings.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIProvider(api_key=settings.openai_api_key.get_secret_value(), timeout=timeout)
    raise ValueError(f"Unsupported LLM provider: {name}")


def build_gateway(
    settings: Settings,
    *,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    sleeper: Callable[[float], None] = time.sleep,
    response_cache: Any | None = None,
    daily_budget: GroqDailyTokenBudget | None = None,
) -> Gateway:
    if settings.llm_record_fixtures and settings.llm_provider == "stub":
        raise ValueError("LLM_RECORD_FIXTURES requires a real LLM_PROVIDER")
    fixtures = FixtureStore(fixture_dir)
    primary = _provider(
        settings.llm_provider,
        settings,
        float(settings.agent_timeout_s),
        sleeper=sleeper,
        daily_budget=daily_budget,
    )
    fallback = (
        _provider(
            settings.llm_fallback_provider,
            settings,
            float(settings.agent_timeout_s),
            sleeper=sleeper,
            daily_budget=daily_budget,
        )
        if settings.llm_provider != "stub" and settings.llm_fallback_provider
        else None
    )
    if isinstance(primary, StubProvider):
        primary.fixtures = fixtures
    return Gateway(
        primary,
        fallback_provider=fallback,
        fallback_model=settings.llm_fallback_model if fallback else None,
        fixtures=fixtures,
        record_fixtures=settings.llm_record_fixtures,
        timeout=float(settings.agent_timeout_s),
        sleeper=sleeper,
        response_cache=response_cache,
        debug_raw=settings.llm_debug_raw,
    )
