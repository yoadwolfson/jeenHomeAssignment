"""ChunkRepository backed by PostgreSQL with pgvector."""

import logging
from importlib.resources import files

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from docindex.domain import EMBEDDING_DIMENSIONS, ChunkRecord, SearchResult, SplitStrategy

SCHEMA_RESOURCE = "schema.sql"

DELETE_CHUNK_SET = "DELETE FROM chunks WHERE filename = %s AND split_strategy = %s"
INSERT_CHUNK = (
    "INSERT INTO chunks (filename, split_strategy, chunk_index, chunk_text, embedding) VALUES (%s, %s, %s, %s, %s)"
)
SEARCH_BY_COSINE = (
    "SELECT filename, split_strategy, chunk_index, chunk_text, 1 - (embedding <=> %(query)s) AS score "
    "FROM chunks ORDER BY embedding <=> %(query)s LIMIT %(top_k)s"
)

logger = logging.getLogger(__name__)


class PostgresChunkRepository:
    """Stores chunks in the `chunks` table; each operation uses its own connection and transaction."""

    def __init__(self, postgres_url: str, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._postgres_url = postgres_url
        self._dimensions = dimensions

    def ensure_schema(self) -> None:
        """Run the idempotent DDL from the packaged schema file."""
        ddl = sql.SQL(files(__package__).joinpath(SCHEMA_RESOURCE).read_text(encoding="utf-8"))
        with psycopg.connect(self._postgres_url) as connection:
            connection.execute(ddl.format(dimensions=sql.Literal(self._dimensions)))
        logger.info("Connected to PostgreSQL (%s) and ensured the schema", self._safe_location())

    def replace_chunks(self, filename: str, strategy: SplitStrategy, records: list[ChunkRecord]) -> None:
        """Delete the (filename, strategy) set and insert `records` in one transaction."""
        rows = [
            (record.filename, record.strategy.value, record.chunk_index, record.text, Vector(record.embedding))
            for record in records
        ]
        # One transaction means every row shares the same now() for created_at.
        with self._connect() as connection, connection.transaction():
            connection.execute(DELETE_CHUNK_SET, (filename, strategy.value))
            with connection.cursor() as cursor:
                cursor.executemany(INSERT_CHUNK, rows)

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        """Return up to `top_k` chunks ordered by cosine distance; score is 1 - distance."""
        with self._connect() as connection:
            rows = connection.execute(SEARCH_BY_COSINE, {"query": Vector(vector), "top_k": top_k}).fetchall()
        return [
            SearchResult(filename, SplitStrategy(strategy), chunk_index, text, float(score))
            for filename, strategy, chunk_index, text, score in rows
        ]

    def _connect(self) -> psycopg.Connection:
        connection = psycopg.connect(self._postgres_url)
        register_vector(connection)
        return connection

    def _safe_location(self) -> str:
        # Only host and database name are ever logged, never the URL or its credentials.
        parameters = conninfo_to_dict(self._postgres_url)
        return f"host={parameters.get('host', 'localhost')}, database={parameters.get('dbname', '')}"
