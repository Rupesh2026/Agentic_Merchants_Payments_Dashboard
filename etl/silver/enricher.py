"""
etl/silver/enricher.py — SILVER layer step 2: Faker enrichment (pandas)

Reads the cleaned Silver parquet written by cleaner.py, adds 10 synthetic
operational fields derived deterministically from trans_num (so the output
is reproducible), and writes the final clean.transactions to Supabase.

Distributions mirror config/settings.py:
  card_network  Visa .44 / MC .31 / Amex .12 / ACH .09 / Other .04
  txn_status    fraud → 8% flagged else approved; clean → 2.7% declined else approved
  decline_code  ISO-8583 weighted (51/05/14/41/43/59)
  auth_latency  Box-Muller normal by status, clipped 80-800 ms
  settlement    T+1/T+2/T+3 by network
  chargeback    8% of fraud rows, +30-90 days, weighted reason
"""

from __future__ import annotations

import hashlib
import logging
import math
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings, db

log = logging.getLogger(__name__)

CLEAN_COLUMNS = [
    "trans_id", "trans_num", "trans_at", "merchant", "category",
    "merch_lat", "merch_long", "amt", "is_fraud", "gender", "age_group",
    "city", "state", "city_pop", "job_category", "cust_lat", "cust_long",
    "card_network", "card_last4", "txn_status", "decline_code", "decline_reason",
    "auth_latency_ms", "settlement_date", "has_chargeback", "chargeback_date",
    "chargeback_reason", "source_file",
]


def _uhash_col(trans_nums: pd.Series, salt: str) -> np.ndarray:
    """Vectorized uniform [0,1) float derived deterministically from trans_num + salt."""
    def _h(x: str) -> float:
        b = hashlib.md5(f"{x}{salt}".encode()).digest()[:4]
        return struct.unpack(">I", b)[0] / 0x100000000
    return trans_nums.map(_h).to_numpy(dtype=float)


def _int_hash_col(trans_nums: pd.Series, salt: str) -> np.ndarray:
    """Vectorized unsigned 32-bit int hash."""
    def _h(x: str) -> int:
        b = hashlib.md5(f"{x}{salt}".encode()).digest()[:4]
        return struct.unpack(">I", b)[0]
    return trans_nums.map(_h).to_numpy(dtype=np.uint32)


def run_silver_enrich() -> int:
    parquet = settings.PROCESSED_DIR / "silver_clean.parquet"
    if not parquet.exists():
        raise FileNotFoundError(f"{parquet} not found — run run_silver_clean() first")

    log.info("Reading cleaned Silver parquet ...")
    df = pd.read_parquet(parquet)
    n = len(df)
    log.info("  rows: %s", f"{n:,}")

    tn = df["trans_num"]

    # ── Uniform random variates (deterministic per trans_num) ──────────────
    log.info("Computing deterministic enrichment fields ...")
    u_net      = _uhash_col(tn, "net")
    u_status   = _uhash_col(tn, "status")
    u_decline  = _uhash_col(tn, "decline")
    u_lat1     = np.clip(_uhash_col(tn, "lat1"), 1e-9, 1.0)
    u_lat2     = _uhash_col(tn, "lat2")
    u_settle   = _uhash_col(tn, "settle")
    u_cbflag   = _uhash_col(tn, "cbflag")
    u_cbdays   = _uhash_col(tn, "cbdays")
    u_cbreason = _uhash_col(tn, "cbreason")
    last4_num  = (_int_hash_col(tn, "last4") % 9000) + 1000

    # ── Card network ──────────────────────────────────────────────────────
    net = np.select(
        [u_net < 0.44, u_net < 0.75, u_net < 0.87, u_net < 0.96],
        ["Visa", "Mastercard", "Amex", "ACH"],
        default="Other",
    )
    df["card_network"] = net
    df["card_last4"]   = pd.Series(last4_num, dtype=str).str.zfill(4)

    # ── Transaction status ────────────────────────────────────────────────
    is_fraud = df["is_fraud"].to_numpy()
    status = np.where(
        is_fraud,
        np.where(u_status < 0.08, "flagged", "approved"),
        np.where(u_status < 0.027, "declined", "approved"),
    )
    df["txn_status"] = status

    # ── Decline code & reason ─────────────────────────────────────────────
    declined_mask = status == "declined"
    code = np.select(
        [u_decline < 0.38, u_decline < 0.62, u_decline < 0.78,
         u_decline < 0.87, u_decline < 0.92],
        ["51", "05", "14", "41", "43"],
        default="59",
    )
    reason = np.select(
        [u_decline < 0.38, u_decline < 0.62, u_decline < 0.78,
         u_decline < 0.87, u_decline < 0.92],
        ["Insufficient funds", "Do not honour", "Invalid card number",
         "Lost card", "Stolen card"],
        default="Suspected fraud",
    )
    df["decline_code"]   = np.where(declined_mask, code,   None)
    df["decline_reason"] = np.where(declined_mask, reason, None)

    # ── Auth latency (Box-Muller normal, clipped 80-800 ms) ───────────────
    means = np.select([status == "approved", status == "declined", status == "flagged"],
                      [180, 240, 160], default=180)
    stds  = np.select([status == "approved", status == "declined", status == "flagged"],
                      [30,  40,  20],  default=30)
    z = np.sqrt(-2.0 * np.log(u_lat1)) * np.cos(2.0 * math.pi * u_lat2)
    latency = np.clip(np.round(means + stds * z), 80, 800).astype(int)
    df["auth_latency_ms"] = latency

    # ── Settlement date (T+n by network) ─────────────────────────────────
    settle_days = np.select(
        [
            np.isin(net, ["Visa", "Mastercard"]) & (u_settle < 0.60),
            np.isin(net, ["Visa", "Mastercard"]) & (u_settle >= 0.60),
            (net == "Amex") & (u_settle < 0.50),
            (net == "Amex") & (u_settle >= 0.50),
            net == "ACH",
            u_settle < 0.50,
        ],
        [1, 2, 2, 3, 3, 2],
        default=3,
    )
    trans_date = pd.to_datetime(df["trans_at"]).dt.tz_localize(None).dt.normalize()
    df["settlement_date"] = trans_date + pd.to_timedelta(settle_days, unit="D")
    df["settlement_date"] = df["settlement_date"].dt.date

    # ── Chargeback ────────────────────────────────────────────────────────
    cb_mask = is_fraud & (u_cbflag < 0.08)
    df["has_chargeback"] = cb_mask

    cb_days = (30 + np.floor(u_cbdays * 61)).astype(int)
    cb_date = trans_date + pd.to_timedelta(cb_days, unit="D")
    df["chargeback_date"] = np.where(cb_mask, cb_date.dt.date.astype(object), None)

    cb_reason = np.select(
        [u_cbreason < 0.40, u_cbreason < 0.75, u_cbreason < 0.90],
        ["Unauthorized transaction", "Item not received", "Item not as described"],
        default="Duplicate charge",
    )
    df["chargeback_reason"] = np.where(cb_mask, cb_reason, None)

    # ── Stratified sample (Supabase free-tier disk limit) ────────────────
    sample_n = settings.SUPABASE_SAMPLE_ROWS
    if 0 < sample_n < n:
        log.info("Sampling %s/%s rows (stratified on is_fraud) for Supabase ...",
                 f"{sample_n:,}", f"{n:,}")
        fraud_mask = df["is_fraud"].astype(bool)
        keep_fraud = min(int(fraud_mask.sum()), int(sample_n * fraud_mask.sum() / n))
        keep_legit = sample_n - keep_fraud
        df = pd.concat([
            df[fraud_mask].sample(n=keep_fraud, random_state=42),
            df[~fraud_mask].sample(n=min(keep_legit, int((~fraud_mask).sum())), random_state=42),
        ]).sample(frac=1, random_state=42).reset_index(drop=True)
        n = len(df)
        log.info("  final sample: %s rows (fraud rate %.3f%%)",
                 f"{n:,}", df["is_fraud"].mean() * 100)

    # ── Write clean.transactions ──────────────────────────────────────────
    df = df[CLEAN_COLUMNS].copy()
    log.info("Truncating clean.transactions and writing %s rows ...", f"{n:,}")
    db.execute("TRUNCATE TABLE clean.transactions RESTART IDENTITY CASCADE")

    batch_size = 100_000
    for i in range(0, n, batch_size):
        batch = df.iloc[i: i + batch_size]
        db.bulk_insert(batch, "transactions", schema="clean", chunksize=5000)
        log.info("  wrote %s / %s", f"{min(i + batch_size, n):,}", f"{n:,}")

    log.info("Silver enrichment complete: %s rows in clean.transactions", f"{n:,}")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    run_silver_enrich()
