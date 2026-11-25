"""Remove one Playwright policy upload without touching canonical policy rows."""

import sys
from pathlib import Path
from uuid import UUID

from qdrant_client import models
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from packages.core.clients import create_qdrant_client
from packages.core.config import Settings
from packages.core.db.models import Policy, PolicyExclusion
from packages.core.db.session import create_database_engine
from packages.core.storage import S3Storage
from packages.rag.store import POLICY_COLLECTION, policy_payload_filter

policy_id = UUID(sys.argv[1])
settings = Settings()
engine = create_database_engine(settings.database_url)
storage = S3Storage(
    endpoint_url=settings.s3_endpoint,
    access_key=settings.s3_access_key.get_secret_value(),
    secret_key=settings.s3_secret_key.get_secret_value(),
    bucket=settings.s3_bucket,
)
qdrant = create_qdrant_client(settings)
try:
    with Session(engine) as session, session.begin():
        policy = session.get(Policy, policy_id)
        if policy is None or not (policy.version or "").startswith("e2e-"):
            raise SystemExit("Refusing to delete a non-E2E policy")
        object_key = policy.object_key
        session.query(PolicyExclusion).filter(PolicyExclusion.policy_id == policy_id).delete()
        session.delete(policy)
    qdrant.delete(
        collection_name=POLICY_COLLECTION,
        points_selector=models.FilterSelector(filter=policy_payload_filter(policy_id)),
        wait=True,
    )
    if object_key:
        storage._client.delete_object(Bucket=settings.s3_bucket, Key=object_key)
finally:
    qdrant.close()
    storage.close()
    engine.dispose()
