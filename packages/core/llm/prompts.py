"""Load versioned Markdown prompts with validated YAML front matter."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from packages.core.config import Settings
from packages.core.llm.protocol import LLMGateway

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_REQUIRED_FIELDS = {"model", "temperature", "max_tokens", "schema"}
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class PromptDefinition:
    name: str
    version: str
    model: str
    temperature: float
    max_tokens: int
    schema: str
    system: str

    def resolve_model(self, settings: Settings) -> str:
        if self.model == "vision":
            return settings.llm_vision_model
        if self.model == "text":
            return settings.llm_text_model
        raise ValueError("Prompt model must be 'vision' or 'text'")

    def invoke(
        self,
        gateway: LLMGateway,
        settings: Settings,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes] | None,
        schema: type[ModelT],
    ) -> ModelT:
        return gateway.complete_json(
            self.resolve_model(settings),
            self.system,
            messages,
            images,
            schema,
            prompt_name=self.name,
            prompt_version=self.version,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )


class PromptLoader:
    def __init__(self, root: Path = Path("packages/agents/prompts")) -> None:
        self.root = root

    def load(self, name: str, version: str) -> PromptDefinition:
        if not _NAME.fullmatch(name) or not _NAME.fullmatch(version):
            raise ValueError(
                "Prompt name and version may contain only letters, numbers, '_' or '-'"
            )
        path = self.root / f"{name}.{version}.md"
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise FileNotFoundError(f"Prompt not found: {name}.{version}") from error
        metadata, body = self._parse_front_matter(source, path)
        missing = _REQUIRED_FIELDS.difference(metadata)
        if missing:
            raise ValueError(
                f"Prompt {name}.{version} is missing front matter: {', '.join(sorted(missing))}"
            )
        model = metadata["model"]
        temperature = metadata["temperature"]
        max_tokens = metadata["max_tokens"]
        schema = metadata["schema"]
        if model not in {"vision", "text"}:
            raise ValueError("Prompt front matter model must be 'vision' or 'text'")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise TypeError("Prompt temperature must be numeric")
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
            raise ValueError("Prompt max_tokens must be a positive integer")
        if not isinstance(schema, str) or not schema.strip():
            raise ValueError("Prompt schema must name a schema")
        if not body.strip():
            raise ValueError(f"Prompt body is empty: {name}.{version}")
        return PromptDefinition(
            name=name,
            version=version,
            model=model,
            temperature=float(temperature),
            max_tokens=max_tokens,
            schema=schema,
            system=body.strip(),
        )

    @staticmethod
    def _parse_front_matter(source: str, path: Path) -> tuple[dict[str, Any], str]:
        lines = source.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError(f"Prompt is missing YAML front matter: {path.name}")
        try:
            closing_index = next(
                index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
            )
        except StopIteration as error:
            raise ValueError(f"Prompt has unterminated YAML front matter: {path.name}") from error
        metadata = yaml.safe_load("\n".join(lines[1:closing_index]))
        if not isinstance(metadata, dict):
            raise TypeError(f"Prompt front matter must be a mapping: {path.name}")
        body = "\n".join(lines[closing_index + 1 :])
        return metadata, body
