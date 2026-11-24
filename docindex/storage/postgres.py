"""ChunkRepository backed by PostgreSQL with pgvector."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib.resources import files
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg import sql

from docindex.domain import EMBEDDING_DIMENSIONS, ChunkRecord, SearchResult, SplitStrategy
from docindex.errors import DatabaseConnectionError, DatabaseOperationError

SCHEMA_RESOURCE = "schema.sql"
# libpq waits indefinitely by default, and a stopped Docker Desktop container swallows connections instead of
# refusing them. The timeout applies per address, so "localhost" (::1 and 127.0.0.1) can take twice as long.
CONNECT_TIMEOUT_SECONDS = 3

DELETE_CHUNK_SET = "DELETE FROM chunks WHERE filename = %s AND split_strategy = %s"
INSERT_CHUNK = (
    "INSERT INTO chunks (filename, split_strategy, chunk_index, chunk_text, embedding) VALUES (%s, %s, %s, %s, %s)"
)
SEARCH_BY_COSINE = (
    "SELECT filename, split_strategy, chunk_index, chunk_text, 1 - (embedding <=> %(query)s) AS score "
    "FROM chunks ORDER BY embedding <=> %(query)s LIMIT %(top_k)s"
)

type Connector = Callable[..., psycopg.Connection[Any]]

logger = logging.getLogger(__name__)


class PostgresChunkRepository:
    """Stores chunks in the `chunks` table; each operation uses its own connection and transaction."""

    def __init__(
        self,
        postgres_url: str,
        dimensions: int = EMBEDDING_DIMENSIONS,
        connect: Connector = psycopg.connect,
    ) -> None:
        self._postgres_url = postgres_url
        self._dimensions = dimensions
        self._connect = connect

    def ensure_schema(self) -> None:
        """Run the idempotent DDL from the packaged schema file."""
        ddl = sql.SQL(files(__package__).joinpath(SCHEMA_RESOURCE).read_text(encoding="utf-8"))
        with self._session() as connection:
            connection.execute(ddl.format(dimensions=sql.Literal(self._dimensions)))
            location = _safe_location(connection)
        # Logged only after the session committed, so the line never claims a schema that was rolled back.
        logger.info("Connected to PostgreSQL (%s) and ensured the schema", location)

    def replace_chunks(self, filename: str, strategy: SplitStrategy, records: list[ChunkRecord]) -> None:
        """Delete the (filename, strategy) set and insert `records` in one transaction."""
        rows = [
            (record.filename, record.strategy.value, record.chunk_index, record.text, Vector(record.embedding))
            for record in records
        ]
        # One transaction means every row shares the same now() for created_at, and a failure keeps the old set.
        with self._session() as connection, connection.transaction():
            register_vector(connection)
            connection.execute(DELETE_CHUNK_SET, (filename, strategy.value))
            with connection.cursor() as cursor:
                cursor.executemany(INSERT_CHUNK, rows)

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        """Return up to `top_k` chunks ordered by cosine distance; score is 1 - distance."""
        with self._session() as connection:
            register_vector(connection)
            rows = connection.execute(SEARCH_BY_COSINE, {"query": Vector(vector), "top_k": top_k}).fetchall()
        return [
            SearchResult(filename, SplitStrategy(strategy), chunk_index, text, float(score))
            for filename, strategy, chunk_index, text, score in rows
        ]

    @contextmanager
    def _session(self) -> Iterator[psycopg.Connection[Any]]:
        """Yield an open connection; commit on success, roll back and raise DatabaseOperationError on failure."""
        connection = self._open()
        try:
            # psycopg's connection block commits on success and rolls back on an exception.
            with connection:
                yield connection
        except psycopg.Error as error:
            raise DatabaseOperationError() from error
        finally:
            # psycopg skips its own close when the commit itself fails; close() is idempotent.
            connection.close()

    def _open(self) -> psycopg.Connection[Any]:
        try:
            return self._connect(self._postgres_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
        except psycopg.ProgrammingError:
            # A malformed URL: libpq's message quotes the whole string, password included, so it is never chained.
            logger.debug("POSTGRES_URL is not a valid PostgreSQL connection URL")
            raise DatabaseConnectionError() from None
        except psycopg.Error as error:
            raise DatabaseConnectionError() from error


def _safe_location(connection: psycopg.Connection[Any]) -> str:
    # Only host and database name are ever logged, never the URL or its credentials.
    return f"host={connection.info.host}, database={connection.info.dbname}"
