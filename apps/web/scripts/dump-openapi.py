"""Dump the FastAPI OpenAPI document without starting a server."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_PROVIDER", "stub")
os.environ.setdefault("LLM_FALLBACK_PROVIDER", "")
os.environ.setdefault("LLM_VISION_MODEL", "schema-vision")
os.environ.setdefault("LLM_TEXT_MODEL", "schema-text")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:5432/medishield")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("REDIS_PASSWORD", "schema-only")
os.environ.setdefault("S3_ENDPOINT", "http://127.0.0.1:9000")
os.environ.setdefault("S3_ACCESS_KEY", "schema-only")
os.environ.setdefault("S3_SECRET_KEY", "schema-only")
os.environ.setdefault("S3_BUCKET", "schema-only")
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6333")
os.environ.setdefault("QDRANT_API_KEY", "schema-only")
os.environ.setdefault("JWT_SECRET", "schema-only")
os.environ.setdefault("SEED_TEST_USER_PASSWORD", "schema-only")

from apps.api.main import app  # noqa: E402

output = Path(__file__).resolve().parents[1] / "lib" / "openapi.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
