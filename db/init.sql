CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS message_metadata (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'assistant',
    source      TEXT        NOT NULL,
    similarity_score FLOAT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_metadata_session_id
    ON message_metadata (session_id, created_at);
