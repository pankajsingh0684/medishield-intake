"""Classify one document file through the configured LLM gateway."""

import argparse
import mimetypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.agents.classifier.agent import ClassifierAgent
from packages.core.config import Settings
from packages.core.llm.gateway import build_gateway


def detect_mime_type(path: Path, content: bytes) -> str:
    guessed_type, _ = mimetypes.guess_type(path.name)
    if guessed_type in {"application/pdf", "image/tiff", "image/jpeg", "image/png"}:
        return guessed_type
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    raise ValueError(f"Could not determine a supported document type for {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify a document using the configured provider."
    )
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    content = args.path.read_bytes()
    mime_type = detect_mime_type(args.path, content)
    settings = Settings()
    gateway = build_gateway(settings)
    try:
        result = ClassifierAgent(gateway, settings).classify(content, mime_type)
    finally:
        gateway.close()
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
