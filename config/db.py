# config/db.py — shared Supabase Postgres access
#
# Uses psycopg2 directly with autocommit=True for all writes/DDL to avoid
# the Supabase session-pooler read-only recycling issue.
# SQLAlchemy engine is kept only for pd.read_sql() compatibility.

from __future__ import annotations

import functools
import io

import pandas as pd
import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import settings


@functools.lru_cache(maxsize=1)
def get_engine() -> Engine:
    """SQLAlchemy engine — used only for read_sql (SELECT queries)."""
    return create_engine(
        settings.SQLALCHEMY_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )


def _connect() -> psycopg2.extensions.connection:
    """Open a direct psycopg2 connection with autocommit=True.

    Bypasses SQLAlchemy pooling so the Supabase session-pooler cannot
    recycle us into a read-only connection mid-operation.
    """
    conn = psycopg2.connect(
        host=settings.PG_HOST,
        port=settings.PG_PORT,
        dbname=settings.PG_DB,
        user=settings.PG_USER,
        password=settings.PG_PASSWORD,
        sslmode=settings.PG_SSLMODE,
        connect_timeout=30,
    )
    conn.autocommit = True
    return conn


def get_connection() -> psycopg2.extensions.connection:
    """Return a direct psycopg2 connection with autocommit=True.

    Callers are responsible for closing the connection.  Used by predict.py
    and embeddings.py for write-heavy paths that need UPSERT / DDL.
    """
    return _connect()


def execute(statement: str, params: dict | None = None) -> None:
    """Execute a single DDL/DML statement via direct psycopg2 (autocommit)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params or {})


def bulk_insert(df: pd.DataFrame, table: str, schema: str,
                chunksize: int = 2000) -> None:
    """Bulk-insert a DataFrame using psycopg2 execute_values (fast, autocommit)."""
    if df.empty:
        return
    cols = list(df.columns)
    col_str = ", ".join(f'"{c}"' for c in cols)
    sql = f'INSERT INTO "{schema}"."{table}" ({col_str}) VALUES %s'

    # Convert all values to native Python types so psycopg2 can adapt them
    def _native(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(v, "item"):          # numpy scalar → Python scalar
            return v.item()
        if hasattr(v, "isoformat"):     # date / datetime → keep as-is (psycopg2 handles)
            return v
        return v

    records = [
        tuple(_native(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    with _connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records,
                                           page_size=chunksize)


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def execute_script(sql_text: str) -> None:
    """Execute a multi-statement SQL script."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)


def apply_schema() -> None:
    """Apply config/schema.sql to the connected Supabase database."""
    schema_path = settings.BASE_DIR / "config" / "schema.sql"
    execute_script(schema_path.read_text(encoding="utf-8"))


def ping() -> bool:
    """Return True if the database is reachable."""
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import sys
    ok = ping()
    print("Supabase connection:", "OK" if ok else "FAILED")
    if ok and "--schema" in sys.argv:
        print("Applying config/schema.sql ...")
        apply_schema()
        print("Schema applied.")
