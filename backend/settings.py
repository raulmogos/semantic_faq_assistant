from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_postgres.vectorstores import DistanceStrategy
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    pythonunbuffered: int = 1

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "semantic_fqa"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    database_url: str = (
        "postgresql://postgres:postgres@localhost:5432/semantic_fqa"
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    vector_collection_name: str = "knowledge_base"

    top_k: int = 5
    similarity_threshold: float = 0.5

    log_level: str = "INFO"
    log_format: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    log_file: str = ""

    @computed_field
    @property
    def database_connection_string(self) -> str:
        if self.database_url.startswith("postgresql+psycopg://"):
            return self.database_url
        return self.database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    def get_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.openai_model,
            api_key=self.openai_api_key or None,
        )

    def get_embedding_model(self) -> OpenAIEmbeddings:
        return OpenAIEmbeddings(
            model=self.openai_embedding_model,
            api_key=self.openai_api_key or None,
        )

    def get_vector_store(self, *, pre_delete_collection: bool = False) -> PGVector:
        return PGVector(
            embeddings=self.get_embedding_model(),
            collection_name=self.vector_collection_name,
            connection=self.database_connection_string,
            use_jsonb=True,
            pre_delete_collection=pre_delete_collection,
            distance_strategy=DistanceStrategy.COSINE,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
