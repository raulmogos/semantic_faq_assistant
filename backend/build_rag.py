"""
Build a RAG pipeline for the semantic FQA.
"""

import json
import logging
from pathlib import Path

from logging_config import setup_logging
from settings import get_settings

logger = logging.getLogger(__name__)


def _knowledge_base_path() -> Path:
    project_root = Path(__file__).resolve().parent.parent
    knowledge_base_path = project_root / "data" / "knowledge_base.json"
    if knowledge_base_path.exists():
        return knowledge_base_path
    raise FileNotFoundError(
        "Could not find data/knowledge_base.json at the project root."
    )


def build_rag():
    """
    Build a RAG pipeline for the semantic FQA.
    """

    settings = get_settings()
    setup_logging(settings)

    knowledge_base_path = _knowledge_base_path()
    logger.info("Loading knowledge base from %s", knowledge_base_path)

    with knowledge_base_path.open(encoding="utf-8") as file:
        data = json.load(file)

    items = data["knowledge_base_items"]
    documents = [
        f"Question: {item['question']}\nAnswer: {item['answer']}\nCategory: {item['category']}" for item in items
    ]
    metadatas = [
        {
            "question": item["question"],
            "answer": item["answer"],
            "category": item["category"],
        }
        for item in items
    ]

    logger.info("Embedding and storing %s documents in pgvector", len(documents))
    vector_store = settings.get_vector_store(pre_delete_collection=True)
    ids = vector_store.add_texts(texts=documents, metadatas=metadatas)

    logger.info(
        "Stored %s documents in collection=%s",
        len(ids),
        settings.vector_collection_name,
    )


if __name__ == "__main__":
    build_rag()
