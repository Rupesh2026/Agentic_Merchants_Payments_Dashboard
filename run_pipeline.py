#!/usr/bin/env python3
"""
run_pipeline.py — Master pipeline orchestrator.

Runs ETL (Spark) → ML (XGBoost + MLflow) → RAG (OpenAI embeddings) end to end
against Supabase. No Docker.

Usage:
    python run_pipeline.py                 # run all phases
    python run_pipeline.py --phase etl     # Bronze→Silver→Gold (Spark)
    python run_pipeline.py --phase ml      # train + evaluate + score
    python run_pipeline.py --phase rag     # embeddings + HNSW index
    python run_pipeline.py --skip-prereq   # skip prerequisite checks
"""

import argparse
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_log_fmt = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter(_log_fmt))
if hasattr(_stream_handler.stream, "reconfigure"):
    _stream_handler.stream.reconfigure(encoding="utf-8", errors="replace")
_file_handler = logging.FileHandler(
    f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(_log_fmt))
logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger("pipeline")


def run_etl():
    log.info("=" * 60)
    log.info("PHASE 2: ETL PIPELINE (pandas + psycopg2 -> local Postgres)")
    log.info("=" * 60)

    from etl.bronze.loader import load_bronze
    from etl.silver.cleaner import run_silver_clean
    from etl.silver.enricher import run_silver_enrich
    from etl.gold.features import run_feature_engineering
    from etl.gold.aggregations import run_aggregations

    steps = [
        ("Bronze: load CSVs → raw.transactions", load_bronze),
        ("Silver: clean → cleaned Delta", run_silver_clean),
        ("Silver: enrich → clean.transactions", run_silver_enrich),
        ("Gold: features → gold.features", run_feature_engineering),
        ("Gold: KPI aggregations", run_aggregations),
    ]
    for i, (label, fn) in enumerate(steps, 1):
        log.info("Step %d/%d — %s", i, len(steps), label)
        t0 = time.time()
        fn()
        log.info("  done in %.1fs", time.time() - t0)


def run_ml():
    log.info("=" * 60)
    log.info("PHASE 3: ML MODEL (XGBoost + SHAP + MLflow)")
    log.info("=" * 60)

    from ml.train import train_model
    from ml.evaluate import evaluate_model
    from ml.predict import batch_score
    from etl.gold.aggregations import run_aggregations

    log.info("Step 1/4 — Training XGBoost (MLflow tracked)")
    t0 = time.time(); artifact = train_model(); log.info("  done in %.1fs", time.time() - t0)

    log.info("Step 2/4 — Evaluating (ROC / PR / SHAP)")
    t0 = time.time(); evaluate_model(artifact); log.info("  done in %.1fs", time.time() - t0)

    log.info("Step 3/4 — Batch scoring → gold.risk_scores")
    t0 = time.time(); batch_score(artifact, force=True); log.info("  done in %.1fs", time.time() - t0)

    log.info("Step 4/4 — Refresh Gold aggregations with risk scores")
    t0 = time.time(); run_aggregations(); log.info("  done in %.1fs", time.time() - t0)


def run_rag():
    log.info("=" * 60)
    log.info("PHASE 4: RAG CORPUS (OpenAI embeddings → pgvector)")
    log.info("=" * 60)

    from rag.embeddings import build_embeddings, build_hnsw_index

    log.info("Step 1/2 — Generating + storing embeddings")
    t0 = time.time(); build_embeddings(); log.info("  done in %.1fs", time.time() - t0)

    log.info("Step 2/2 — Building HNSW index")
    t0 = time.time(); build_hnsw_index(); log.info("  done in %.1fs", time.time() - t0)


def check_prerequisites(phase: str):
    from config import settings, db

    errors, warnings = [], []

    # Data files (needed for ETL)
    if phase in ("etl", "all"):
        for fp in (settings.TRAIN_CSV, settings.TEST_CSV):
            if not fp.exists():
                errors.append(
                    f"Missing dataset: {fp}\n"
                    "  → Download from https://www.kaggle.com/datasets/kartik2112/fraud-detection\n"
                    "  → Place fraudTrain.csv / fraudTest.csv in data/raw/"
                )
            pass  # no Java/Spark needed — ETL uses pandas

    # Supabase reachability
    if db.ping():
        log.info("Supabase connection OK (%s)", settings.PG_HOST)
    else:
        errors.append(
            "Cannot reach Supabase Postgres.\n"
            "  → Set DATABASE_URL in .env (Session pooler string)\n"
            "  → Apply schema: python -m config.db --schema  (or paste config/schema.sql in the SQL Editor)"
        )

    # OpenAI key (needed for RAG)
    if phase in ("rag", "all") and not settings.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY not set in .env — required for embeddings + AI Analyst.")
    elif not settings.OPENAI_API_KEY:
        warnings.append("OPENAI_API_KEY not set — RAG phase will fail when reached.")

    for w in warnings:
        log.warning(w)
    if errors:
        log.error("Prerequisites not met:\n%s", "\n".join(errors))
        sys.exit(1)
    log.info("All prerequisites satisfied")


def main():
    parser = argparse.ArgumentParser(description="Payments Dashboard Pipeline")
    parser.add_argument("--phase", choices=["etl", "ml", "rag", "all"], default="all")
    parser.add_argument("--skip-prereq", action="store_true")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("PAYMENTS MERCHANT DASHBOARD — PIPELINE  (phase: %s)", args.phase.upper())
    log.info("=" * 60)

    if not args.skip_prereq:
        check_prerequisites(args.phase)

    start = time.time()
    if args.phase in ("etl", "all"):
        run_etl()
    if args.phase in ("ml", "all"):
        run_ml()
    if args.phase in ("rag", "all"):
        run_rag()

    log.info("=" * 60)
    log.info("Pipeline complete in %.1f min", (time.time() - start) / 60)
    log.info("Next: streamlit run dashboard/app.py   |   mlflow ui")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
