# Payments Merchant Dashboard

An open-source payments analytics demo that combines:

- a medallion-style data pipeline
- fraud detection with XGBoost and SHAP
- a retrieval-backed AI analyst
- a Streamlit dashboard for merchant and portfolio analysis

The project is designed so another engineer can clone it, run it locally, and build on top of the same database, feature tables, and UI patterns.

## What This Project Does

- Ingests the Sparkov credit card fraud dataset from `data/raw/`
- Cleans and enriches the raw data into a `clean.transactions` table
- Builds Gold-layer feature and KPI tables for analytics and modeling
- Trains an XGBoost fraud model and stores evaluation artifacts in MLflow
- Scores all transactions into `gold.risk_scores`
- Generates OpenAI embeddings for merchant and KPI narratives
- Serves a Streamlit dashboard with merchant drill-down, fraud analysis, payouts, and an AI analyst chat

## Architecture

```text
fraudTrain.csv + fraudTest.csv
        |
        v
Bronze: data/processed/bronze_raw.parquet
        |
        v
Silver clean: clean.transactions, clean.merchants
        |
        v
Silver enrich: synthetic card and payment metadata
        |
        v
Gold features: gold.features
Gold analytics: gold.kpi_daily, gold.merchant_stats, gold.category_stats,
                gold.fraud_heatmap, gold.state_stats, gold.payout_history
        |
        +--> ML: XGBoost -> SHAP -> gold.risk_scores
        |
        +--> RAG: OpenAI embeddings -> gold.embeddings
        |
        v
Streamlit dashboard + AI Analyst
```

## Tech Stack

- Python
- pandas
- PostgreSQL
- pgvector
- Streamlit
- Plotly
- XGBoost
- SHAP
- MLflow
- OpenAI
- Google ADK

## Repository Layout

```text
config/      Environment settings, database helpers, schema.sql
data/        Raw CSVs and processed parquet outputs
dashboard/   Streamlit app, data access helpers, page views, components
etl/         Bronze, Silver, and Gold transformation steps
ml/          Model training, evaluation, scoring, and feature helpers
rag/         Embeddings, retrieval, prompts, and agent tools
sql/         SQL transform scripts used by the data pipeline
run_pipeline.py
docker-compose.yml
```

## Requirements

- Python 3.11 or 3.12
- PostgreSQL 15+ or 16+
- Docker Desktop if you want the local database container
- An OpenAI API key for embeddings and the AI Analyst

## Quick Start

### 1. Start the database

For local development, use the included PostgreSQL container:

```bash
docker compose up -d
```

The compose file exposes Postgres on `localhost:5433`.

### 2. Create a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and set the values for your environment.

If you are using the local Docker database, set:

```env
DATABASE_URL=postgresql://payments_user:payments_pass@localhost:5433/payments_db
SSLMODE=disable
OPENAI_API_KEY=your_key_here
MLFLOW_TRACKING_URI=file:./mlruns
MLFLOW_EXPERIMENT=payments-fraud-xgboost
```

If you are using a managed Postgres instance, set `DATABASE_URL` to that connection string instead.

### 4. Apply the database schema

```bash
python -m config.db --schema
```

This creates the `raw`, `clean`, and `gold` schemas plus the tables and indexes used by the app.
The current Bronze step writes to `data/processed/bronze_raw.parquet`; the `raw.transactions` table is defined in the schema for teams that want to load Bronze into Postgres as well.

### 5. Make sure the dataset is available

Place these files in `data/raw/`:

- `fraudTrain.csv`
- `fraudTest.csv`

If they are missing, download the Sparkov fraud dataset from Kaggle and copy the CSVs into that folder.

### 6. Run the pipeline

```bash
python run_pipeline.py
```

You can also run phases independently:

```bash
python run_pipeline.py --phase etl
python run_pipeline.py --phase ml
python run_pipeline.py --phase rag
```

The pipeline performs:

- ETL into Bronze, Silver, and Gold tables
- model training and evaluation
- batch scoring into `gold.risk_scores`
- embedding generation into `gold.embeddings`

### 7. Launch the apps

```bash
streamlit run dashboard/app.py
mlflow ui
```

The dashboard runs on `http://localhost:8501`.
MLflow runs on `http://localhost:5000`.

## Pipeline Phases

### ETL

The ETL flow is implemented in `etl/` and is intentionally easy to extend:

- `etl/bronze/loader.py` reads the raw CSVs and writes a Bronze parquet audit file
- `etl/silver/cleaner.py` standardizes types, drops PII, de-duplicates rows, and builds `clean.merchants`
- `etl/silver/enricher.py` adds deterministic synthetic payment fields such as card network, status, decline codes, auth latency, settlement date, and chargebacks
- `etl/gold/features.py` creates the model feature store in `gold.features`
- `etl/gold/aggregations.py` builds the dashboard tables in `gold.*`

### ML

The ML flow in `ml/`:

- trains an XGBoost classifier on `gold.features`
- logs metrics and artifacts to MLflow
- writes ROC, PR, confusion matrix, and SHAP plots to `ml/artifacts/`
- scores all transactions into `gold.risk_scores`

### RAG

The RAG flow in `rag/`:

- generates embeddings for merchant and KPI narratives
- stores vectors in `gold.embeddings`
- exposes a Google ADK agent with tools for SQL, semantic search, merchant detail, fraud explanation, and KPI summaries

## Dashboard Pages

The Streamlit app in `dashboard/app.py` routes to six views:

- Overview
- Transactions
- Performance
- Fraud and Risk
- Payouts
- AI Analyst

Shared data access lives in `dashboard/data.py`, and reusable UI pieces live in `dashboard/components/`.

## How To Extend The Project

### Add a new database field

- Update `config/schema.sql`
- Update the relevant ETL step in `etl/`
- Add the column to the dashboard query helpers in `dashboard/data.py`
- Surface it in one or more dashboard views

### Add a new dashboard page

- Create a new file in `dashboard/views/`
- Register it in the sidebar routing in `dashboard/app.py`
- Add any new queries to `dashboard/data.py`

### Add a new model feature

- Add the feature to `etl/gold/features.py`
- Update `config/settings.py` if the feature should be part of the ML feature list
- Retrain the model with `python run_pipeline.py --phase ml`

### Add a new AI Analyst tool

- Implement the tool in `rag/agent.py`
- Add any prompt guidance in `rag/prompts.py`
- Keep the tool read-only unless you are intentionally changing the app behavior

## Data Model

The main data assets are:

- `data/processed/bronze_raw.parquet` for Bronze data
- `raw.transactions` for teams that choose to persist Bronze in Postgres
- `clean.transactions` and `clean.merchants` for the cleaned Silver layer
- `gold.features` for the model feature store
- `gold.risk_scores` for model predictions and SHAP explanations
- `gold.kpi_daily`, `gold.merchant_stats`, `gold.category_stats`, `gold.fraud_heatmap`, `gold.state_stats`, `gold.payout_history` for dashboard analytics
- `gold.embeddings` for the vector corpus used by the AI Analyst

## Outputs Worth Knowing

- `data/processed/bronze_raw.parquet`
- `data/processed/silver_clean.parquet`
- `ml/artifacts/xgb_fraud.pkl`
- `ml/artifacts/roc_curve.png`
- `ml/artifacts/pr_curve.png`
- `ml/artifacts/confusion_matrix.png`
- `ml/artifacts/shap_summary.png`
- `mlruns/` for MLflow runs

## Troubleshooting

- If the pipeline cannot connect to the database, confirm `DATABASE_URL` and `SSLMODE`
- If the dashboard shows no data, make sure `python run_pipeline.py` completed successfully
- If the AI Analyst fails, confirm `OPENAI_API_KEY` is set
- If you use the local Docker database, remember it listens on port `5433`
- If you already have a Postgres server on your machine, you can point `DATABASE_URL` to it instead of using Docker

## Notes For Contributors

- The codebase is intentionally modular so each layer can be changed independently
- `config/settings.py` is the best place to inspect env-driven behavior and defaults
- `config/schema.sql` is the source of truth for the database schema
- The current pipeline is built to be reproducible and rerunnable, so most steps truncate and rebuild their target tables

## License

Add the license you want to publish with before pushing the repository public.
