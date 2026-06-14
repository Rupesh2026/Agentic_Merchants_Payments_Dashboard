"""
etl/silver/cleaner.py — SILVER layer step 1: clean & conform (pandas)

Reads raw.transactions, applies typing/dedup/PII-drop/derivations, and
writes clean.transactions + clean.merchants to Supabase.
Enrichment (card_network, decline codes, etc.) runs in enricher.py next.
"""

from __future__ import annotations

import hashlib
import logging
import re
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings, db

log = logging.getLogger(__name__)

REF_DATE = pd.Timestamp("2020-12-31")

JOB_PATTERNS = [
    ("Technology",  r"engineer|developer|programmer|analyst|software|information technology|tech"),
    ("Healthcare",  r"doctor|nurse|medical|health|physician|therapist|dental"),
    ("Finance",     r"accountant|banker|financial|broker|trader|economist"),
    ("Education",   r"teacher|professor|lecturer|educator|instructor|tutor"),
    ("Legal",       r"lawyer|attorney|paralegal|judge|solicitor"),
    ("Management",  r"manager|director|executive|ceo|officer|administrator"),
    ("Service",     r"driver|clerk|assistant|worker|operator|technician"),
    ("Sales",       r"sales|marketing|representative|agent|consultant"),
    ("Creative",    r"designer|artist|writer|journalist|architect"),
]


def _make_trans_id(s: pd.Series) -> pd.Series:
    """Deterministic 64-bit surrogate key from trans_num (simulates xxhash64)."""
    def _h(x: str) -> int:
        b = hashlib.md5(x.encode()).digest()[:8]
        return abs(struct.unpack(">q", b)[0])
    return s.map(_h)


def _categorize_job(job: str | float) -> str:
    if not isinstance(job, str):
        return "Other"
    jl = job.lower()
    for cat, pattern in JOB_PATTERNS:
        if re.search(pattern, jl):
            return cat
    return "Other"


def _age_group(age: float) -> str:
    if pd.isna(age) or age < 18:
        return "Unknown"
    if age <= 25:
        return "18-25"
    if age <= 35:
        return "26-35"
    if age <= 50:
        return "36-50"
    if age <= 65:
        return "51-65"
    return "66+"


BRONZE_PARQUET = settings.PROCESSED_DIR / "bronze_raw.parquet"


def run_silver_clean() -> int:
    if not BRONZE_PARQUET.exists():
        raise FileNotFoundError(
            f"{BRONZE_PARQUET} not found — run load_bronze() first"
        )
    log.info("Reading Bronze parquet ...")
    df = pd.read_parquet(BRONZE_PARQUET)
    log.info("  raw rows: %s", f"{len(df):,}")

    # ── Dedup: keep first occurrence per trans_num ─────────────────────────
    df = df[df["trans_num"].notna() & df["amt"].notna()].copy()
    df["_sort_ts"] = pd.to_datetime(df["trans_date_trans_time"], errors="coerce")
    df = (df.sort_values("_sort_ts")
            .drop_duplicates(subset="trans_num", keep="first")
            .reset_index(drop=True))

    # ── Surrogate key ──────────────────────────────────────────────────────
    df["trans_id"] = _make_trans_id(df["trans_num"])

    # ── Timestamp ─────────────────────────────────────────────────────────
    df["trans_at"] = pd.to_datetime(df["trans_date_trans_time"], errors="coerce")
    df = df[df["trans_at"].notna()].copy()
    df["trans_at"] = df["trans_at"].dt.tz_localize("UTC")

    # ── Merchant: strip 'fraud_' prefix ───────────────────────────────────
    df["merchant"] = df["merchant"].str.replace(r"^fraud_", "", regex=True).str.strip()
    df = df[df["merchant"].notna() & df["category"].notna()].copy()

    # ── Geo coords ────────────────────────────────────────────────────────
    df["merch_lat"]  = pd.to_numeric(df["merch_lat"],  errors="coerce")
    df["merch_long"] = pd.to_numeric(df["merch_long"], errors="coerce")
    df["cust_lat"]   = pd.to_numeric(df["lat"],        errors="coerce")
    df["cust_long"]  = pd.to_numeric(df["long"],       errors="coerce")

    # ── Amount & fraud flag ───────────────────────────────────────────────
    df["amt"]      = pd.to_numeric(df["amt"], errors="coerce")
    df["is_fraud"] = df["is_fraud"].astype(str).str.strip().isin(["1", "1.0", "true", "True"])
    df = df[df["amt"].notna() & df["is_fraud"].notna()].copy()

    # ── Gender ────────────────────────────────────────────────────────────
    df["gender"] = df["gender"].str.upper().str.strip().str[:1]
    df.loc[~df["gender"].isin(["F", "M"]), "gender"] = None

    # ── Age group from dob ────────────────────────────────────────────────
    dob = pd.to_datetime(df["dob"], errors="coerce")
    age = (REF_DATE - dob).dt.days / 365.25
    df["age_group"] = age.map(_age_group)

    # ── City / state ──────────────────────────────────────────────────────
    df["city"]  = df["city"].str.title().str.strip()
    df["state"] = df["state"].str.upper().str.strip()

    # ── City pop ──────────────────────────────────────────────────────────
    df["city_pop"] = pd.to_numeric(df["city_pop"], errors="coerce").astype("Int64")

    # ── Job category ─────────────────────────────────────────────────────
    df["job_category"] = df["job"].map(_categorize_job)

    # ── Final column selection ────────────────────────────────────────────
    CLEAN_BASE = [
        "trans_id", "trans_num", "trans_at", "merchant", "category",
        "merch_lat", "merch_long", "amt", "is_fraud", "gender", "age_group",
        "city", "state", "city_pop", "job_category", "cust_lat", "cust_long",
        "source_file",
    ]
    df = df[CLEAN_BASE].copy()
    n = len(df)
    log.info("Silver cleaned rows: %s", f"{n:,}")

    # ── Write clean.merchants dimension ───────────────────────────────────
    log.info("Building clean.merchants ...")
    merchants = (
        df.groupby("merchant", as_index=False)
        .agg(category=("category", "first"),
             merch_lat=("merch_lat", "mean"),
             merch_long=("merch_long", "mean"))
        .rename(columns={"merchant": "merchant_name"})
    )
    db.execute("TRUNCATE TABLE clean.merchants RESTART IDENTITY CASCADE")
    db.bulk_insert(merchants, "merchants", schema="clean", chunksize=2000)
    log.info("  clean.merchants: %s unique merchants", f"{len(merchants):,}")

    # ── Persist cleaned base for enricher ─────────────────────────────────
    # Save to parquet so enricher doesn't re-read the raw table
    out = settings.PROCESSED_DIR / "silver_clean.parquet"
    df.to_parquet(out, index=False)
    log.info("Saved cleaned Silver to %s", out)

    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    run_silver_clean()
