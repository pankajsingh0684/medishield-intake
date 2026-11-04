#!/usr/bin/env python
"""CLI for OCR processing of a single file."""

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from packages.agents.ocr.agent import OCRAgent, OCRError
from packages.core.config import Settings
from packages.core.llm.fixtures import FixtureStore
from packages.core.llm.gateway import Gateway, StubProvider


def main(argv: list[str] | None = None) -> int:
    """Process a supported document with OCR and print its normalized payload."""
    parser = argparse.ArgumentParser(description="Extract OCR fields from a document")
    parser.add_argument("file_path", type=Path)
    args = parser.parse_args(argv)
    file_path: Path = args.file_path
    if not file_path.is_file():
        parser.error(f"file not found: {file_path}")

    content = file_path.read_bytes()
    mime_type = detect_mime_type(content)
    if mime_type == "application/octet-stream":
        parser.error(f"unsupported file signature: {file_path}")

    try:
        settings = Settings()
        fixture_store = FixtureStore(Path("data/fixtures/llm"))
        gateway = Gateway(StubProvider(fixture_store))
        agent = OCRAgent(gateway, settings)
        result = agent.process(content, mime_type)
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0

    except OCRError as e:
        print(f"Error: OCR processing failed: {e}", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, RuntimeError) as e:
        print(f"Error: Unexpected error: {e}", file=sys.stderr)
        return 1


def detect_mime_type(content: bytes) -> str:
    """Detect supported document formats from their file signatures."""
    if content.startswith(b"%PDF"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")):
        return "image/tiff"
    return "application/octet-stream"


if __name__ == "__main__":
    sys.exit(main())
