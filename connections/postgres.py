"""
Conexión reutilizable a PostgreSQL usando psycopg 3 + pool de conexiones.

Uso:
    from connections import PostgresClient

    db = PostgresClient()
    rows = db.fetch_all("SELECT * FROM usuarios WHERE activo = %s", (True,))
    db.execute("UPDATE usuarios SET activo = false WHERE id = %s", (5,))

    with db.transaction() as cur:
        cur.execute("INSERT INTO a ...")
        cur.execute("INSERT INTO b ...")   # commit al salir, rollback si hay error

    db.close()
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import PostgresSettings, get_settings

logger = logging.getLogger(__name__)

Params = Optional[Sequence[Any] | dict[str, Any]]


class PostgresClient:
    def __init__(self, settings: Optional[PostgresSettings] = None) -> None:
        self.settings = settings or get_settings().postgres
        self._pool: Optional[ConnectionPool] = None

    # ------------------------------------------------------------------ pool
    @property
    def pool(self) -> ConnectionPool:
        if self._pool is None:
            s = self.settings
            logger.info("Abriendo pool PostgreSQL %s:%s/%s", s.host, s.port, s.db)
            self._pool = ConnectionPool(
                conninfo=s.dsn,
                min_size=s.pool_min_size,
                max_size=s.pool_max_size,
                kwargs={"row_factory": dict_row},
                open=True,
            )
        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def __enter__(self) -> PostgresClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---------------------------------------------------------- conexiones
    @contextmanager
    def connection(self):
        """Conexión cruda del pool (commit automático al salir sin error)."""
        with self.pool.connection() as conn:
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Cursor dentro de una transacción: commit al salir, rollback si hay excepción."""
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            yield cur

    # ------------------------------------------------------------- helpers
    def execute(self, query: str, params: Params = None) -> int:
        """Ejecuta INSERT/UPDATE/DELETE/DDL. Devuelve filas afectadas."""
        with self.transaction() as cur:
            cur.execute(query, params)
            return cur.rowcount

    def execute_many(self, query: str, params_seq: Sequence[Params]) -> int:
        with self.transaction() as cur:
            cur.executemany(query, params_seq)
            return cur.rowcount

    def fetch_all(self, query: str, params: Params = None) -> list[dict[str, Any]]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def fetch_one(self, query: str, params: Params = None) -> Optional[dict[str, Any]]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def fetch_value(self, query: str, params: Params = None) -> Any:
        row = self.fetch_one(query, params)
        return next(iter(row.values())) if row else None

    def ping(self) -> bool:
        """Prueba la conexión directamente (sin pool) para fallar rápido."""
        try:
            with psycopg.connect(self.settings.dsn) as conn:
                return conn.execute("SELECT 1").fetchone()[0] == 1
        except Exception as exc:  # noqa: BLE001
            logger.error("PostgreSQL no disponible: %s", exc)
            return False
