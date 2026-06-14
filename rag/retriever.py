"""
rag/retriever.py — pgvector similarity search over gold.embeddings.

Embeds a query with OpenAI text-embedding-3-small and runs cosine similarity
against the stored vectors. Used by the agent's vector_search tool.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from openai import OpenAI
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from config import db

log = logging.getLogger(__name__)

_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def embed_query(query: str) -> list[float]:
    resp = _openai().embeddings.create(input=[query], model=settings.EMBEDDING_MODEL)
    return resp.data[0].embedding


def _vec_literal(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


def vector_search(query: str, doc_type: str = "", top_k: int = 5) -> list[dict]:
    """Cosine-similarity search. doc_type='' searches all document types."""
    qvec = _vec_literal(embed_query(query))
    filt = "AND doc_type = :doc_type" if doc_type else ""
    sql = text(f"""
        SELECT doc_type, doc_id, content,
               1 - (embedding <=> CAST(:qvec AS vector)) AS similarity
        FROM gold.embeddings
        WHERE TRUE {filt}
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :top_k
    """)
    params = {"qvec": qvec, "top_k": int(top_k)}
    if doc_type:
        params["doc_type"] = doc_type
    with db.get_engine().connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


def format_results(rows: list[dict]) -> str:
    if not rows:
        return "No relevant documents found."
    blocks = []
    for r in rows:
        blocks.append(
            f"[{r['doc_type']} | {r['doc_id']} | similarity={r['similarity']:.3f}]\n"
            f"{r['content']}"
        )
    return "\n---\n".join(blocks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(format_results(vector_search("high risk merchant fraud spike", top_k=3)))
