"""
dashboard/data.py — cached Supabase queries shared by all dashboard pages.

Every page reads through these helpers so there is a single connection path
(config.db → Supabase, TLS). Results are cached for 5 minutes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import db


def _q(sql: str, params: dict | None = None) -> pd.DataFrame:
    return db.read_sql(sql, params or {})


@st.cache_data(ttl=300, show_spinner=False)
def has_data() -> bool:
    try:
        n = _q("SELECT COUNT(*) AS c FROM gold.kpi_daily").iloc[0]["c"]
        return int(n) > 0
    except Exception:
        return False


@st.cache_data(ttl=300, show_spinner=False)
def kpi_daily(days: int = 30) -> pd.DataFrame:
    return _q(
        "SELECT * FROM gold.kpi_daily ORDER BY date DESC LIMIT :n", {"n": days}
    )


@st.cache_data(ttl=300, show_spinner=False)
def kpi_all() -> pd.DataFrame:
    return _q("SELECT * FROM gold.kpi_daily ORDER BY date")


@st.cache_data(ttl=300, show_spinner=False)
def category_stats() -> pd.DataFrame:
    return _q("SELECT * FROM gold.category_stats ORDER BY total_volume DESC")


@st.cache_data(ttl=300, show_spinner=False)
def merchant_stats(order_by: str = "total_volume", limit: int = 15) -> pd.DataFrame:
    order_by = order_by if order_by in {"total_volume", "fraud_rate", "risk_score_avg"} else "total_volume"
    return _q(
        f"SELECT * FROM gold.merchant_stats ORDER BY {order_by} DESC NULLS LAST LIMIT :n",
        {"n": limit},
    )


@st.cache_data(ttl=300, show_spinner=False)
def state_stats() -> pd.DataFrame:
    return _q("SELECT * FROM gold.state_stats ORDER BY total_volume DESC")


@st.cache_data(ttl=300, show_spinner=False)
def fraud_heatmap() -> pd.DataFrame:
    return _q("SELECT * FROM gold.fraud_heatmap")


@st.cache_data(ttl=300, show_spinner=False)
def payout_history() -> pd.DataFrame:
    return _q("SELECT * FROM gold.payout_history ORDER BY payout_date")


@st.cache_data(ttl=300, show_spinner=False)
def recent_transactions(limit: int = 15, merchant: str = "") -> pd.DataFrame:
    where = "AND ct.merchant = :m" if merchant and merchant != "All Merchants" else ""
    return _q(
        f"""
        SELECT ct.trans_num, ct.merchant, ct.category, ct.amt, ct.txn_status,
               ct.trans_at, ct.card_network, rs.risk_score, rs.risk_tier
        FROM clean.transactions ct
        LEFT JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
        WHERE TRUE {where}
        ORDER BY ct.trans_at DESC
        LIMIT :n
        """,
        {"n": limit, "m": merchant or ""},
    )


@st.cache_data(ttl=300, show_spinner=False)
def filter_options() -> dict:
    cats = _q("SELECT DISTINCT category FROM clean.transactions ORDER BY 1")["category"].tolist()
    states = _q("SELECT DISTINCT state FROM clean.transactions WHERE state IS NOT NULL ORDER BY 1")["state"].tolist()
    nets = _q("SELECT DISTINCT card_network FROM clean.transactions ORDER BY 1")["card_network"].tolist()
    return {"categories": cats, "states": states, "networks": nets}


@st.cache_data(ttl=120, show_spinner=False)
def transactions(
    category: str = "", state: str = "", status: str = "",
    risk_tier: str = "", min_amt: float = 0.0, limit: int = 200,
    merchant: str = "",
) -> pd.DataFrame:
    clauses, params = ["TRUE"], {"min_amt": min_amt, "n": limit}
    if category:
        clauses.append("ct.category = :category"); params["category"] = category
    if state:
        clauses.append("ct.state = :state"); params["state"] = state
    if status:
        clauses.append("ct.txn_status = :status"); params["status"] = status
    if risk_tier:
        clauses.append("rs.risk_tier = :risk_tier"); params["risk_tier"] = risk_tier
    if merchant and merchant != "All Merchants":
        clauses.append("ct.merchant = :merchant"); params["merchant"] = merchant
    where = " AND ".join(clauses)
    return _q(
        f"""
        SELECT ct.trans_num, ct.trans_at, ct.merchant, ct.category, ct.amt,
               ct.state, ct.card_network, ct.txn_status, ct.is_fraud,
               rs.risk_score, rs.risk_tier
        FROM clean.transactions ct
        LEFT JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
        WHERE {where} AND ct.amt >= :min_amt
        ORDER BY ct.trans_at DESC
        LIMIT :n
        """,
        params,
    )


@st.cache_data(ttl=300, show_spinner=False)
def risk_distribution() -> pd.DataFrame:
    return _q("SELECT risk_score, risk_tier FROM gold.risk_scores")


@st.cache_data(ttl=300, show_spinner=False)
def top_fraud_transactions(limit: int = 50, merchant: str = "") -> pd.DataFrame:
    where = "AND ct.merchant = :m" if merchant and merchant != "All Merchants" else ""
    return _q(
        f"""
        SELECT ct.trans_num, ct.trans_at, ct.merchant, ct.category, ct.amt,
               ct.city, ct.state, rs.risk_score, rs.risk_tier, rs.fraud_probability
        FROM clean.transactions ct
        JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
        WHERE ct.is_fraud = TRUE {where}
        ORDER BY rs.risk_score DESC
        LIMIT :n
        """,
        {"n": limit, "m": merchant or ""},
    )


@st.cache_data(ttl=300, show_spinner=False)
def demographics() -> pd.DataFrame:
    return _q(
        """
        SELECT age_group, gender, COUNT(*) AS tx, SUM(amt) AS volume
        FROM clean.transactions
        GROUP BY age_group, gender
        ORDER BY age_group, gender
        """
    )


@st.cache_data(ttl=300, show_spinner=False)
def merchant_list() -> pd.DataFrame:
    """All merchants with summary stats, sorted by name."""
    return _q(
        """SELECT merchant, category, total_volume, total_transactions,
                  fraud_rate, risk_score_avg, approval_rate
           FROM gold.merchant_stats ORDER BY merchant"""
    )


@st.cache_data(ttl=300, show_spinner=False)
def merchant_card(merchant: str) -> pd.DataFrame:
    return _q("SELECT * FROM gold.merchant_stats WHERE merchant = :m", {"m": merchant})


@st.cache_data(ttl=300, show_spinner=False)
def merchant_kpi_daily(merchant: str) -> pd.DataFrame:
    return _q(
        """
        SELECT DATE(trans_at) AS date,
               SUM(amt) AS gross_volume,
               COUNT(*) AS total_transactions,
               AVG(amt) AS avg_ticket,
               SUM(CASE WHEN txn_status = 'approved' THEN 1 ELSE 0 END)::float / COUNT(*) AS approval_rate,
               SUM(CASE WHEN is_fraud = TRUE THEN 1 ELSE 0 END)::float / COUNT(*) AS fraud_rate,
               SUM(CASE WHEN has_chargeback = TRUE THEN 1 ELSE 0 END) AS chargeback_count
        FROM clean.transactions
        WHERE merchant = :m
        GROUP BY DATE(trans_at) ORDER BY date
        """,
        {"m": merchant},
    )


@st.cache_data(ttl=60, show_spinner=False)
def transaction_detail(trans_num: str) -> dict | None:
    df = _q(
        """
        SELECT ct.trans_num, ct.merchant, ct.category, ct.amt, ct.trans_at,
               ct.city, ct.state, ct.card_network, ct.txn_status, ct.is_fraud,
               ct.age_group, ct.gender, ct.has_chargeback,
               rs.risk_score, rs.fraud_probability, rs.risk_tier, rs.top_shap_features
        FROM clean.transactions ct
        LEFT JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
        WHERE ct.trans_num = :tn LIMIT 1
        """,
        {"tn": trans_num},
    )
    return None if df.empty else df.iloc[0].to_dict()


@st.cache_data(ttl=300, show_spinner=False)
def merchant_fraud_txns(merchant: str, limit: int = 50) -> pd.DataFrame:
    return _q(
        """
        SELECT ct.trans_num, ct.trans_at, ct.amt, ct.city, ct.state,
               ct.card_network, ct.txn_status, ct.has_chargeback,
               rs.risk_score, rs.risk_tier, rs.fraud_probability
        FROM clean.transactions ct
        LEFT JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id
        WHERE ct.merchant = :m AND ct.is_fraud = TRUE
        ORDER BY rs.risk_score DESC NULLS LAST LIMIT :n
        """,
        {"m": merchant, "n": limit},
    )


@st.cache_data(ttl=300, show_spinner=False)
def fee_by_network() -> pd.DataFrame:
    return _q(
        """
        SELECT card_network,
               COUNT(*) AS tx,
               SUM(amt) AS volume,
               SUM(amt * CASE card_network
                            WHEN 'Visa'       THEN 0.0215
                            WHEN 'Mastercard' THEN 0.0220
                            WHEN 'Amex'       THEN 0.0350
                            WHEN 'ACH'        THEN 0.0080
                            ELSE 0.0250 END) AS fees
        FROM clean.transactions
        GROUP BY card_network
        ORDER BY volume DESC
        """
    )


@st.cache_data(ttl=300, show_spinner=False)
def merchant_payout_weekly(merchant: str) -> pd.DataFrame:
    """Weekly payout breakdown for one merchant using the same fee rates as the portfolio."""
    return _q(
        """
        SELECT
            DATE_TRUNC('week', trans_at)::date AS payout_date,
            SUM(amt) AS gross_amount,
            SUM(amt * CASE card_network
                WHEN 'Visa'       THEN 0.0150
                WHEN 'Mastercard' THEN 0.0160
                WHEN 'Amex'       THEN 0.0270
                WHEN 'ACH'        THEN 0.0050
                ELSE 0.0165 END) AS interchange_fee,
            SUM(amt * 0.0030) AS processing_fee,
            SUM(amt * 0.0013) AS network_fee,
            SUM(amt * 0.0005) AS scheme_fee,
            SUM(amt * (1.0 - (
                CASE card_network
                    WHEN 'Visa'       THEN 0.0150
                    WHEN 'Mastercard' THEN 0.0160
                    WHEN 'Amex'       THEN 0.0270
                    WHEN 'ACH'        THEN 0.0050
                    ELSE 0.0165 END
                + 0.0030 + 0.0013 + 0.0005
            ))) AS net_payout,
            COUNT(*) AS transaction_count
        FROM clean.transactions
        WHERE merchant = :m AND txn_status = 'approved'
        GROUP BY DATE_TRUNC('week', trans_at)::date
        ORDER BY payout_date
        """,
        {"m": merchant},
    )


@st.cache_data(ttl=300, show_spinner=False)
def merchant_fee_by_network(merchant: str) -> pd.DataFrame:
    return _q(
        """
        SELECT card_network,
               COUNT(*) AS tx,
               SUM(amt) AS volume,
               SUM(amt * CASE card_network
                            WHEN 'Visa'       THEN 0.0215
                            WHEN 'Mastercard' THEN 0.0220
                            WHEN 'Amex'       THEN 0.0350
                            WHEN 'ACH'        THEN 0.0080
                            ELSE 0.0250 END) AS fees
        FROM clean.transactions
        WHERE merchant = :m AND txn_status = 'approved'
        GROUP BY card_network
        ORDER BY volume DESC
        """,
        {"m": merchant},
    )
