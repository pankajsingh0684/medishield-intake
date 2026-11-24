"""Atomic on-disk response cache for evaluation runs."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def response_cache_key(input_hash: str, prompt_name: str, prompt_version: str) -> str:
    payload = json.dumps(
        {"input_hash": input_hash, "prompt_name": prompt_name, "prompt_version": prompt_version},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EvaluationResponseCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def key_for(
        self,
        system: str,
        messages: Sequence[Mapping[str, str]],
        images: Sequence[bytes],
        prompt_name: str,
        prompt_version: str | None,
        provider: str = "unspecified",
        model: str = "unspecified",
    ) -> str:
        input_payload = {
            "system": system,
            "messages": list(messages),
            "images": [hashlib.sha256(image).hexdigest() for image in images],
        }
        input_hash = hashlib.sha256(
            json.dumps(input_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        provider_input_hash = hashlib.sha256(
            f"{input_hash}\0{provider}\0{model}".encode()
        ).hexdigest()
        return response_cache_key(provider_input_hash, prompt_name, prompt_version or "unspecified")

    def read(self, key: str) -> Any | None:
        try:
            return json.loads((self.root / f"{key}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def write(self, key: str, response: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".response-", dir=self.root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as cache_file:
                cache_file.write(payload)
            Path(temporary_name).replace(self.root / f"{key}.json")
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
