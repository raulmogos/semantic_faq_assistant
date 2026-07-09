import json
import logging
from pathlib import Path

from celery import Task

from app.celery_app import celery_app
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _knowledge_base_path() -> Path:
    """Resolve the knowledge base JSON path for both local dev and Docker."""
    # backend/app/tasks/embed_task.py → .parent×3 = backend/
    # Docker: /app/app/tasks/embed_task.py → .parent×3 = /app (the mounted root)
    backend_root = Path(__file__).resolve().parent.parent.parent
    candidates = [
        backend_root / "data" / "knowledge_base.json",  # Docker: /app/data/
        backend_root.parent / "data" / "knowledge_base.json",  # local dev: project_root/data/
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"knowledge_base.json not found in: {candidates}")


class EmbedTask(Task):
    """
    Celery task base class that lazy-initialises the vector store once per worker
    process and reuses it across task executions.
    """

    _vector_store = None

    @property
    def vector_store(self):
        if self._vector_store is None:
            logger.info("EmbedTask: initialising vector store")
            self._vector_store = get_settings().get_vector_store()
        return self._vector_store


@celery_app.task(
    bind=True,
    base=EmbedTask,
    name="app.tasks.embed_task.rebuild_embeddings",
    queue="embeddings",
    max_retries=3,
    default_retry_delay=30,
)
def rebuild_embeddings(self: EmbedTask) -> dict:
    """
    Load the knowledge base JSON, embed every document and store them in pgvector.
    The collection is wiped and rebuilt from scratch on each run.

    Returns a summary dict with the number of documents embedded.
    """
    logger.info("rebuild_embeddings: starting task id=%s", self.request.id)

    try:
        kb_path = _knowledge_base_path()
        logger.info("rebuild_embeddings: loading knowledge base from %s", kb_path)

        with kb_path.open(encoding="utf-8") as fh:
            data = json.load(fh)

        items = data["knowledge_base_items"]
        documents = [
            f"Question: {item['question']}\nAnswer: {item['answer']}\nCategory: {item['category']}"
            for item in items
        ]
        metadatas = [
            {
                "category": item["category"],
            }
            for item in items
        ]

        logger.info("rebuild_embeddings: embedding %d documents", len(documents))
        settings = get_settings()
        vector_store = settings.get_vector_store(pre_delete_collection=True)
        ids = vector_store.add_texts(texts=documents, metadatas=metadatas)

        result = {
            "status": "completed",
            "documents_embedded": len(ids),
            "collection": settings.vector_collection_name,
        }
        logger.info("rebuild_embeddings: completed %s", result)
        return result

    except Exception as exc:
        logger.error("rebuild_embeddings: failed — %s", exc, exc_info=True)
        raise self.retry(exc=exc) from exc
