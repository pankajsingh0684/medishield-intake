"""On-disk cache of raw OCR output keyed by image hash and OCR code version."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from packages.agents.ocr.tesseract_wrapper import OcrWord

OcrPages = tuple[list[OcrWord], list[tuple[int, str]], int]


class OcrCache:
    def __init__(self, root: Path, version: str) -> None:
        self.root = root
        self.version = version

    def key(self, content: bytes) -> str:
        return hashlib.sha256(self.version.encode() + b"\0" + content).hexdigest()

    def _path(self, content: bytes) -> Path:
        return self.root / f"{self.key(content)}.json"

    def get(self, content: bytes) -> OcrPages | None:
        path = self._path(content)
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        words = [OcrWord(**word) for word in data["words"]]
        texts = [(int(page), text) for page, text in data["texts"]]
        return words, texts, int(data["page_count"])

    def put(self, content: bytes, pages: OcrPages) -> None:
        words, texts, page_count = pages
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "words": [asdict(word) for word in words],
            "texts": [[page, text] for page, text in texts],
            "page_count": page_count,
        }
        self._path(content).write_text(json.dumps(payload), encoding="utf-8")
