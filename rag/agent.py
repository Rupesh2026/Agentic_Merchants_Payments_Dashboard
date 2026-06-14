"""
rag/agent.py — Agentic RAG with Google ADK + OpenAI gpt-4o (via LiteLLM).

The agent reasons over five tools backed by Supabase (gold/clean layers + the
pgvector corpus) and the XGBoost SHAP outputs. OpenAI is the only model
provider; ADK reaches it through LiteLlm("openai/gpt-4o").
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from config import db
from rag import retriever
from rag.prompts import SYSTEM_PROMPT
from rag.security import SAFE_REFUSAL
from rag.security import sanitize_tool_output
from rag.security import sanitize_user_input
from rag.security import validate_assistant_output

log = logging.getLogger(__name__)

APP_NAME = "payments_ai_analyst"
USER_ID = "dashboard"


def _safe_tool_text(text: str) -> str:
    return sanitize_tool_output(text)


# ── Tools (plain functions; ADK auto-wraps as FunctionTools) ─────────────────

def vector_search(query: str, doc_type: str = "", top_k: int = 5) -> str:
    """Semantic search over the RAG corpus (merchant summaries, daily reports).

    Args:
        query: Natural-language search query.
        doc_type: Optional filter: 'merchant_summary' or 'daily_report'. '' = all.
        top_k: Number of results to return.
    """
    try:
        rows = retriever.vector_search(query, doc_type=doc_type or "", top_k=top_k)
        return _safe_tool_text(retriever.format_results(rows))
    except Exception as e:  # noqa: BLE001
        return f"Search error: {e}"


def sql_query(query: str) -> str:
    """Run a read-only SQL SELECT against the gold.* and clean.* schemas.

    Only SELECT statements are permitted. Returns up to 20 rows as text.
    """
    upper = query.strip().upper()
    if not upper.startswith(("SELECT", "WITH")):
        return "Error: only SELECT/WITH read-only queries are allowed."
    if any(kw in upper for kw in ("DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER", "CREATE", "GRANT")):
        return "Error: only read-only SELECT statements are allowed."
    try:
        df = db.read_sql(query)
        if df.empty:
            return "Query returned no results."
        note = f"(showing first 20 of {len(df)} rows)\n" if len(df) > 20 else ""
        return _safe_tool_text(note + df.head(20).to_string(index=False))
    except Exception as e:  # noqa: BLE001
        return f"SQL error: {e}"


def get_merchant_detail(merchant_name: str) -> str:
    """Get full stats and risk profile for a merchant (partial name matches).

    Args:
        merchant_name: Exact or partial merchant name.
    """
    try:
        df = db.read_sql(
            """
            SELECT ms.*,
                   (SELECT COUNT(*) FROM clean.transactions ct
                     WHERE ct.merchant ILIKE :pat) AS tx_total
            FROM gold.merchant_stats ms
            WHERE ms.merchant ILIKE :pat
            ORDER BY ms.total_volume DESC
            LIMIT 3
            """,
            {"pat": f"%{merchant_name}%"},
        )
        if df.empty:
            return f"No merchant found matching '{merchant_name}'."
        out = []
        for _, r in df.iterrows():
            vs = (r["fraud_rate"] / settings.INDUSTRY_FRAUD_RATE) if r["fraud_rate"] else 0
            out.append(
                f"Merchant: {r['merchant']}\n"
                f"Category: {r['category']}\n"
                f"Total Volume: ${r['total_volume']:,.2f}\n"
                f"Transactions: {r['total_transactions']:,}\n"
                f"Avg Ticket: ${r['avg_ticket']:.2f}\n"
                f"Fraud Rate: {r['fraud_rate']:.4%} ({vs:.1f}x industry avg)\n"
                f"Chargebacks: {r['chargeback_count']}\n"
                f"Approval Rate: {r['approval_rate']:.2%}\n"
                f"Avg Risk Score: {r['risk_score_avg']:.1f}/100\n"
                f"Active: {r['first_seen']} -> {r['last_seen']}"
            )
        return _safe_tool_text("\n\n".join(out))
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"


def explain_fraud_transaction(trans_num: str) -> str:
    """Explain a transaction's fraud risk using the XGBoost SHAP values.

    Args:
        trans_num: The transaction number (trans_num).
    """
    try:
        df = db.read_sql(
            """
            SELECT ct.trans_num, ct.merchant, ct.category, ct.amt, ct.trans_at,
                   ct.city, ct.state, rs.risk_score, rs.fraud_probability,
                   rs.risk_tier, rs.top_shap_features
            FROM clean.transactions ct
            JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
            WHERE ct.trans_num = :tn
            LIMIT 1
            """,
            {"tn": trans_num},
        )
        if df.empty:
            return f"Transaction '{trans_num}' not found (or not yet scored)."
        r = df.iloc[0]
        shap = r["top_shap_features"]
        if isinstance(shap, str):
            shap = json.loads(shap)
        shap = shap or []
        lines = "\n".join(
            f"  - {f['explanation']} (SHAP {f['shap_value']:+.3f})" for f in shap
        )
        return (
            f"Transaction: {r['trans_num']}\n"
            f"Merchant: {r['merchant']} ({r['category']})\n"
            f"Amount: ${r['amt']:.2f}\n"
            f"Time: {r['trans_at']}\n"
            f"Location: {r['city']}, {r['state']}\n\n"
            f"Risk Score: {r['risk_score']}/100 ({str(r['risk_tier']).upper()})\n"
            f"Fraud Probability: {r['fraud_probability']:.2%}\n\n"
            f"Top contributing factors:\n{lines}"
        )
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"


def get_kpi_summary(period: str = "today") -> str:
    """Get KPI metrics for a period: 'today', 'yesterday', '7d', '30d', or 'mtd'."""
    where = {
        "today":     "date = (SELECT MAX(date) FROM gold.kpi_daily)",
        "yesterday": "date = (SELECT MAX(date) - 1 FROM gold.kpi_daily)",
        "7d":        "date >= (SELECT MAX(date) - 6 FROM gold.kpi_daily)",
        "30d":       "date >= (SELECT MAX(date) - 29 FROM gold.kpi_daily)",
        "mtd":       "EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM (SELECT MAX(date) FROM gold.kpi_daily)) "
                     "AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM (SELECT MAX(date) FROM gold.kpi_daily))",
    }.get(period, "date = (SELECT MAX(date) FROM gold.kpi_daily)")
    try:
        df = db.read_sql(f"""
            SELECT MIN(date) AS period_start, MAX(date) AS period_end,
                   SUM(gross_volume) AS gross_volume,
                   SUM(total_transactions) AS total_transactions,
                   AVG(avg_ticket) AS avg_ticket,
                   AVG(approval_rate) AS approval_rate,
                   AVG(fraud_rate) AS fraud_rate,
                   SUM(chargeback_count) AS chargebacks,
                   SUM(processing_fees) AS processing_fees,
                   SUM(net_volume) AS net_volume
            FROM gold.kpi_daily WHERE {where}
        """)
        r = df.iloc[0]
        if r["total_transactions"] is None:
            return "No KPI data available for that period."
        return (
            f"Period: {r['period_start']} -> {r['period_end']}\n"
            f"Gross Volume:  ${r['gross_volume']:,.2f}\n"
            f"Transactions:  {r['total_transactions']:,.0f}\n"
            f"Avg Ticket:    ${r['avg_ticket']:.2f}\n"
            f"Approval Rate: {r['approval_rate']:.2%}\n"
            f"Fraud Rate:    {r['fraud_rate']:.4%}\n"
            f"Chargebacks:   {r['chargebacks']:.0f}\n"
            f"Fees:          ${r['processing_fees']:,.2f}\n"
            f"Net Volume:    ${r['net_volume']:,.2f}"
        )
    except Exception as e:  # noqa: BLE001
        return f"Error: {e}"


TOOLS = [
    vector_search,
    sql_query,
    get_merchant_detail,
    explain_fraud_transaction,
    get_kpi_summary,
]


# ── ADK runner (lazy singletons) ─────────────────────────────────────────────

_runner = None
_session_service = None
_created_sessions: set[str] = set()


def _build_runner():
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    # LiteLLM reads OPENAI_API_KEY from the environment.
    if settings.OPENAI_API_KEY:
        os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    agent = Agent(
        name="payments_fraud_analyst",
        model=LiteLlm(model=settings.ADK_MODEL),   # "openai/gpt-4o"
        description="Payments fraud analyst over the Supabase gold/clean layers.",
        instruction=SYSTEM_PROMPT,
        tools=TOOLS,
    )
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    return runner, session_service


def _get_runner():
    global _runner, _session_service
    if _runner is None:
        _runner, _session_service = _build_runner()
    return _runner, _session_service


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


async def _ensure_session(session_service, session_id: str) -> None:
    if session_id in _created_sessions:
        return
    try:
        await _maybe_await(session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id,
        ))
    except Exception:  # already exists / signature differences across versions
        pass
    _created_sessions.add(session_id)


async def _arun(question: str, session_id: str) -> str:
    from google.genai import types

    runner, session_service = _get_runner()
    await _ensure_session(session_service, session_id)

    sanitized = sanitize_user_input(question)
    if sanitized.blocked:
        log.warning("blocked canary token in user input: %s", sanitized.canary_hits)
        return SAFE_REFUSAL

    message = types.Content(role="user", parts=[types.Part(text=sanitized.text)])
    final = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = event.content.parts[0].text or final
    validated = validate_assistant_output(final or "(no response)")
    if not validated.valid:
        log.warning("blocked canary token in assistant output: %s", validated.canary_hits)
    return validated.text


def ask(question: str, session_id: str = "dashboard", chat_history=None) -> str:
    """Ask the AI analyst a question. Multi-turn history is kept per session_id.

    chat_history is accepted for backward compatibility but ADK's session store
    already retains the conversation for a given session_id.
    """
    if not settings.OPENAI_API_KEY:
        return "OPENAI_API_KEY is not set — the AI Analyst is unavailable."
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_arun(question, session_id))
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001
        log.exception("agent run failed")
        return f"Agent error: {e}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(ask("Give me a KPI summary for the last 30 days"))
