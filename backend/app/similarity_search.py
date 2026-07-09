import logging
import math
from typing import Any

from langchain_core.tools import tool
from langchain_postgres import PGVector

from app.schemas import SimilaritySearchResult
from app.settings import Settings

logger = logging.getLogger(__name__)


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """Compute the cosine similarity between two vectors. Returns a value in [-1, 1]."""
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0 or norm_b == 0:
        logger.warning("cosine_similarity: one or both vectors are zero-length, returning 0.0")
        return 0.0
    return dot_product / (norm_a * norm_b)


def _embedding_to_list(embedding: Any) -> list[float]:
    """Convert a pgvector embedding object to a plain Python list of floats."""
    return [float(value) for value in embedding]


def fetch_all_vectors(
    vector_store: PGVector,
) -> list[tuple[list[float], dict[str, Any], str]]:
    """Fetch all stored embeddings from the PGVector collection."""
    logger.debug("Fetching vectors from collection=%r", vector_store.collection_name)
    with vector_store._make_sync_session() as session:
        collection = vector_store.get_collection(session)
        if not collection:
            logger.warning("fetch_all_vectors: collection not found in the database")
            return []

        rows = (
            session.query(vector_store.EmbeddingStore)
            .filter(vector_store.EmbeddingStore.collection_id == collection.uuid)
            .all()
        )
        logger.debug("fetch_all_vectors: retrieved %d rows", len(rows))

        return [
            (
                _embedding_to_list(row.embedding),
                row.cmetadata or {},
                row.document or "",
            )
            for row in rows
        ]


def search_similar_question(
    question: str,
    settings: Settings,
    *,
    vector_store: PGVector | None = None,
) -> SimilaritySearchResult | None:
    """
    Embed the user's question, load all FAQ vectors, compute cosine similarity
    against each, and return the best match. Returns None if no vectors are stored.
    """
    logger.info("search_similar_question: question=%r", question)
    store = vector_store or settings.get_vector_store()
    query_embedding = settings.get_embedding_model().embed_query(question)
    logger.debug("search_similar_question: embedding computed, fetching vectors")
    all_vectors = fetch_all_vectors(store)

    if not all_vectors:
        logger.info(
            "search_similar_question: no FAQ vectors found in collection=%r",
            settings.vector_collection_name,
        )
        return None

    best_metadata: dict[str, Any] = {}
    best_document = ""
    best_similarity = -1.0

    for stored_embedding, metadata, document in all_vectors:
        similarity = cosine_similarity(query_embedding, stored_embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            best_metadata = metadata
            best_document = document

    logger.info(
        "search_similar_question: best match matched_question=%r category=%r "
        "cosine_similarity=%.4f scanned=%d",
        best_metadata.get("question"),
        best_metadata.get("category"),
        best_similarity,
        len(all_vectors),
    )

    return SimilaritySearchResult(
        question=best_metadata.get("question", best_document),
        answer=best_metadata.get("answer", best_document),
        category=best_metadata.get("category", ""),
        similarity_score=best_similarity,
    )


def create_search_faq_tool(settings: Settings, vector_store: PGVector):
    """
    Factory that builds the search_faq LangChain tool bound to the given
    settings and vector store. The tool is called by the router agent.
    """
    threshold = settings.similarity_threshold

    @tool
    def search_faq(question: str) -> str:
        """Search the FAQ knowledge base for the most semantically similar question."""
        logger.info("search_faq tool called: question=%r", question)
        match = search_similar_question(question, settings, vector_store=vector_store)

        if match is None:
            logger.info("search_faq: no match found, threshold=%.4f", threshold)
            return f"No FAQ entries found. threshold={threshold:.4f}"

        meets = match.similarity_score >= threshold
        logger.info(
            "search_faq: similarity_score=%.4f threshold=%.4f meets_threshold=%s",
            match.similarity_score,
            threshold,
            meets,
        )
        return (
            f"matched_question: {match.question}\n"
            f"answer: {match.answer}\n"
            f"category: {match.category}\n"
            f"similarity_score: {match.similarity_score:.4f}\n"
            f"threshold: {threshold:.4f}\n"
            f"meets_threshold: {meets}\n\n"
        )

    return search_faq
