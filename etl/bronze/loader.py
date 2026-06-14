"""
etl/bronze/loader.py — BRONZE layer (pandas, local only)

Reads raw Kaggle CSVs in chunks and saves a local parquet as the
Bronze audit log. Does NOT write to Supabase — raw.transactions is
kept empty to save disk space on the free tier.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings

log = logging.getLogger(__name__)

RAW_COLUMNS = [
    "trans_date_trans_time", "cc_num", "merchant", "category", "amt",
    "first", "last", "gender", "street", "city", "state", "zip",
    "lat", "long", "city_pop", "job", "dob", "trans_num",
    "unix_time", "merch_lat", "merch_long", "is_fraud",
]

BRONZE_PARQUET = settings.PROCESSED_DIR / "bronze_raw.parquet"


def load_bronze() -> int:
    for fp in (settings.TRAIN_CSV, settings.TEST_CSV):
        if not fp.exists():
            raise FileNotFoundError(
                f"{fp} not found.\n"
                "Download from https://www.kaggle.com/datasets/kartik2112/fraud-detection\n"
                "and place fraudTrain.csv / fraudTest.csv in data/raw/"
            )

    chunks = []
    total = 0
    for fp, source_name in [(settings.TRAIN_CSV, "fraudTrain.csv"),
                             (settings.TEST_CSV,  "fraudTest.csv")]:
        log.info("Reading %s ...", fp.name)
        file_rows = 0
        for chunk in pd.read_csv(fp, chunksize=settings.CHUNK_SIZE,
                                  dtype=str, index_col=0):
            present = [c for c in RAW_COLUMNS if c in chunk.columns]
            chunk = chunk[present].copy()
            chunk["source_file"] = source_name
            chunks.append(chunk)
            file_rows += len(chunk)
        log.info("  %s: %s rows", source_name, f"{file_rows:,}")
        total += file_rows

    log.info("Saving Bronze parquet → %s", BRONZE_PARQUET)
    bronze = pd.concat(chunks, ignore_index=True)
    bronze.to_parquet(BRONZE_PARQUET, index=False)
    log.info("Bronze complete: %s rows saved locally (Supabase raw table stays empty)", f"{total:,}")
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    load_bronze()
