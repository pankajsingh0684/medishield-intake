"""Deterministic fixture keys and JSON fixture persistence."""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from packages.core.llm.protocol import FixtureNotFoundError

_PROMPT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def fixture_key(
    prompt_name: str, messages: Sequence[dict[str, str]], images: Sequence[bytes]
) -> str:
    if not _PROMPT_NAME.fullmatch(prompt_name):
        raise ValueError("Prompt names may contain only letters, numbers, underscores, and hyphens")
    canonical_input = {
        "messages": list(messages),
        "images": [hashlib.sha256(image).hexdigest() for image in images],
    }
    encoded = json.dumps(
        canonical_input,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{prompt_name}.{digest}"


class FixtureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def read(self, key: str) -> Any:
        path = self.path_for(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FixtureNotFoundError(f"Missing LLM fixture: {key}") from error
        except json.JSONDecodeError as error:
            raise FixtureNotFoundError(f"Invalid JSON in LLM fixture: {key}") from error

    def write(self, key: str, value: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".fixture-", dir=self.root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as fixture_file:
                fixture_file.write(payload)
            Path(temporary_name).replace(self.path_for(key))
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
