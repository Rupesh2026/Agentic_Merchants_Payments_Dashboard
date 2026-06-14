"""
etl/gold/aggregations.py — GOLD layer: KPI aggregations (pandas)

Reads clean.transactions (+ gold.risk_scores when available), builds all
gold.* dashboard tables. Safe to re-run — truncates before each write.
Called twice by the pipeline: after ETL (risk_scores empty) and after ML.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings, db

log = logging.getLogger(__name__)

FEE_RATES = {
    "Visa": 0.0215, "Mastercard": 0.0220, "Amex": 0.0350,
    "ACH": 0.0080, "Other": 0.0250,
}
INTERCHANGE_RATES = {
    "Visa": 0.0175, "Mastercard": 0.0, "Amex": 0.0, "ACH": 0.0, "Other": 0.0,
}
PROCESSING_RATES = {
    "Visa": 0.0040, "Mastercard": 0.0045, "Amex": 0.0100,
    "ACH": 0.0030, "Other": 0.0050,
}


def _write(df: pd.DataFrame, table: str, schema: str = "gold") -> None:
    db.execute(f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY CASCADE")
    db.bulk_insert(df, table, schema=schema, chunksize=2000)
    log.info("  %s.%s: %s rows", schema, table, f"{len(df):,}")


def _kpi_daily(ct: pd.DataFrame) -> pd.DataFrame:
    ct["date"] = pd.to_datetime(ct["trans_at"]).dt.date
    ct["cust_key"] = ct["city"].fillna("") + ct["state"].fillna("") + ct["gender"].fillna("")
    ct["fee"] = ct["amt"] * ct["card_network"].map(FEE_RATES).fillna(0.025)

    daily = ct.groupby("date").agg(
        gross_volume       =("amt",          "sum"),
        total_transactions =("trans_id",     "count"),
        avg_ticket         =("amt",          "mean"),
        approved_count     =("txn_status",   lambda x: (x == "approved").sum()),
        declined_count     =("txn_status",   lambda x: (x == "declined").sum()),
        fraud_count        =("is_fraud",     "sum"),
        chargeback_count   =("has_chargeback", "sum"),
        processing_fees    =("fee",          "sum"),
        unique_customers   =("cust_key",     "nunique"),
    ).reset_index()

    daily["approval_rate"] = daily["approved_count"] / daily["total_transactions"]
    daily["fraud_rate"]    = daily["fraud_count"]    / daily["total_transactions"]
    daily["net_volume"]    = daily["gross_volume"] - daily["processing_fees"]

    # top category per day
    top_cat = (ct.groupby(["date", "category"])["amt"].sum()
                 .reset_index()
                 .sort_values("amt", ascending=False)
                 .drop_duplicates("date")[["date", "category"]]
                 .rename(columns={"category": "top_category"}))
    daily = daily.merge(top_cat, on="date", how="left")

    # repeat customers
    multi_cust = (ct.groupby("cust_key")["trans_id"].count()
                    .loc[lambda s: s > 1].index)
    repeat = (ct[ct["cust_key"].isin(multi_cust)]
                .groupby("date")["cust_key"].nunique()
                .reset_index()
                .rename(columns={"cust_key": "repeat_customers"}))
    daily = daily.merge(repeat, on="date", how="left")
    daily["repeat_customers"] = daily["repeat_customers"].fillna(0).astype(int)

    return daily


def _merchant_stats(ct: pd.DataFrame, rs: pd.DataFrame) -> pd.DataFrame:
    ct = ct.merge(rs[["trans_id", "risk_score"]], on="trans_id", how="left")

    # Primary category = the one with the most transactions per merchant
    primary_cat = (
        ct.groupby(["merchant", "category"])["trans_id"].count()
          .reset_index()
          .sort_values("trans_id", ascending=False)
          .drop_duplicates("merchant")[["merchant", "category"]]
    )

    stats = ct.groupby("merchant").agg(
        total_volume      =("amt",            "sum"),
        total_transactions=("trans_id",       "count"),
        avg_ticket        =("amt",            "mean"),
        fraud_count       =("is_fraud",       "sum"),
        chargeback_count  =("has_chargeback", "sum"),
        risk_score_avg    =("risk_score",     "mean"),
        first_seen        =("trans_at",       lambda x: pd.to_datetime(x).dt.date.min()),
        last_seen         =("trans_at",       lambda x: pd.to_datetime(x).dt.date.max()),
        decline_count     =("txn_status",     lambda x: (x == "declined").sum()),
    ).reset_index()

    stats = stats.merge(primary_cat, on="merchant", how="left")
    stats["fraud_rate"]    = stats["fraud_count"]   / stats["total_transactions"]
    stats["approval_rate"] = 1 - (stats["decline_count"] / stats["total_transactions"])
    stats["risk_score_avg"] = stats["risk_score_avg"].fillna(0)
    return stats.drop(columns="decline_count")


def _category_stats(ct: pd.DataFrame) -> pd.DataFrame:
    grand = ct["amt"].sum()
    stats = ct.groupby("category").agg(
        total_volume      =("amt",        "sum"),
        total_transactions=("trans_id",   "count"),
        avg_ticket        =("amt",        "mean"),
        fraud_count       =("is_fraud",   "sum"),
    ).reset_index()
    stats["fraud_rate"]    = stats["fraud_count"]   / stats["total_transactions"]
    stats["approval_rate"] = ct.groupby("category")["txn_status"].apply(
        lambda x: (x == "approved").sum() / len(x)
    ).reindex(stats["category"]).values
    stats["pct_of_volume"] = stats["total_volume"] / grand
    return stats.drop(columns="fraud_count")


def _fraud_heatmap(ct: pd.DataFrame, rs: pd.DataFrame) -> pd.DataFrame:
    ct = ct.merge(rs[["trans_id", "risk_score"]], on="trans_id", how="left")
    ct["hour_of_day"] = pd.to_datetime(ct["trans_at"]).dt.hour.astype("int16")
    ct["day_of_week"] = pd.to_datetime(ct["trans_at"]).dt.dayofweek.astype("int16")
    hm = ct.groupby(["hour_of_day", "day_of_week"]).agg(
        total_transactions=("trans_id",   "count"),
        fraud_count       =("is_fraud",   "sum"),
        avg_risk_score    =("risk_score", "mean"),
    ).reset_index()
    hm["fraud_rate"]    = hm["fraud_count"]    / hm["total_transactions"]
    hm["avg_risk_score"] = hm["avg_risk_score"].fillna(0)
    return hm


def _state_stats(ct: pd.DataFrame) -> pd.DataFrame:
    ct = ct[ct["state"].notna()]
    stats = ct.groupby("state").agg(
        total_volume      =("amt",      "sum"),
        total_transactions=("trans_id", "count"),
        fraud_count       =("is_fraud", "sum"),
        avg_ticket        =("amt",      "mean"),
    ).reset_index()
    stats["fraud_rate"] = stats["fraud_count"] / stats["total_transactions"]
    return stats


def _payout_history(ct: pd.DataFrame) -> pd.DataFrame:
    approved = ct[ct["txn_status"] == "approved"].copy()
    approved = approved[approved["settlement_date"].notna()]
    approved["settlement_date"] = pd.to_datetime(approved["settlement_date"])
    approved["payout_week"] = approved["settlement_date"].dt.to_period("W").dt.start_time

    approved["interchange"] = approved["amt"] * approved["card_network"].map(INTERCHANGE_RATES).fillna(0)
    approved["processing"]  = approved["amt"] * approved["card_network"].map(PROCESSING_RATES).fillna(0.005)

    calc = approved.groupby("payout_week").agg(
        gross_amount     =("amt",          "sum"),
        transaction_count=("trans_id",     "count"),
        interchange_fee  =("interchange",  "sum"),
        processing_fee   =("processing",   "sum"),
    ).reset_index()
    calc["network_fee"] = calc["gross_amount"] * 0.0020
    calc["scheme_fee"]  = calc["gross_amount"] * 0.0008
    calc["net_payout"]  = (calc["gross_amount"]
                           - calc["interchange_fee"]
                           - calc["processing_fee"]
                           - calc["network_fee"]
                           - calc["scheme_fee"])
    calc = calc.rename(columns={"payout_week": "payout_date"})
    calc["payout_date"] = calc["payout_date"].dt.date
    return calc.sort_values("payout_date")


def run_aggregations() -> None:
    log.info("Reading clean.transactions ...")
    ct = db.read_sql("SELECT * FROM clean.transactions")
    log.info("  rows: %s", f"{len(ct):,}")

    ct["is_fraud"]       = ct["is_fraud"].astype(bool)
    ct["has_chargeback"] = ct["has_chargeback"].astype(bool)
    ct["amt"]            = pd.to_numeric(ct["amt"], errors="coerce")

    log.info("Reading gold.risk_scores ...")
    rs = db.read_sql("SELECT trans_id, risk_score FROM gold.risk_scores")
    log.info("  risk score rows: %s", f"{len(rs):,}")

    log.info("Building gold.kpi_daily ...")
    _write(_kpi_daily(ct.copy()), "kpi_daily")

    log.info("Building gold.merchant_stats ...")
    _write(_merchant_stats(ct.copy(), rs), "merchant_stats")

    log.info("Building gold.category_stats ...")
    _write(_category_stats(ct.copy()), "category_stats")

    log.info("Building gold.fraud_heatmap ...")
    _write(_fraud_heatmap(ct.copy(), rs), "fraud_heatmap")

    log.info("Building gold.state_stats ...")
    _write(_state_stats(ct.copy()), "state_stats")

    log.info("Building gold.payout_history ...")
    _write(_payout_history(ct.copy()), "payout_history")

    log.info("All Gold aggregations complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    run_aggregations()
