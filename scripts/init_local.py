"""Idempotently initialize local databases, buckets, and the policy vector collection."""

from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from packages.core.clients import create_qdrant_client, create_redis_client
from packages.core.config import Settings
from packages.core.storage import S3Storage

TEST_DATABASE = "medishield_test"
TEST_BUCKET = "medishield-documents-test"
POLICY_COLLECTION = "policy_chunks"
EMBEDDING_DIMENSION = 384


def ensure_test_database(settings: Settings) -> None:
    database_url = make_url(settings.database_url)
    admin_engine = create_engine(
        database_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    database_identifier = admin_engine.dialect.identifier_preparer.quote(TEST_DATABASE)
    owner_identifier = admin_engine.dialect.identifier_preparer.quote(database_url.username)

    with admin_engine.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :database"),
            {"database": TEST_DATABASE},
        )
        if exists is None:
            connection.exec_driver_sql(
                f"CREATE DATABASE {database_identifier} OWNER {owner_identifier}"
            )
            print("Created medishield_test database.")
        else:
            print("medishield_test database already exists.")
    admin_engine.dispose()


def ensure_redis(settings: Settings) -> None:
    client = create_redis_client(settings)
    try:
        client.ping()
    finally:
        client.close()
    print("Redis authentication verified.")


def ensure_buckets(settings: Settings) -> None:
    for bucket in (settings.s3_bucket, TEST_BUCKET):
        storage = S3Storage(
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key.get_secret_value(),
            secret_key=settings.s3_secret_key.get_secret_value(),
            bucket=bucket,
        )
        try:
            storage.ensure_bucket()
        finally:
            storage.close()
        print(f"Bucket {bucket} is ready.")


def ensure_policy_collection(settings: Settings) -> None:
    client = create_qdrant_client(settings)
    try:
        if not client.collection_exists(POLICY_COLLECTION):
            client.create_collection(
                collection_name=POLICY_COLLECTION,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
                sparse_vectors_config={"text": SparseVectorParams()},
            )
            print("Created policy_chunks collection.")
        else:
            print("policy_chunks collection already exists.")
    finally:
        client.close()


def main() -> None:
    settings = Settings()
    ensure_test_database(settings)
    ensure_redis(settings)
    ensure_buckets(settings)
    ensure_policy_collection(settings)


if __name__ == "__main__":
    main()
