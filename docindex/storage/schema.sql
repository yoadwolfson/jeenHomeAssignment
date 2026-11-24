CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename       text        NOT NULL,
    split_strategy text        NOT NULL CHECK (split_strategy IN ('fixed', 'sentence', 'paragraph')),
    chunk_index    integer     NOT NULL,
    chunk_text     text        NOT NULL,
    embedding      vector({dimensions}) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (filename, split_strategy, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
