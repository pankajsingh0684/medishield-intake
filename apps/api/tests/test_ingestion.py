import io
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import boto3
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from apps.api.factory import create_app
from apps.api.settings import ApiSettings
from packages.core.db.models import Case
from packages.core.enums import DecisionKind, DocType
from packages.core.storage import S3Storage, StorageUnavailable

ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = ROOT / "data" / "synthetic" / "dataset"


class IngestionTestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    database_url: str
    test_database_url: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_test_bucket: str = "medishield-documents-test"

    @model_validator(mode="after")
    def require_isolated_targets(self) -> "IngestionTestSettings":
        def target(url: str) -> tuple[str, str, int, str | None]:
            parsed = make_url(url)
            host = (parsed.host or "").casefold()
            if host in {"localhost", "127.0.0.1", "::1"}:
                host = "loopback"
            return (parsed.get_backend_name(), host, parsed.port or 5432, parsed.database)

        if target(self.database_url) == target(self.test_database_url):
            raise ValueError("API tests require TEST_DATABASE_URL separate from DATABASE_URL")
        if self.s3_test_bucket == self.s3_bucket:
            raise ValueError("API tests require S3_TEST_BUCKET separate from S3_BUCKET")
        return self


@pytest.fixture(scope="module")
def ingestion_settings() -> IngestionTestSettings:
    return IngestionTestSettings()


@pytest.fixture(scope="module")
def api_settings(ingestion_settings: IngestionTestSettings) -> ApiSettings:
    return ApiSettings(
        app_env="test",
        database_url=ingestion_settings.test_database_url,
        redis_url="redis://127.0.0.1:6380/0",
        redis_password="test-redis-password",
        s3_endpoint=ingestion_settings.s3_endpoint,
        s3_access_key=ingestion_settings.s3_access_key,
        s3_secret_key=ingestion_settings.s3_secret_key,
        s3_bucket=ingestion_settings.s3_test_bucket,
        qdrant_url="http://127.0.0.1:6333",
        qdrant_api_key="test-qdrant-key",
        jwt_secret="test-jwt-secret",
        seed_test_user_password="test-seed-password",
        max_upload_mb=10,
    )


@pytest.fixture(scope="module")
def test_storage(
    ingestion_settings: IngestionTestSettings,
) -> Iterator[S3Storage]:
    storage = S3Storage(
        endpoint_url=ingestion_settings.s3_endpoint,
        access_key=ingestion_settings.s3_access_key,
        secret_key=ingestion_settings.s3_secret_key,
        bucket=ingestion_settings.s3_test_bucket,
    )
    assert storage.bucket != ingestion_settings.s3_bucket
    storage.ensure_bucket()
    yield storage
    storage.close()


@pytest.fixture
def test_engine(ingestion_settings: IngestionTestSettings):
    engine = create_engine(ingestion_settings.test_database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", ingestion_settings.test_database_url.replace("%", "%%")
    )
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def client(
    api_settings: ApiSettings,
    test_engine,
    test_storage: S3Storage,
) -> Iterator[TestClient]:
    app = create_app(api_settings, engine=test_engine, storage=test_storage)
    with TestClient(app) as test_client:
        yield test_client


def post_file(client: TestClient, filename: str, content: bytes):
    return client.post(
        "/api/v1/cases",
        files={"file": (filename, content, "application/octet-stream")},
    )


def _dataset_category_samples() -> list[tuple[str, bytes]]:
    metadata = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    seen: set[str] = set()
    samples = []
    for row in metadata:
        if row["category"] not in seen:
            seen.add(row["category"])
            samples.append((row["category"], (DATASET_DIR / row["file_path"]).read_bytes()))
    return samples


def test_upload_accepts_dataset_images_and_stores_original_bytes(
    client: TestClient,
    ingestion_settings: IngestionTestSettings,
    test_engine,
    test_storage: S3Storage,
) -> None:
    category_samples = _dataset_category_samples()
    assert len(category_samples) == 6
    object_client = boto3.client(
        "s3",
        endpoint_url=ingestion_settings.s3_endpoint,
        aws_access_key_id=ingestion_settings.s3_access_key,
        aws_secret_access_key=ingestion_settings.s3_secret_key,
        region_name="us-east-1",
    )
    for category, content in category_samples:
        response = post_file(client, f"misleading-{category}.txt", content)
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "RECEIVED"
        assert data["duplicate_of"] is None
        case_id = UUID(data["case_id"])
        with Session(test_engine) as session:
            case = session.get(Case, case_id)
            assert case is not None
            object_response = object_client.get_object(
                Bucket=test_storage.bucket,
                Key=case.object_key,
            )
            assert object_response["Body"].read() == content


def test_upload_accepts_generated_pdf_and_tiff(client: TestClient) -> None:
    pdf_content = (
        b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF"
    )
    tiff_file = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(tiff_file, format="TIFF")
    tiff_content = tiff_file.getvalue()
    jpeg_file = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(jpeg_file, format="JPEG")
    jpeg_content = jpeg_file.getvalue()

    pdf_response = post_file(client, "scan.png", pdf_content)
    tiff_response = post_file(client, "scan.pdf", tiff_content)
    jpeg_response = post_file(client, "scan.tiff", jpeg_content)

    assert pdf_response.status_code == 202
    assert pdf_response.json()["mime_type"] == "application/pdf"
    assert tiff_response.status_code == 202
    assert tiff_response.json()["mime_type"] == "image/tiff"
    assert jpeg_response.status_code == 202
    assert jpeg_response.json()["mime_type"] == "image/jpeg"


def test_wrong_type_and_oversize_use_error_envelope(client: TestClient) -> None:
    wrong_type = post_file(client, "looks-like.png", b"not an image")
    too_large = post_file(
        client,
        "large.png",
        b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024),
    )

    assert wrong_type.status_code == 400
    assert wrong_type.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert wrong_type.json()["error"]["request_id"]
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_hash_duplicate_returns_existing_case_and_dup_scan_is_new(client: TestClient) -> None:
    metadata = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    original_row = next(row for row in metadata if row["doc_id"] == "claim_PT_20322")
    duplicate_row = next(row for row in metadata if row["doc_id"] == "claim_PT_20322_dup")
    original_content = (DATASET_DIR / original_row["file_path"]).read_bytes()
    duplicate_content = (DATASET_DIR / duplicate_row["file_path"]).read_bytes()

    first = post_file(client, "claim.jpg", original_content)
    second = post_file(client, "claim.jpg", duplicate_content)
    exact_duplicate = post_file(client, "another-name.pdf", duplicate_content)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["case_id"] != second.json()["case_id"]
    assert exact_duplicate.status_code == 200
    assert exact_duplicate.json()["case_id"] == second.json()["case_id"]
    assert exact_duplicate.json()["duplicate_of"] == second.json()["case_id"]


def test_list_filters_paginates_and_case_detail_is_retrievable(
    client: TestClient,
    test_engine,
) -> None:
    claim_files = [
        row
        for row in json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
        if row["category"] == "claim_forms"
    ][:2]
    for row in claim_files:
        response = post_file(client, "claim.data", (DATASET_DIR / row["file_path"]).read_bytes())
        assert response.status_code == 202
    with Session(test_engine) as session, session.begin():
        session.execute(update(Case).values(doc_type=DocType.CLAIM_FORM))

    first_page = client.get(
        "/api/v1/cases",
        params={
            "status": "RECEIVED",
            "doc_type": "CLAIM_FORM",
            "page": 1,
            "page_size": 1,
        },
    )
    second_page = client.get(
        "/api/v1/cases",
        params={
            "status": "RECEIVED",
            "doc_type": "CLAIM_FORM",
            "page": 2,
            "page_size": 1,
        },
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 2
    assert len(first_page.json()["items"]) == len(second_page.json()["items"]) == 1
    first_case_id = first_page.json()["items"][0]["case_id"]
    assert first_case_id != second_page.json()["items"][0]["case_id"]
    detail = client.get(f"/api/v1/cases/{first_case_id}")
    assert detail.status_code == 200
    assert detail.json()["case_id"] == first_case_id
    assert "object_key" not in detail.json()
    assert (
        client.get("/api/v1/cases", params={"decision": DecisionKind.APPROVE.value}).json()["total"]
        == 0
    )


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_storage_failure_returns_clean_error_without_case_row(
    test_engine,
    api_settings: ApiSettings,
) -> None:
    class FailedStorage:
        def put(self, **_: object) -> None:
            raise StorageUnavailable("private storage details")

    app = create_app(api_settings, engine=test_engine, storage=FailedStorage())
    with TestClient(app) as failing_client:
        response = post_file(failing_client, "claim.png", _dataset_category_samples()[0][1])

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "STORAGE_UNAVAILABLE",
        "message": "The document could not be stored.",
        "request_id": response.headers["x-request-id"],
    }
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Case)) == 0
