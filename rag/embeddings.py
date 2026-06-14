"""
rag/embeddings.py — build the RAG corpus in gold.embeddings (OpenAI only).

Generates a short risk narrative per merchant with gpt-4o, embeds merchant
summaries + recent daily reports with text-embedding-3-small, and stores them as
pgvector rows in Supabase. Finishes by building the HNSW index.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from openai import OpenAI
from psycopg2.extras import execute_values
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from config import db
from rag import prompts

log = logging.getLogger(__name__)

_client = OpenAI(api_key=settings.OPENAI_API_KEY)

INSERT_SQL = """
    INSERT INTO gold.embeddings (doc_type, doc_id, content, embedding, metadata)
    VALUES %s
"""
INSERT_TEMPLATE = "(%s, %s, %s, %s::vector, %s::jsonb)"


def embed_texts(texts: list[str], max_retries: int = 4) -> list[list[float]]:
    """Embed a batch of texts, retrying with backoff on transient errors."""
    for attempt in range(max_retries):
        try:
            resp = _client.embeddings.create(input=texts, model=settings.EMBEDDING_MODEL)
            return [d.embedding for d in resp.data]
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            log.warning("Embedding error (attempt %d): %s — retry in %ds", attempt + 1, e, wait)
            time.sleep(wait)


def _vec(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


def _insert(docs: list[dict], embeddings: list[list[float]]) -> None:
    rows = [
        (d["doc_type"], d["doc_id"], d["content"], _vec(emb), d["metadata"])
        for d, emb in zip(docs, embeddings)
    ]
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, INSERT_SQL, rows, template=INSERT_TEMPLATE, page_size=200)
    finally:
        conn.close()


def _count(doc_type: str) -> int:
    return int(db.read_sql(
        "SELECT COUNT(*) AS c FROM gold.embeddings WHERE doc_type = :t",
        {"t": doc_type},
    ).iloc[0]["c"])


def generate_merchant_narrative(stats: dict) -> str:
    """One-paragraph risk narrative from gpt-4o."""
    prompt = prompts.MERCHANT_NARRATIVE_PROMPT.format(**stats)
    resp = _client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        max_tokens=200,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def embed_merchants(force: bool = False) -> int:
    if not force and _count("merchant_summary") > 0:
        log.info("Merchant embeddings already exist. Skipping.")
        return 0

    merchants = db.read_sql("SELECT * FROM gold.merchant_stats")
    log.info("Embedding %d merchant summaries ...", len(merchants))

    docs = []
    for _, row in tqdm(merchants.iterrows(), total=len(merchants), desc="Narratives"):
        stats = row.to_dict()
        narrative = generate_merchant_narrative(stats)
        content = prompts.MERCHANT_DOC_TEMPLATE.format(narrative=narrative, **stats)
        docs.append({
            "doc_type": "merchant_summary",
            "doc_id": stats["merchant"],
            "content": content,
            "metadata": json.dumps({
                "category": stats["category"],
                "fraud_rate": float(stats["fraud_rate"]),
            }),
        })

    texts = [d["content"] for d in docs]
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), settings.EMBEDDING_BATCH):
        embeddings.extend(embed_texts(texts[i:i + settings.EMBEDDING_BATCH]))
    _insert(docs, embeddings)
    log.info("Inserted %d merchant embeddings", len(docs))
    return len(docs)


def embed_daily_reports(force: bool = False, limit: int = 90) -> int:
    if not force and _count("daily_report") > 0:
        log.info("Daily report embeddings already exist. Skipping.")
        return 0

    daily = db.read_sql(
        "SELECT * FROM gold.kpi_daily ORDER BY date DESC LIMIT :n", {"n": limit}
    )
    if daily.empty:
        log.warning("gold.kpi_daily is empty — run ETL aggregations first.")
        return 0
    log.info("Embedding %d daily reports ...", len(daily))

    docs = []
    for _, row in daily.iterrows():
        r = row.to_dict()
        r["top_category"] = r.get("top_category") or "N/A"
        docs.append({
            "doc_type": "daily_report",
            "doc_id": str(r["date"]),
            "content": prompts.DAILY_DOC_TEMPLATE.format(**r),
            "metadata": json.dumps({"date": str(r["date"]),
                                    "fraud_rate": float(r["fraud_rate"])}),
        })

    embeddings = embed_texts([d["content"] for d in docs])
    _insert(docs, embeddings)
    log.info("Inserted %d daily report embeddings", len(docs))
    return len(docs)


def build_hnsw_index() -> None:
    log.info("Building HNSW index on gold.embeddings ...")
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET maintenance_work_mem = '512MB'")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw
                ON gold.embeddings USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
    finally:
        conn.close()
    log.info("HNSW index ready")


def build_embeddings(force: bool = False) -> None:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set — required for embeddings.")
    embed_merchants(force=force)
    embed_daily_reports(force=force)
    log.info("Embedding pipeline complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    build_embeddings()
    build_hnsw_index()
