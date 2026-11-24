"""Construct and dispose worker-side database, storage, LLM, and Redis clients."""

from dataclasses import dataclass

from redis import Redis
from sqlalchemy import Engine

from packages.core.config import Settings
from packages.core.db.session import create_database_engine
from packages.core.llm.gateway import Gateway, build_gateway
from packages.core.logging_security import configure_phi_log_redaction
from packages.core.storage import S3Storage
from packages.graph.nodes import GraphRuntime


@dataclass
class WorkerRuntime:
    graph: GraphRuntime
    gateway: Gateway
    redis_client: Redis
    engine: Engine
    storage: S3Storage

    def close(self) -> None:
        self.gateway.close()
        self.redis_client.close()
        self.storage.close()
        self.engine.dispose()


def build_runtime(settings: Settings | None = None) -> WorkerRuntime:
    active_settings = settings or Settings()
    configure_phi_log_redaction(active_settings.phi_log_redaction)
    engine = create_database_engine(active_settings.database_url)
    storage = S3Storage(
        endpoint_url=active_settings.s3_endpoint,
        access_key=active_settings.s3_access_key.get_secret_value(),
        secret_key=active_settings.s3_secret_key.get_secret_value(),
        bucket=active_settings.s3_bucket,
    )
    from packages.core.clients import create_redis_client

    redis_client = create_redis_client(active_settings)
    gateway = build_gateway(active_settings)
    return WorkerRuntime(
        graph=GraphRuntime(
            engine=engine,
            storage=storage,
            settings=active_settings,
            gateway=gateway,
            redis_client=redis_client,
        ),
        gateway=gateway,
        redis_client=redis_client,
        engine=engine,
        storage=storage,
    )
