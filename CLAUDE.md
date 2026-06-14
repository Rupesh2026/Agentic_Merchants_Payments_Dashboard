# CLAUDE.md — Payments Merchant Dashboard
## Master Instructions for Claude Code

> ### ⚠️ AUTHORITATIVE STACK OVERRIDE (2026-06-12)
> The project was re-platformed per the user's `/goal`. Where this file or
> `docs/` disagree, **these decisions win** (see `README.md` for the run guide):
> - **Serving DB:** Supabase (Postgres + pgvector) — **no Docker, no local Postgres**.
> - **ETL engine:** **PySpark 3.5 + Spark SQL + Delta Lake** (not pandas). SQL in `sql/`.
> - **LLM provider:** **OpenAI only** (gpt-4o + text-embedding-3-small) — **no Anthropic/Claude**.
> - **Agent framework:** **Google ADK** (`google-adk`) via LiteLLM → OpenAI.
> - **Experiment tracking:** **MLflow**.
> - Data lives in `data/raw/` (already downloaded). Connection/keys come from `.env`.

This file is the single source of truth for building this project.
Read this file, then `docs/architecture.md`, then `docs/agents.md` before writing any code.

---

## What You Are Building

A **production-grade payments merchant dashboard** for an interview demo that shows:
1. Full **Medallion Architecture ETL pipeline** (Bronze → Silver → Gold) in PostgreSQL
2. **Traditional ML** fraud detection model (XGBoost) with SHAP explainability
3. **Agentic RAG** workflow (Claude API + pgvector) for natural language merchant analytics
4. A **Stripe-style dashboard UI** (Streamlit) showing performance, transaction health, fraud, payouts, and AI analyst

The stack is: Python · PostgreSQL · pgvector · XGBoost · scikit-learn · SHAP · LangChain · Claude API · Streamlit · Plotly

---

## Project Structure

```
payments-dashboard/
├── CLAUDE.md                    ← You are here. Read first.
├── docs/
│   ├── architecture.md          ← System design, data flow, DB schema
│   └── agents.md                ← RAG agent design, tools, prompts
├── data/
│   ├── raw/                     ← Downloaded Kaggle CSVs go here (gitignored)
│   │   ├── fraudTrain.csv       ← Sparkov training set (~1.29M rows)
│   │   └── fraudTest.csv        ← Sparkov test set (~555K rows)
│   └── processed/               ← Intermediate outputs (gitignored)
├── config/
│   ├── settings.py              ← All env vars, DB URLs, API keys
│   └── schema.sql               ← Full PostgreSQL schema DDL
├── sql/
│   ├── bronze_views.sql         ← Raw schema views
│   ├── silver_transforms.sql    ← Cleaning queries
│   └── gold_aggregations.sql    ← Feature + KPI queries
├── etl/
│   ├── __init__.py
│   ├── bronze/
│   │   ├── __init__.py
│   │   └── loader.py            ← CSV → raw schema in Postgres
│   ├── silver/
│   │   ├── __init__.py
│   │   ├── cleaner.py           ← Dedup, type cast, null handling
│   │   └── enricher.py          ← Faker enrichment (decline codes etc)
│   └── gold/
│       ├── __init__.py
│       ├── features.py          ← ML feature engineering
│       └── aggregations.py     ← KPI aggregation tables
├── ml/
│   ├── __init__.py
│   ├── train.py                 ← XGBoost training pipeline
│   ├── predict.py               ← Batch scoring → gold.risk_scores
│   ├── evaluate.py              ← Metrics, confusion matrix, ROC
│   └── features.py              ← Feature list + SHAP explainer
├── rag/
│   ├── __init__.py
│   ├── embeddings.py            ← Generate + store pgvector embeddings
│   ├── retriever.py             ← Similarity search against pgvector
│   ├── agent.py                 ← LangChain agentic RAG loop
│   └── prompts.py               ← All system + user prompt templates
├── dashboard/
│   ├── app.py                   ← Streamlit entry point
│   ├── pages/
│   │   ├── 01_overview.py       ← KPI summary page
│   │   ├── 02_transactions.py   ← Transaction explorer
│   │   ├── 03_performance.py    ← Revenue + category analytics
│   │   ├── 04_fraud.py          ← Fraud & risk page
│   │   ├── 05_payouts.py        ← Payout + fee breakdown
│   │   └── 06_ai_analyst.py     ← RAG chat interface
│   └── components/
│       ├── kpi_cards.py         ← Reusable KPI card components
│       ├── charts.py            ← Plotly chart builders
│       └── tables.py            ← Styled dataframe components
├── requirements.txt
├── .env.example
├── docker-compose.yml           ← PostgreSQL + pgvector
└── run_pipeline.py              ← Single script to run full pipeline
```

---

## Build Order — Follow This Exactly

### Phase 1 — Infrastructure
1. `docker-compose.yml` — PostgreSQL 15 with pgvector extension
2. `config/settings.py` — env vars, DB connection string
3. `config/schema.sql` — all table DDL (raw, clean, gold schemas)
4. Run `docker-compose up -d` and `psql < config/schema.sql`

### Phase 2 — ETL Pipeline
5. `etl/bronze/loader.py` — load CSVs into `raw.transactions`
6. `etl/silver/cleaner.py` — clean into `clean.transactions`
7. `etl/silver/enricher.py` — add Faker fields into `clean.transactions_enriched`
8. `etl/gold/features.py` — engineer ML features into `gold.features`
9. `etl/gold/aggregations.py` — build KPI views in `gold.*`

### Phase 3 — ML Model
10. `ml/features.py` — define feature columns
11. `ml/train.py` — train XGBoost, save model artifact
12. `ml/predict.py` — score all transactions, write `gold.risk_scores`
13. `ml/evaluate.py` — print metrics, save ROC/SHAP plots

### Phase 4 — RAG Agent
14. `rag/embeddings.py` — generate embeddings, insert into `gold.embeddings`
15. `rag/retriever.py` — pgvector cosine similarity search
16. `rag/agent.py` — LangChain agent with tools
17. `rag/prompts.py` — all prompt templates

### Phase 5 — Dashboard
18. `dashboard/components/` — kpi_cards, charts, tables
19. `dashboard/pages/` — all 6 pages
20. `dashboard/app.py` — entry point, navigation, sidebar

### Phase 6 — Orchestration
21. `run_pipeline.py` — runs phases 2→3→4 in sequence with logging

---

## Dataset Setup

### Download (do this before running any code)
1. Go to: https://www.kaggle.com/datasets/kartik2112/fraud-detection
2. Download `fraudTrain.csv` and `fraudTest.csv`
3. Place both files in `data/raw/`

### File sizes
- `fraudTrain.csv` — ~230MB, 1,296,675 rows, 23 columns
- `fraudTest.csv` — ~96MB, 555,719 rows, 23 columns
- Combined: ~1.85M transactions

### Columns in the dataset
```
trans_date_trans_time, cc_num, merchant, category, amt,
first, last, gender, street, city, state, zip,
lat, long, city_pop, job, dob, trans_num,
unix_time, merch_lat, merch_long, is_fraud
```

### Columns to DROP (PII / unnecessary)
- `first`, `last`, `street`, `zip`, `cc_num` — PII, not needed
- `unix_time` — redundant with trans_date_trans_time

### Columns to USE
All remaining 16 columns — see `docs/architecture.md` for full mapping

---

## Environment Variables

Create a `.env` file from `.env.example`:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=payments_db
POSTGRES_USER=payments_user
POSTGRES_PASSWORD=payments_pass
ANTHROPIC_API_KEY=your_key_here
EMBEDDING_MODEL=text-embedding-3-small
```

---

## Key Design Decisions

### Why Sparkov only (no MLG-ULB)
Sparkov has real timestamps, merchant names, 14 categories, and geo coordinates.
MLG-ULB has only PCA features — no merchant context. Sparkov alone is sufficient.

### Why drop cc_num
We agreed not to include card numbers or BINs — not needed for any dashboard metric,
adds PCI-DSS scope concerns, and weakens the demo story. Use `card_network` (Faker) instead.

### Why XGBoost not deep learning
1.85M rows, tabular data, interview setting — XGBoost is the right tool.
Trains in ~3 minutes, highly interpretable with SHAP, industry standard for fraud.

### Why pgvector not Pinecone/Weaviate
Keeps everything in one database. pgvector on PostgreSQL is production-grade,
demonstrates data engineering depth, and simplifies the demo setup.

### Why Streamlit not React
Interview demo — Streamlit ships in hours, looks professional, supports Plotly natively.
Mention React + FastAPI as the production replacement during the interview.

---

## Running the Full Pipeline

```bash
# 1. Start Postgres
docker-compose up -d

# 2. Create schema
psql -U payments_user -d payments_db -f config/schema.sql

# 3. Run full ETL + ML + RAG pipeline
python run_pipeline.py

# 4. Launch dashboard
streamlit run dashboard/app.py
```

---

## Interview Talking Points (remind the interviewer of these)

1. **Medallion architecture** separates raw ingest from business logic — raw schema is append-only audit log
2. **Faker enrichment** is explicit and isolated in `silver/enricher.py` — easy to swap for real data
3. **Gold layer** serves dual purpose: ML feature store AND dashboard query layer
4. **pgvector** keeps the RAG corpus in the same DB as transactional data — one connection, one backup
5. **SHAP values** bridge the ML model and the RAG agent — the agent can explain model decisions in plain English
6. **XGBoost + RAG** is the right combination: XGBoost for real-time low-latency scoring, LLM for retrospective analysis and natural language Q&A
