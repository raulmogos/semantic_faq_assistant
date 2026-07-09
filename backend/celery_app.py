from celery import Celery

from settings import get_settings

settings = get_settings()

celery_app = Celery(
    "semantic_fqa",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["tasks.embed_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_routes={
        "tasks.embed_task.*": {"queue": "embeddings"},
    },
)
