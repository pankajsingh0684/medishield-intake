"""Ingest the repository's Gold and Silver policy PDFs with the configured local model."""

import hashlib
import sys
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from packages.core.clients import create_qdrant_client
from packages.core.config import Settings
from packages.core.db.models import Policy
from packages.core.db.session import create_database_engine
from packages.core.storage import S3Storage
from packages.rag.embeddings import LocalSentenceTransformerEmbedder
from packages.rag.ingest import ingest_policy_document
from packages.rag.store import QdrantPolicyStore

ROOT = Path(__file__).resolve().parents[1]
POLICIES = (
    ("GOLD", "medishield_gold_plan.pdf"),
    ("SILVER", "medishield_silver_plan.pdf"),
)
VERSION = "synthetic-v1"
EFFECTIVE_FROM = date(2024, 1, 1)


def main() -> None:
    settings = Settings()
    engine = create_database_engine(settings.database_url)
    storage = S3Storage(
        endpoint_url=settings.s3_endpoint,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        bucket=settings.s3_bucket,
    )
    client = create_qdrant_client(settings)
    store = QdrantPolicyStore(client)
    embedder = LocalSentenceTransformerEmbedder(settings.embedding_model)
    try:
        for plan_code, filename in POLICIES:
            source = ROOT / "data" / "policies" / filename
            policy_id = uuid5(NAMESPACE_URL, f"medishield:plan:{plan_code}:{VERSION}")
            object_key = f"policies/{plan_code.casefold()}/{VERSION}/{filename}"
            content = source.read_bytes()
            storage.put(
                key=object_key,
                content=content,
                content_type="application/pdf",
                sha256=hashlib.sha256(content).hexdigest(),
            )
            with Session(engine) as session, session.begin():
                policy = session.get(Policy, policy_id)
                if policy is None:
                    policy = Policy(policy_id=policy_id)
                    session.add(policy)
                policy.plan_code = plan_code
                policy.name = f"MediShield {plan_code.title()} Plan"
                policy.version = VERSION
                policy.effective_from = EFFECTIVE_FROM
                policy.effective_to = None
                policy.object_key = object_key
                policy.ingest_status = "PENDING"
                policy.chunk_count = 0
                count = ingest_policy_document(session, policy_id, content, store, embedder)
            print(f"{plan_code}: READY with {count} chunks ({policy_id})")
    finally:
        client.close()
        storage.close()
        engine.dispose()


if __name__ == "__main__":
    main()
