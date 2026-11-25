"""Idempotently upload a small synthetic set through the running API."""

import json
import os
from pathlib import Path

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
PASSWORD = os.environ.get("SEED_TEST_USER_PASSWORD")
if not PASSWORD:
    raise SystemExit("SEED_TEST_USER_PASSWORD is required")

email = os.environ.get("SEED_TEST_USER_EMAIL", "reviewer@medishield.test")
client = httpx.Client(base_url=API_URL, timeout=30)
login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
login.raise_for_status()
client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

root = Path(__file__).resolve().parents[3]
labels = [
    json.loads(line)
    for line in (root / "data/synthetic/labels.jsonl").read_text(encoding="utf-8").splitlines()
    if line
]
selected = sorted(
    (label for label in labels if label["decision_expected"] == "ESCALATE"),
    key=lambda row: row["doc_id"],
)[:3]
for label in selected:
    path = root / "data/synthetic" / label["file"]
    with path.open("rb") as file:
        response = client.post("/api/v1/cases", files={"file": (path.name, file, "image/png")})
    if response.status_code not in (200, 202):
        raise SystemExit(f"Upload failed with HTTP {response.status_code}")
print(json.dumps({"seeded": len(selected), "case_ids": []}))
