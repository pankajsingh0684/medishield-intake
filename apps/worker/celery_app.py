"""Celery application configured for authenticated Redis transport."""

from celery import Celery
from kombu import Queue
from sqlalchemy.engine import make_url

from packages.core.config import Settings

celery_app = Celery("medishield")


def configure_celery(redis_url: str, redis_password: str) -> Celery:
    url = make_url(redis_url).set(password=redis_password)
    authenticated_url = url.render_as_string(hide_password=False)
    celery_app.conf.update(
        broker_url=authenticated_url,
        result_backend=authenticated_url,
        task_default_queue="pipeline",
        task_queues=(
            Queue("pipeline"),
            Queue("policy_ingest"),
            Queue("pipeline_dead"),
        ),
        task_routes={
            "apps.worker.tasks.run_pipeline": {"queue": "pipeline"},
            "apps.worker.tasks.dead_letter_pipeline": {"queue": "pipeline_dead"},
        },
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
    )
    return celery_app


_settings = Settings()
configure_celery(_settings.redis_url, _settings.redis_password.get_secret_value())
