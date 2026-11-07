import io
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from time import sleep
from types import SimpleNamespace
from uuid import UUID, uuid4

import boto3
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, func, select, update
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from apps.api.factory import create_app
from apps.api.settings import ApiSettings
from apps.worker import tasks as worker_tasks
from apps.worker.celery_app import celery_app
from packages.core.config import Settings
from packages.core.db.models import AgentRun, AuditEvent, Case, Member
from packages.core.enums import AgentStatus, CaseStatus, DecisionKind, DocType
from packages.core.llm.gateway import build_gateway
from packages.core.models import (
    ClaimFields,
    ClaimsResult,
    Classification,
    KycResult,
    OcrField,
    OcrPayload,
)
from packages.core.storage import S3Storage, StorageUnavailable
from packages.graph.builder import build_graph, initial_state
from packages.graph.nodes import GraphRuntime
from packages.graph.routing import route

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
    class NoopPipelineTask:
        def apply_async(self, **_: object) -> None:
            return None

    app = create_app(
        api_settings,
        engine=test_engine,
        storage=test_storage,
        pipeline_task=NoopPipelineTask(),
    )
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


def _insert_graph_case(engine, *, doc_type: DocType = DocType.CLAIM_FORM) -> UUID:
    case_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            Case(
                case_id=case_id,
                status=CaseStatus.RECEIVED,
                doc_type=doc_type,
                object_key="raw/graph/test.png",
                sha256=str(case_id).replace("-", "")[:64].ljust(64, "a"),
                mime_type="image/png",
                received_at=datetime(2025, 12, 15, tzinfo=UTC),
            )
        )
        session.add(
            Member(
                member_id="PT_19116",
                full_name="Christopher Harris I.",
                date_of_birth=date(1954, 4, 25),
                policy_number="MED-GLD-6770619",
                status="ACTIVE",
                id_doc_expiry=date(2030, 1, 1),
            )
        )
    return case_id


def _graph_payloads(*, classifier_status: AgentStatus = AgentStatus.OK):
    now = datetime.now(UTC)
    classification = Classification(
        agent="classifier",
        agent_version="1.0.0",
        status=classifier_status,
        confidence=0.99 if classifier_status == AgentStatus.OK else 0.0,
        started_at=now,
        finished_at=now,
        error="fixture error" if classifier_status == AgentStatus.ERROR else None,
        doc_type=DocType.CLAIM_FORM if classifier_status == AgentStatus.OK else DocType.UNKNOWN,
        routing_tags=[] if classifier_status == AgentStatus.OK else ["NEEDS_REVIEW"],
    )
    ocr = OcrPayload(
        agent="ocr",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        fields=[
            OcrField(key="claim_amount", value="1250.00", confidence=0.95, page=1),
            OcrField(key="service_date", value="12/10/2025", confidence=0.95, page=1),
            OcrField(key="icd10", value="I25.10", confidence=0.95, page=1),
            OcrField(key="cpt", value="99213", confidence=0.95, page=1),
            OcrField(key="provider_npi", value="NPI-5610293847", confidence=0.95, page=1),
            OcrField(key="signature_present", value="Yes", confidence=0.95, page=1),
            OcrField(key="member_id", value="PT_19116", confidence=0.95, page=1),
            OcrField(key="member_name", value="Christopher Harris I.", confidence=0.95, page=1),
            OcrField(key="dob", value="04/25/1954", confidence=0.95, page=1),
            OcrField(key="policy_number", value="MED-GLD-6770619", confidence=0.95, page=1),
        ],
        raw_text="",
        bounding_boxes=[],
        pages=1,
        used_text_layer=True,
    )
    claims = ClaimsResult(
        agent="claims",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        extracted_fields=ClaimFields(
            claim_amount=Decimal("1250.00"),
            icd10_codes=["I25.10"],
            cpt_codes=["99213"],
            provider_npi="5610293847",
            service_date=date(2025, 12, 10),
        ),
        schema_valid=True,
        validation_errors=[],
    )
    kyc_error = KycResult(
        agent="kyc",
        agent_version="1.0.0",
        status=AgentStatus.ERROR,
        confidence=0.0,
        started_at=now,
        finished_at=now,
        error="fixture KYC error",
        kyc_passed=False,
        flags=[],
        member_ref=None,
    )
    return classification, ocr, claims, kyc_error


def _graph_runtime(engine, storage, overrides) -> GraphRuntime:
    return GraphRuntime(
        engine=engine,
        storage=storage,
        settings=SimpleNamespace(
            agent_timeout_s=2,
            threshold_classify_review=0.6,
            llm_vision_model="test-vision",
            npi_luhn_strict=False,
            claim_amount_max=Decimal(1000000),
        ),
        gateway=None,
        agent_overrides=overrides,
        retry_backoff_seconds=0,
    )


def test_routing_table_has_expected_targets_for_every_document_type():
    assert route(DocType.CLAIM_FORM) == {"kyc", "claims", "policy", "fraud"}
    assert route(DocType.ID_DOCUMENT) == {"kyc", "fraud"}
    assert route(DocType.DISCHARGE_SUMMARY) == {"kyc", "claims", "fraud"}
    assert route(DocType.PRESCRIPTION) == {"kyc", "claims", "fraud"}
    assert route(DocType.POLICY_AMENDMENT) == {"kyc", "policy"}
    assert route(DocType.UNKNOWN) == set()


def test_kyc_error_still_joins_claims_and_ends_needs_review(test_engine):
    case_id = _insert_graph_case(test_engine)
    classification, ocr, claims, kyc_error = _graph_payloads()
    image = (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()

    class FakeStorage:
        def get(self, _: str) -> bytes:
            return image

    completed: list[str] = []
    overrides = {
        "classifier": lambda _: classification,
        "ocr": lambda _: ocr,
        "kyc": lambda _: kyc_error,
        "claims": lambda _: completed.append("claims") or claims,
    }
    runtime = _graph_runtime(test_engine, FakeStorage(), overrides)
    state = build_graph(runtime).invoke(initial_state(str(case_id), str(uuid4())))

    assert completed == ["claims"]
    assert state["terminal_status"] == CaseStatus.NEEDS_REVIEW.value
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.NEEDS_REVIEW
        runs = list(session.scalars(select(AgentRun).where(AgentRun.case_id == case_id)))
        events = list(session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id)))
    run_statuses = {run.agent: run.status for run in runs}
    assert run_statuses["kyc"] == AgentStatus.ERROR.value
    assert run_statuses["claims"] == AgentStatus.OK.value
    assert run_statuses["policy"] == AgentStatus.SKIPPED.value
    assert run_statuses["fraud"] == AgentStatus.SKIPPED.value
    assert run_statuses["orchestrator"] == AgentStatus.SKIPPED.value
    event_pairs = {(event.actor, event.event_type) for event in events}
    expected_nodes = {
        "load_document",
        "classifier",
        "ocr",
        "route_specialists",
        "kyc",
        "claims",
        "policy",
        "join",
        "fraud",
        "orchestrator",
        "aggregate",
    }
    assert event_pairs >= {
        (node, event_type) for node in expected_nodes for event_type in ("NODE_START", "NODE_END")
    }


def test_ocr_error_routes_to_review_without_specialists(test_engine):
    case_id = _insert_graph_case(test_engine)
    classification, ocr, _, _ = _graph_payloads()
    ocr_error = ocr.model_copy(
        update={"status": AgentStatus.ERROR, "confidence": 0.0, "error": "fixture OCR error"}
    )

    class FakeStorage:
        def get(self, _: str) -> bytes:
            return (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()

    routed_calls: list[str] = []
    runtime = _graph_runtime(
        test_engine,
        FakeStorage(),
        {
            "classifier": lambda _: classification,
            "ocr": lambda _: ocr_error,
            "kyc": lambda _: routed_calls.append("kyc"),
            "claims": lambda _: routed_calls.append("claims"),
        },
    )
    state = build_graph(runtime).invoke(initial_state(str(case_id), str(uuid4())))

    assert state["terminal_status"] == CaseStatus.NEEDS_REVIEW.value
    assert routed_calls == []
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.NEEDS_REVIEW
        agents = set(session.scalars(select(AgentRun.agent).where(AgentRun.case_id == case_id)))
    assert agents == {"classifier", "ocr"}


@pytest.mark.parametrize("doc_type", [DocType.CLAIM_FORM, DocType.DISCHARGE_SUMMARY])
def test_fan_in_waits_for_routed_nodes_before_join_and_downstream(
    test_engine, monkeypatch: pytest.MonkeyPatch, doc_type: DocType
):
    from packages.graph import builder as graph_builder_module
    from packages.graph import nodes as graph_nodes_module

    case_id = _insert_graph_case(test_engine, doc_type=doc_type)
    classification, ocr, claims, kyc_error = _graph_payloads()
    classification = classification.model_copy(update={"doc_type": doc_type})
    kyc_ok = kyc_error.model_copy(
        update={"status": AgentStatus.OK, "error": None, "kyc_passed": True}
    )
    image = (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()

    class FakeStorage:
        def get(self, _: str) -> bytes:
            return image

    order: list[str] = []
    completed = Event()
    original_policy = graph_nodes_module._placeholder_policy

    def finish_policy():
        order.append("policy")
        return original_policy()

    monkeypatch.setattr(graph_nodes_module, "_placeholder_policy", finish_policy)
    runtime = _graph_runtime(
        test_engine,
        FakeStorage(),
        {
            "classifier": lambda _: classification,
            "ocr": lambda _: ocr,
            "kyc": lambda _: (sleep(0.03), order.append("kyc"), kyc_ok)[-1],
            "claims": lambda _: (order.append("claims"), completed.set(), claims)[-1],
        },
    )
    original_factory = graph_builder_module.build_nodes

    def observed_factory(graph_runtime):
        nodes = original_factory(graph_runtime)
        original_join = nodes["join"]

        def observed_join(state):
            routed_required = {"kyc", "claims"}
            assert routed_required <= set(order)
            if doc_type == DocType.CLAIM_FORM:
                assert "policy" in order
            else:
                assert "policy" not in route(doc_type)
            order.append("join")
            return original_join(state)

        nodes["join"] = observed_join
        for name in ("fraud", "orchestrator", "aggregate"):
            original_node = nodes[name]

            def observed_node(state, node_name=name, node=original_node):
                assert "join" in order
                order.append(node_name)
                return node(state)

            nodes[name] = observed_node
        return nodes

    monkeypatch.setattr(graph_builder_module, "build_nodes", observed_factory)
    state = build_graph(runtime).invoke(initial_state(str(case_id), str(uuid4())))

    assert completed.is_set()
    assert order.index("join") > order.index("kyc")
    assert order.index("join") > order.index("claims")
    if doc_type == DocType.CLAIM_FORM:
        assert order.index("join") > order.index("policy")
    else:
        with Session(test_engine) as session:
            policy_run = session.scalar(
                select(AgentRun).where(
                    AgentRun.case_id == case_id,
                    AgentRun.agent == "policy",
                )
            )
        assert policy_run is not None and policy_run.status == AgentStatus.SKIPPED.value
    assert order.index("join") < order.index("fraud") < order.index("orchestrator")
    assert state["terminal_status"] == CaseStatus.AGGREGATED.value


def test_classifier_error_routes_to_review_without_ocr(test_engine):
    case_id = _insert_graph_case(test_engine)
    classification, ocr, _, _ = _graph_payloads(classifier_status=AgentStatus.ERROR)

    class FakeStorage:
        def get(self, _: str) -> bytes:
            return (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()

    calls: list[str] = []
    runtime = _graph_runtime(
        test_engine,
        FakeStorage(),
        {
            "classifier": lambda _: classification,
            "ocr": lambda _: calls.append("ocr") or ocr,
        },
    )
    state = build_graph(runtime).invoke(initial_state(str(case_id), str(uuid4())))

    assert calls == []
    assert state["terminal_status"] == CaseStatus.NEEDS_REVIEW.value
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.NEEDS_REVIEW
        agents = list(session.scalars(select(AgentRun.agent).where(AgentRun.case_id == case_id)))
    assert agents == ["classifier"]


def test_document_load_failure_ends_failed(test_engine):
    case_id = _insert_graph_case(test_engine)

    class MissingStorage:
        def get(self, _: str) -> bytes:
            raise StorageUnavailable("missing object")

    runtime = _graph_runtime(test_engine, MissingStorage(), {})
    state = build_graph(runtime).invoke(initial_state(str(case_id), str(uuid4())))

    assert state["terminal_status"] == CaseStatus.FAILED.value
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.FAILED


def test_upload_runs_eager_pipeline_with_stub_fixtures(
    api_settings: ApiSettings,
    test_engine,
    test_storage: S3Storage,
    monkeypatch: pytest.MonkeyPatch,
):
    image_path = DATASET_DIR / "id_documents" / "id_PT_15075.png"
    image = image_path.read_bytes()
    metadata = json.loads((DATASET_DIR / "metadata.json").read_text(encoding="utf-8"))
    dataset_row = next(row for row in metadata if row["doc_id"] == "id_PT_15075")
    with Session(test_engine) as session, session.begin():
        session.add(
            Member(
                member_id="PT_15075",
                full_name="Christopher Harris I.",
                date_of_birth=date(1954, 4, 25),
                policy_number=dataset_row["policy_number"],
                status="ACTIVE",
                id_doc_expiry=date(2029, 12, 14),
            )
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=api_settings.database_url,
        redis_url=api_settings.redis_url,
        redis_password=api_settings.redis_password,
        s3_endpoint=api_settings.s3_endpoint,
        s3_access_key=api_settings.s3_access_key,
        s3_secret_key=api_settings.s3_secret_key,
        s3_bucket=api_settings.s3_bucket,
        qdrant_url=api_settings.qdrant_url,
        qdrant_api_key=api_settings.qdrant_api_key,
        llm_vision_model="test-vision",
        llm_text_model="test-text",
        llm_fallback_model="test-fallback",
        jwt_secret=api_settings.jwt_secret,
        seed_test_user_password=api_settings.seed_test_user_password,
    )
    gateway = build_gateway(settings)
    ocr_result = OcrPayload(
        agent="ocr",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        model="dataset-test",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        fields=[
            OcrField(key="member_id", value="PT_15075", confidence=0.95, page=1),
            OcrField(key="member_name", value="Christopher Harris I.", confidence=0.95, page=1),
            OcrField(key="dob", value="04/25/1954", confidence=0.95, page=1),
            OcrField(
                key="policy_number",
                value=dataset_row["policy_number"],
                confidence=0.95,
                page=1,
            ),
            OcrField(key="id_expiry", value="12/14/2029", confidence=0.95, page=1),
        ],
        raw_text="MEDICARE MEMBER ID",
        bounding_boxes=[],
        pages=1,
        used_text_layer=False,
    )
    kyc_result = KycResult(
        agent="kyc",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        model="dataset-test",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        kyc_passed=True,
        flags=[],
        member_ref="PT_15075",
    )
    runtime_settings = SimpleNamespace(
        agent_timeout_s=api_settings.agent_timeout_s
        if hasattr(api_settings, "agent_timeout_s")
        else 90,
        threshold_classify_review=0.6,
        llm_vision_model="test-vision",
        npi_luhn_strict=False,
        claim_amount_max=Decimal(1_000_000),
    )
    monkeypatch.setitem(celery_app.conf, "task_always_eager", True)
    monkeypatch.setitem(celery_app.conf, "task_eager_propagates", True)
    monkeypatch.setattr(
        worker_tasks,
        "runtime_factory",
        lambda: SimpleNamespace(
            graph=GraphRuntime(
                engine=test_engine,
                storage=test_storage,
                settings=runtime_settings,
                gateway=gateway,
                agent_overrides={
                    "ocr": lambda _: ocr_result,
                    "kyc": lambda _: kyc_result,
                },
                retry_backoff_seconds=0,
            ),
            close=lambda: None,
        ),
    )
    app = create_app(api_settings, engine=test_engine, storage=test_storage)
    with TestClient(app) as eager_client:
        response = post_file(eager_client, image_path.name, image)

    assert response.status_code == 202
    case_id = UUID(response.json()["case_id"])
    with Session(test_engine) as session:
        case = session.get(Case, case_id)
        runs = list(session.scalars(select(AgentRun).where(AgentRun.case_id == case_id)))
        events = list(session.scalars(select(AuditEvent).where(AuditEvent.case_id == case_id)))
    assert case is not None and case.status == CaseStatus.AGGREGATED, [
        (run.agent, run.status, run.error) for run in runs
    ]
    assert {run.agent for run in runs} >= {"classifier", "ocr", "kyc", "claims", "policy"}
    assert any(event.event_type == "NODE_START" and event.actor == "classifier" for event in events)
    assert any(event.event_type == "NODE_END" and event.actor == "kyc" for event in events)


def _successful_kyc() -> KycResult:
    now = datetime.now(UTC)
    return KycResult(
        agent="kyc",
        agent_version="1.0.0",
        status=AgentStatus.OK,
        confidence=0.95,
        started_at=now,
        finished_at=now,
        kyc_passed=True,
        flags=[],
        member_ref="PT_19116",
    )


def test_pipeline_rerun_uses_new_pipeline_run_and_latest_status(
    test_engine, monkeypatch: pytest.MonkeyPatch
):
    case_id = _insert_graph_case(test_engine)
    classification, ocr, claims, _ = _graph_payloads()
    image = (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()

    class FakeStorage:
        def get(self, _: str) -> bytes:
            return image

    current_classification = [classification]
    runtime = _graph_runtime(
        test_engine,
        FakeStorage(),
        {
            "classifier": lambda _: current_classification[0],
            "ocr": lambda _: ocr,
            "kyc": lambda _: _successful_kyc(),
            "claims": lambda _: claims,
        },
    )
    monkeypatch.setattr(
        worker_tasks,
        "runtime_factory",
        lambda: SimpleNamespace(graph=runtime, engine=test_engine, close=lambda: None),
    )
    first_result = worker_tasks.run_pipeline.apply(args=[str(case_id)], throw=True).get()
    current_classification[0] = classification.model_copy(
        update={
            "status": AgentStatus.ERROR,
            "confidence": 0.0,
            "error": "rerun classifier failure",
            "doc_type": DocType.UNKNOWN,
            "routing_tags": ["NEEDS_REVIEW"],
        }
    )
    second_result = worker_tasks.run_pipeline.apply(args=[str(case_id)], throw=True).get()
    first_pipeline = UUID(first_result["pipeline_run"])
    second_pipeline = UUID(second_result["pipeline_run"])

    assert first_pipeline != second_pipeline
    assert first_result["status"] == CaseStatus.AGGREGATED.value
    assert second_result["status"] == CaseStatus.NEEDS_REVIEW.value
    with Session(test_engine) as session:
        case = session.get(Case, case_id)
        runs = list(session.scalars(select(AgentRun).where(AgentRun.case_id == case_id)))
    assert case is not None and case.status == CaseStatus.NEEDS_REVIEW
    assert {run.pipeline_run for run in runs} == {first_pipeline, second_pipeline}


class RetryRequested(Exception):
    pass


def _invoke_task_attempt(task, case_id: UUID, pipeline_run: UUID, retry_number: int):
    task.push_request(retries=retry_number)
    try:
        return task.run(str(case_id), str(pipeline_run))
    finally:
        task.pop_request()


def test_pipeline_task_retries_three_times_with_backoff_then_fails(
    test_engine, monkeypatch: pytest.MonkeyPatch
):
    case_id = _insert_graph_case(test_engine)
    pipeline_run = uuid4()
    attempts: list[str] = []
    retry_calls: list[tuple[list[str], int]] = []

    class AlwaysFailingGraph:
        def invoke(self, state):
            attempts.append(state["pipeline_run"])
            raise RuntimeError("transient graph infrastructure error")

    monkeypatch.setattr(
        worker_tasks,
        "runtime_factory",
        lambda: SimpleNamespace(
            graph=None,
            engine=test_engine,
            close=lambda: None,
        ),
    )
    monkeypatch.setattr(worker_tasks, "build_graph", lambda _: AlwaysFailingGraph())
    task = worker_tasks.run_pipeline._get_current_object()

    def request_retry(*, exc, args, countdown):
        del exc
        retry_calls.append((args, countdown))
        raise RetryRequested

    monkeypatch.setattr(task, "retry", request_retry)
    for retry_number in range(2):
        with pytest.raises(RetryRequested):
            _invoke_task_attempt(task, case_id, pipeline_run, retry_number)
    result = _invoke_task_attempt(task, case_id, pipeline_run, 2)

    assert len(attempts) == 3
    assert set(attempts) == {str(pipeline_run)}
    assert [countdown for _, countdown in retry_calls] == [1, 2]
    assert all(args == [str(case_id), str(pipeline_run)] for args, _ in retry_calls)
    assert result["status"] == CaseStatus.FAILED.value
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.FAILED


def test_pipeline_task_succeeds_on_second_attempt_with_same_pipeline_run(
    test_engine, monkeypatch: pytest.MonkeyPatch
):
    case_id = _insert_graph_case(test_engine)
    pipeline_run = uuid4()
    attempt_count = 0
    retry_calls: list[int] = []

    class RetryThenSuccessGraph:
        def invoke(self, state):
            nonlocal attempt_count
            attempt_count += 1
            assert state["pipeline_run"] == str(pipeline_run)
            if attempt_count == 1:
                raise RuntimeError("transient infrastructure error")
            with Session(test_engine) as session, session.begin():
                session.get(Case, case_id).status = CaseStatus.AGGREGATED
            return {"terminal_status": CaseStatus.AGGREGATED.value}

    monkeypatch.setattr(
        worker_tasks,
        "runtime_factory",
        lambda: SimpleNamespace(graph=None, engine=test_engine, close=lambda: None),
    )
    monkeypatch.setattr(worker_tasks, "build_graph", lambda _: RetryThenSuccessGraph())
    task = worker_tasks.run_pipeline._get_current_object()

    def request_retry(*, exc, args, countdown):
        del exc, args
        retry_calls.append(countdown)
        raise RetryRequested

    monkeypatch.setattr(task, "retry", request_retry)
    with pytest.raises(RetryRequested):
        _invoke_task_attempt(task, case_id, pipeline_run, 0)
    result = _invoke_task_attempt(task, case_id, pipeline_run, 1)

    assert attempt_count == 2
    assert retry_calls == [1]
    assert result["pipeline_run"] == str(pipeline_run)
    assert result["status"] == CaseStatus.AGGREGATED.value
    with Session(test_engine) as session:
        assert session.get(Case, case_id).status == CaseStatus.AGGREGATED


def test_duplicate_upload_enqueues_once_and_enqueue_observes_committed_case(
    api_settings: ApiSettings,
    test_engine,
    test_storage: S3Storage,
):
    image = (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes()
    enqueued: list[tuple[str, str]] = []

    class CommitCheckingTask:
        def apply_async(self, *, args, queue):
            case_id, pipeline_run = args
            with Session(test_engine) as independent_session:
                assert independent_session.get(Case, UUID(case_id)) is not None
            assert queue == "pipeline"
            enqueued.append((case_id, pipeline_run))

    app = create_app(
        api_settings,
        engine=test_engine,
        storage=test_storage,
        pipeline_task=CommitCheckingTask(),
    )
    with TestClient(app) as client:
        first = post_file(client, "first.png", image)
        second = post_file(client, "same-content.png", image)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate_of"] == first.json()["case_id"]
    assert len(enqueued) == 1


def test_failed_case_commit_does_not_enqueue(
    api_settings: ApiSettings,
    test_engine,
    test_storage: S3Storage,
):
    enqueued: list[tuple[str, ...]] = []

    class RecordingTask:
        def apply_async(self, *, args, queue):
            del queue
            enqueued.append(tuple(args))

    def reject_case_commit(session):
        if any(
            isinstance(instance, Case)
            for instance in (*session.new, *session.identity_map.values())
        ):
            raise RuntimeError("simulated commit failure")

    app = create_app(
        api_settings,
        engine=test_engine,
        storage=test_storage,
        pipeline_task=RecordingTask(),
    )
    sqlalchemy_event.listen(Session, "before_commit", reject_case_commit)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = post_file(
                client,
                "commit-failure.png",
                (DATASET_DIR / "claim_forms" / "claim_PT_15075.png").read_bytes(),
            )
    finally:
        sqlalchemy_event.remove(Session, "before_commit", reject_case_commit)

    assert response.status_code == 500
    assert enqueued == []
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Case)) == 0
