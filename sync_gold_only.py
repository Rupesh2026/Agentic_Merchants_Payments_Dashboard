"""
sync_gold_only.py
  1. Re-run gold aggregations locally (merchant_stats approval_rate fix + payout fee fix)
  2. Sync affected gold tables to Supabase (skips features / risk_scores / ML)

Run:
    .venv\Scripts\python sync_gold_only.py
"""

import json, sys, time, logging
from pathlib import Path
from urllib.parse import urlparse, unquote

import pandas as pd
import psycopg2, psycopg2.extras
from psycopg2.extras import Json
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("sync_gold")

SUPABASE_URL = "postgresql://postgres.jshnnfzqgiwcnznwieje:Getjob%402026!@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

TABLES = [
    "gold.kpi_daily",
    "gold.merchant_stats",
    "gold.category_stats",
    "gold.state_stats",
    "gold.fraud_heatmap",
    "gold.payout_history",
]


def _native(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if isinstance(v, dict):
        return Json(v)
    if isinstance(v, list):
        return json.dumps(v)
    return v.item() if hasattr(v, "item") else v


def sync_table(src_engine, tgt_conn, schema_table: str):
    schema, table = schema_table.split(".")
    with src_engine.connect() as conn:
        total = conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar()
    if total == 0:
        log.info("  %s: 0 rows — skipping", schema_table)
        return
    log.info("  %s: %s rows", schema_table, f"{total:,}")
    with tgt_conn.cursor() as cur:
        cur.execute(f'TRUNCATE "{schema}"."{table}" CASCADE')
    tgt_conn.commit()

    CHUNK, offset, copied = 50_000, 0, 0
    t0 = time.time()
    while offset < total:
        df = pd.read_sql(
            text(f'SELECT * FROM "{schema}"."{table}" LIMIT {CHUNK} OFFSET {offset}'),
            src_engine,
        )
        if df.empty:
            break
        cols = list(df.columns)
        col_str = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{schema}"."{table}" ({col_str}) VALUES %s ON CONFLICT DO NOTHING'
        records = [tuple(_native(v) for v in row) for row in df.itertuples(index=False, name=None)]
        psycopg2.extras.execute_values(tgt_conn.cursor(), sql, records, page_size=5_000)
        tgt_conn.commit()
        copied += len(records)
        offset += CHUNK
        log.info("    %s / %s (%.0f%%)", f"{copied:,}", f"{total:,}", copied / total * 100)
    log.info("  done in %.1fs", time.time() - t0)


def main():
    from config import settings
    src = create_engine(settings.SQLALCHEMY_URL, pool_pre_ping=True)

    log.info("=== Step 1: Re-running gold aggregations locally ===")
    from etl.gold.aggregations import run_aggregations
    run_aggregations()

    log.info("=== Step 2: Syncing gold tables to Supabase ===")
    _p = urlparse(SUPABASE_URL)
    tgt = psycopg2.connect(
        host=_p.hostname, port=_p.port, dbname=_p.path.lstrip("/"),
        user=unquote(_p.username), password=unquote(_p.password),
        sslmode="require", connect_timeout=30,
    )
    tgt.autocommit = False

    for t in TABLES:
        try:
            sync_table(src, tgt, t)
        except Exception as e:
            log.error("  ERROR on %s: %s", t, e)
            tgt.rollback()

    tgt.close()
    log.info("Done. Gold tables updated in Supabase.")


if __name__ == "__main__":
    main()
