# Payments Merchant Dashboard — Implementation Log

Complete record of every build step: what was built, what broke, and why each decision was made.

---

## What Is This Project?

This is a **production-grade Payments Merchant Dashboard** built as an interview demonstration. It simulates the kind of internal analytics platform that companies like Stripe, Square, or Adyen provide to their merchants — showing real-time transaction health, fraud risk, payout schedules, and an AI-powered analyst that answers questions in plain English.

The project was designed to demonstrate the full breadth of a modern data engineering stack in one cohesive product:

1. **Data engineering depth** — Medallion Architecture (Bronze → Silver → Gold) with a real ETL pipeline processing 1.85 million transactions
2. **Machine learning** — XGBoost fraud detection trained on the full dataset, with SHAP explainability bridging model scores to human language
3. **Agentic AI** — A RAG agent backed by pgvector semantic search and GPT-4o that answers natural language questions about any merchant or time period by querying the live database
4. **Dashboard UI** — A Stripe-style interactive frontend with a global merchant filter, row-level drill-in, cross-page navigation, and an embedded AI chat interface

---

## Why This Dataset?

### Dataset: Sparkov Credit Card Fraud Detection (Kaggle)
Source: https://www.kaggle.com/datasets/kartik2112/fraud-detection

The Sparkov dataset was chosen over alternatives (e.g., the MLG-ULB anonymised PCA dataset) for three specific reasons:

**1. Rich merchant and category context**
Sparkov contains real merchant names (e.g., `fraud_Johnston-Hamill`, stripped to `Johnston-Hamill`) and 14 transaction categories (`grocery_pos`, `online_retail`, `travel`, `gas_transport`, etc.). This makes meaningful per-merchant analytics possible — fraud rate per merchant, peer comparison by category, volume breakdowns — which is the core of a merchant dashboard. MLG-ULB has only 28 anonymous PCA features with no merchant context at all.

**2. Temporal richness**
Sparkov has actual timestamps (`trans_date_trans_time`) spanning January 2019 to December 2020. This enables:
- Daily/weekly/monthly KPI aggregation
- Time-of-day and day-of-week fraud heatmaps
- Velocity features (how many transactions in the last 1h / 24h)
- Rolling payout schedules
- Trend charts with real date axes

MLG-ULB has only seconds-elapsed timestamps — no absolute dates.

**3. Geographic data**
Customer and merchant lat/long coordinates allow computing Haversine distance as a fraud feature (unusually large cardholder-to-merchant distance is a strong fraud signal) and state-level geographic aggregation for the dashboard.

### Dataset Size
| File | Rows | Size |
|---|---|---|
| `fraudTrain.csv` | 1,296,675 | ~230 MB |
| `fraudTest.csv` | 555,719 | ~96 MB |
| **Combined** | **1,852,394** | **~326 MB** |

1.85 million rows is large enough to be a realistic data engineering problem (chunked reading, batch inserts, indexed queries) while still being processable on a laptop in under 90 minutes end-to-end.

### What Was Dropped From the Dataset
| Column | Reason dropped |
|---|---|
| `first`, `last` | PII — name not needed for any metric |
| `street`, `zip` | PII — city + state + lat/long sufficient |
| `cc_num` | PII — adds PCI-DSS scope, not needed; replaced with synthetic `card_last4` |
| `unix_time` | Redundant with `trans_date_trans_time` |

### What Was Added (Synthetic Enrichment)
The Kaggle dataset is purely transactional — it has no payment processing metadata. Ten operational fields were added synthetically to make the dashboard realistic:

| Field | Business purpose |
|---|---|
| `card_network` | Powers the fee-by-network breakdown and payout page |
| `txn_status` | Approved / declined / flagged — drives approval rate KPI |
| `decline_code` | ISO-8583 codes — makes the decline breakdown chart meaningful |
| `auth_latency_ms` | Processing performance metric |
| `settlement_date` | Drives the payout schedule (T+1 Visa, T+3 ACH) |
| `has_chargeback` | Chargeback count KPI on overview and fraud pages |
| `card_last4` | Realistic display without storing full card number |

All synthetic fields are generated **deterministically** from `trans_num` via MD5 seeding — the same transaction always gets the same enriched values regardless of how many times the pipeline is re-run.

---

## Business Problem Being Solved

A payments processor has 693 active merchants processing 1.85 million transactions over two years. The business needs:

1. **Portfolio health monitoring** — Is the overall approval rate trending down? Is fraud spiking in any category? How much did we pay out last week?

2. **Per-merchant drill-in** — Select any of 693 merchants and see their specific KPIs, fraud rate vs industry average, recent high-risk transactions, peer comparison within their category, and estimated payout.

3. **Fraud investigation** — Which transactions have the highest risk scores? What features drove that score? (SHAP explanation per transaction.) Which hours and days see the most fraud?

4. **Natural language Q&A** — A non-technical merchant should be able to ask "What are my top 3 fraud patterns this month?" and get a plain-English answer backed by live database queries.

---

## Architecture Overview

```
Raw CSVs (Kaggle)
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│  BRONZE LAYER  (data/processed/bronze_raw.parquet)       │
│  All columns, all rows, minimal cleaning                  │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│  SILVER LAYER  (clean.transactions in Postgres)          │
│  Typed, deduped, enriched with 10 synthetic fields        │
│  693 merchants in clean.merchants                         │
└────────────────────────────┬────────────────────────────┘
                             │
                ┌────────────┴──────────────┐
                ▼                           ▼
┌──────────────────────┐       ┌────────────────────────────┐
│  GOLD — ML FEATURES  │       │  GOLD — AGGREGATIONS       │
│  gold.features       │       │  gold.kpi_daily            │
│  19 engineered cols  │       │  gold.merchant_stats       │
└──────────┬───────────┘       │  gold.category_stats       │
           │                   │  gold.fraud_heatmap        │
           ▼                   │  gold.state_stats          │
┌──────────────────────┐       │  gold.payout_history       │
│  XGBoost Model       │       └──────────────┬─────────────┘
│  ROC-AUC: 0.9997     │                      │
│  SHAP explainer      │                      │
└──────────┬───────────┘                      │
           │                                  │
           ▼                                  │
┌──────────────────────┐                      │
│  gold.risk_scores    │◄─────────────────────┘
│  1.85M rows          │  (re-agg after scoring
│  prob + tier + SHAP  │   to get avg risk score)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│  RAG LAYER  (gold.embeddings — pgvector)                  │
│  693 merchant narratives + 90 daily reports               │
│  HNSW index (cosine, m=16)                                │
│  Google ADK agent → LiteLLM → GPT-4o                     │
│  5 tools: vector_search / sql_query / merchant_detail /   │
│           explain_fraud / kpi_summary                     │
└──────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────┐
│  STREAMLIT DASHBOARD  (dashboard/app.py)                  │
│  6 pages, global merchant filter, cross-page navigation   │
│  Row selection + SHAP panel, watchlist, CSV export        │
│  AI Analyst chat with merchant context injection          │
└──────────────────────────────────────────────────────────┘
```

---

## Validation at Each Layer

### Bronze
- Row count matches sum of both CSV files: 1,296,675 + 555,719 = 1,852,394
- No processing applied — used as a count baseline

### Silver Clean
- Dedup check: `trans_num` is unique (no duplicate transaction IDs in the output)
- `is_fraud` distribution preserved: ~0.58% fraud rate (same as source dataset)
- 693 distinct merchant names extracted and written to `clean.merchants`
- Null rates for key fields: `lat`, `long`, `city`, `state` all < 0.01%

### Silver Enrich
- `card_network` distribution matches target (Visa ~44%, MC ~31%, Amex ~12%, ACH ~9%)
- `txn_status` cross-check: `approved` rate ≈ 97.3% for non-fraud, ≈ 92% for fraud rows
- `has_chargeback` is always False when `is_fraud = False` (chargebacks only on fraud)
- Settlement dates are always after transaction dates

### Gold Features
- Velocity features: `tx_count_1h` max ≈ 8–12 per customer key (realistic for fraud rings)
- `geo_distance_km` range: 0–3,000 km (median ~50 km for local merchants)
- `amt_zscore` is centred at 0, std ~1 per customer key as expected

### ML Model
- ROC-AUC **0.9997** and PR-AUC **0.9806** — extremely high because Sparkov is a synthetic dataset with clean signal (real-world would be ~0.85 AUC)
- Recall (fraud) = **0.98** — catches 98% of fraudulent transactions
- Precision (fraud) = **0.73** — 27% false-positive rate is acceptable for a risk score (not a hard block)
- Top SHAP features: `geo_distance_km`, `tx_amount_24h`, `tx_count_24h`, `amt_zscore`, `merchant_fraud_rate` — all logically expected

### Gold Aggregations
- `gold.kpi_daily` spans exactly 730 days (2019-01-01 to 2020-12-31) — matches dataset dates
- `gold.merchant_stats` has exactly 693 rows matching `clean.merchants`
- `gold.payout_history` has 105 weekly rows (~730 days / 7)
- Portfolio fraud rate in `kpi_daily` matches source dataset's 0.58%

### RAG Embeddings
- 693 merchant vectors + 90 daily report vectors = 783 total in `gold.embeddings`
- HNSW index built with 0 errors; cosine similarity queries return in <5 ms

### Dashboard
- All 6 pages render without exceptions on a fresh `streamlit run`
- Merchant selector: switching between merchants correctly re-queries and re-renders all components
- Row selection: SHAP panel appears on row click; "Ask AI" cross-links route correctly
- AI Analyst: agent completes multi-step queries (vector search → SQL → synthesis) in 10–30 seconds

---

## Stack Decisions (Final)

| Concern | Choice | Why |
|---|---|---|
| Database | Local PostgreSQL 16 + pgvector (Docker) | Supabase free tier (500 MB) overflowed with 1.85 M rows; local Docker has no size limit |
| ETL engine | pandas + psycopg2 | PySpark requires Java; user cancelled Java install; pandas handles 1.85 M rows fine |
| LLM / embeddings | OpenAI gpt-4o + text-embedding-3-small | Specified in CLAUDE.md; gpt-4o is the best available for the agent reasoning tasks |
| Agent framework | Google ADK 1.4.2 via LiteLLM 1.88.1 | Specified in CLAUDE.md; LiteLLM bridges ADK to OpenAI's API |
| ML model | XGBoost + SHAP | Tabular fraud data, trains in ~3 min, industry standard, SHAP bridges to RAG explanation |
| Experiment tracking | MLflow 3.13.0 (SQLite backend) | File-store deprecated in MLflow 3.x; SQLite is zero-config |
| Dashboard | Streamlit 1.35 + Plotly | Ships fast, professional appearance, supports `on_select` row selection natively |

---

## Phase 1 — Infrastructure

### 1.1 Docker Compose (`docker-compose.yml`)
- Image: `pgvector/pgvector:pg16` — PostgreSQL 16 with pgvector pre-installed, no manual extension setup
- Port: `5433:5432` — avoids collision with any pre-existing local Postgres instance
- Volume: `payments_pgdata` — data persists across `docker compose down` / `up` cycles
- Healthcheck: `pg_isready` polling every 5s — downstream steps wait for a healthy DB

```bash
docker compose up -d
```

### 1.2 Environment (`.env`)
```
DATABASE_URL=postgresql://payments_user:payments_pass@localhost:5433/payments_db
SSLMODE=disable
OPENAI_API_KEY=<key>
MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db
MLFLOW_EXPERIMENT=payments-fraud-xgboost
```
`SSLMODE=disable` is required for the local Docker container; the same code works with `require` for any cloud Postgres.

### 1.3 Schema (`config/schema.sql`)
Applied via `db.apply_schema()`. Creates three schemas implementing the Medallion Architecture:

| Schema | Layer | Purpose |
|---|---|---|
| `raw` | Bronze | Append-only all-TEXT audit log — `raw.transactions` |
| `clean` | Silver | Typed, deduped, enriched data — `clean.transactions`, `clean.merchants` |
| `gold` | Gold | ML feature store + dashboard query layer — `gold.features`, `gold.risk_scores`, `gold.kpi_daily`, `gold.merchant_stats`, `gold.category_stats`, `gold.fraud_heatmap`, `gold.state_stats`, `gold.payout_history`, `gold.embeddings` |

Extensions enabled: `vector` (pgvector for cosine similarity search), `pg_trgm` (fuzzy text search).

### 1.4 DB Connection Layer (`config/db.py`)
- `get_connection()` — raw psycopg2 with `autocommit=True`; avoids `ReadOnlySqlTransaction` errors that affected the SQLAlchemy layer
- `bulk_insert()` — `psycopg2.extras.execute_values` for batch writes (10-100× faster than row-by-row)
- `read_sql()` — SQLAlchemy engine only for SELECT (pandas `read_sql` compatibility)
- SSL mode read from `SSLMODE` env var — makes the same codebase work locally and on any cloud Postgres

### 1.5 Settings (`config/settings.py`)
- `MLFLOW_TRACKING_URI` reads from env (was hardcoded `file:./mlruns`, deprecated in MLflow 3.x)
- `INDUSTRY_FRAUD_RATE = 0.0058` — benchmark for coloring fraud rate KPIs red/amber/green
- `CATEGORY_DISPLAY` — human-readable category name mapping for charts

---

## Phase 2 — ETL Pipeline

### 2.1 Bronze — `etl/bronze/loader.py`
- Reads `data/raw/fraudTrain.csv` + `data/raw/fraudTest.csv` in 50k chunks
- Drops trivial PII columns that add no analytical value: `first`, `last`, `street`, `zip`, `cc_num`, `unix_time`
- Saves to `data/processed/bronze_raw.parquet` rather than writing to `raw.transactions` in Postgres
  - **Why:** The all-TEXT raw table for 1.85 M rows would be ~400 MB; local parquet is faster to iterate on
- Output: 1,852,394 rows

### 2.2 Silver Clean — `etl/silver/cleaner.py`
Reads `bronze_raw.parquet`, applies the full cleaning pipeline:

| Transform | Detail |
|---|---|
| Dedup | Keep first occurrence per `trans_num` (sort by timestamp) |
| Surrogate key | `trans_id` = deterministic 64-bit MD5 hash of `trans_num` |
| Timestamps | Parse `trans_date_trans_time` → `trans_at` (UTC datetime) |
| Merchant | Strip `fraud_` prefix added by the Kaggle dataset generator |
| Geo coords | Cast lat/long to float; drop rows with NaN coords |
| `is_fraud` | Cast from "0"/"1"/"true"/"false" strings to bool |
| Gender | Normalize to "M"/"F"; unknown → None |
| Age group | Bin from `dob` relative to dataset end date 2020-12-31 |
| City/state | Title-case city, uppercase state |
| Job category | Regex-bucket 100+ job titles into 9 groups |

Writes:
- `data/processed/silver_clean.parquet` — local fast path for ML
- `clean.merchants` — 693 unique merchant records

### 2.3 Silver Enrich — `etl/silver/enricher.py`
Adds 10 synthetic operational fields that the Kaggle dataset lacks. All fields are generated **deterministically** from `trans_num` via MD5 seeding — the same transaction always gets the same enriched values, making the pipeline reproducible.

| Field | Logic |
|---|---|
| `card_network` | Visa 44%, MC 31%, Amex 12%, ACH 9%, Other 4% |
| `card_last4` | 4-digit string 1000–9999 |
| `txn_status` | Fraud txns → 8% flagged, rest approved; legit → 2.7% declined, rest approved |
| `decline_code` | ISO-8583 weighted distribution (51/05/14/41/43/59) |
| `decline_reason` | Human-readable text matching the ISO code |
| `auth_latency_ms` | Box-Muller normal by status, clipped 80–800 ms |
| `settlement_date` | T+1/T+2/T+3 by card network (Visa=T+1, ACH=T+3) |
| `has_chargeback` | 8% of confirmed fraud rows |
| `chargeback_date` | Transaction date + 30–90 days |
| `chargeback_reason` | Weighted (unauthorized / not received / not as described / duplicate) |

Writes `clean.transactions` — 1,852,394 rows in 100k batches.

**Bug fixed:** `pd.array(...).astype(str).str.zfill(4)` — numpy array has no `.str` accessor. Fixed to `pd.Series(last4_num, dtype=str).str.zfill(4)`.

### 2.4 Gold Features — `etl/gold/features.py`
Reads `clean.transactions` (1,852,394 rows), engineers 19 ML features across 5 groups:

| Group | Features | Why |
|---|---|---|
| Temporal | `hour_of_day`, `day_of_week`, `is_weekend`, `month` | Fraud spikes at night and weekends |
| Geographic | `geo_distance_km` (Haversine), `city_pop_log`, `is_rural` | Large cardholder-to-merchant distance signals fraud |
| Velocity | `tx_count_1h`, `tx_count_24h`, `tx_amount_1h`, `tx_amount_24h` | Rapid-fire transactions are the #1 fraud signal |
| Amount | `amt_zscore` (per customer key) | Unusually large purchase relative to customer baseline |
| Category + demographics | `category_encoded`, `is_online`, `gender_encoded`, `age_group_encoded` | High-risk categories (online retail, travel) |
| Historical rates | `merchant_fraud_rate`, `category_fraud_rate` | Prior fraud probability for this merchant / category |

Velocity windows computed per `cust_key = city + state + gender` (966 unique keys) — a privacy-safe proxy for card identity (no card number stored).

Writes `gold.features` — 1,852,394 rows.

### 2.5 Gold Aggregations — `etl/gold/aggregations.py`
Builds the dashboard query layer from `clean.transactions` + (optionally) `gold.risk_scores`:

| Table | Rows | Content |
|---|---|---|
| `gold.kpi_daily` | 730 | Daily gross volume, transactions, approval rate, fraud rate, processing fees, net volume, chargebacks, top category |
| `gold.merchant_stats` | 693 | Per-merchant: total volume, transactions, avg ticket, fraud rate, fraud count, chargeback count, approval rate, avg risk score |
| `gold.category_stats` | 14 | Per-category: volume, transactions, avg ticket, fraud rate, approval rate, % of total |
| `gold.fraud_heatmap` | 168 | Fraud rate by hour (0–23) × day of week (0–6) — 24×7 grid |
| `gold.state_stats` | 51 | Per-state: volume, transactions, fraud count, fraud rate, avg ticket |
| `gold.payout_history` | 105 | Weekly payout with fee breakdown: interchange (1.5%), processing (0.35%), network (0.2%), scheme (0.1%) |

Fee rates are model rates chosen to reflect real-world interchange economics for a demo.

**Bug fixed:** `_merchant_stats` grouped by `(merchant, category)` — multiple categories per merchant caused duplicate PK on `merchant`. Fixed: group by `merchant` only, pick the primary category by transaction count (mode).

---

## Phase 3 — ML Model

### 3.1 Training — `ml/train.py`
- Loads `gold.features` (1,852,394 rows, 19 features)
- 80/20 stratified split — preserves the ~0.58% fraud rate in both sets
- `scale_pos_weight` computed dynamically from training data: `(y_train==0).sum() / (y_train==1).sum()` ≈ 190
  - **Why dynamic:** Hardcoding 578 (full-dataset ratio) was wrong for the 80% training split
- XGBoost params: 500 trees, `max_depth=6`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `tree_method=hist` (GPU-optional)

**Results:**
| Metric | Value |
|---|---|
| ROC-AUC | **0.9997** |
| PR-AUC | **0.9806** |
| Precision (Fraud) | 0.73 |
| Recall (Fraud) | 0.98 |
| F1 (Fraud) | 0.84 |
| Accuracy | 0.998 |

Model artifact: `ml/artifacts/xgb_fraud.pkl`. Logged to MLflow experiment `payments-fraud-xgboost`.

### 3.2 Evaluation — `ml/evaluate.py`
Saves four plots to `ml/artifacts/`:
- `roc_curve.png` — AUC-ROC
- `pr_curve.png` — Precision-Recall (more informative for imbalanced data)
- `confusion_matrix.png` — counts at 0.5 threshold
- `shap_summary.png` — SHAP beeswarm on 5k sample, shows feature importance ranking

### 3.3 Batch Scoring — `ml/predict.py`
For every transaction:
1. `XGBClassifier.predict_proba` → `fraud_probability`
2. `risk_score = int(prob × 100)` clipped 0–100
3. `risk_tier`: critical ≥90, high ≥70, medium ≥30, low <30
4. SHAP `TreeExplainer` → top-3 features with human-readable explanation text and signed SHAP values (positive = increases fraud risk)
5. UPSERT into `gold.risk_scores` on `trans_id`

Throughput: ~100k rows per 2.5 minutes. All 1,852,394 transactions scored.

**Bug fixed:** Replaced `db.get_engine().raw_connection()` (SQLAlchemy) with `db.get_connection()` (direct psycopg2, `autocommit=True`). Removed manual `conn.commit()` calls that conflicted with autocommit mode.

### 3.4 Gold Re-aggregation
After scoring, aggregations run a second time so `gold.merchant_stats.risk_score_avg` and `gold.fraud_heatmap.avg_risk_score` reflect actual ML-derived scores instead of nulls.

---

## Phase 4 — RAG Agent

### 4.1 Embeddings — `rag/embeddings.py`
- For each of 693 merchants: `gpt-4o` generates a 150-word risk narrative summarising volume, fraud rate, top risk factors; then `text-embedding-3-small` embeds it to `vector(1536)`
- For the last 90 days in `gold.kpi_daily`: generates a daily report text and embeds it
- All stored in `gold.embeddings` with `doc_type`, `doc_id`, and content metadata
- HNSW index built after insertion: `m=16, ef_construction=64`, cosine distance operator `<=>`, for sub-millisecond ANN search at 783 vectors

**Results:** 693 merchant + 90 daily report embeddings. HNSW index built in 0.4 s. Total RAG phase: ~19.5 min (OpenAI API rate-limited).

**Bug fixed:** Replaced `db.get_engine().raw_connection()` with `db.get_connection()` in both `_insert_batch()` and `build_hnsw_index()` — same autocommit fix as scoring phase.

### 4.2 Retriever — `rag/retriever.py`
- Embed query with `text-embedding-3-small`
- pgvector cosine similarity: `embedding <=> CAST(:qvec AS vector) ORDER BY ... LIMIT k`
- Returns top-k documents with similarity scores; used by the agent's `vector_search` tool

### 4.3 Agent — `rag/agent.py`
Google ADK agent (`InMemoryRunner`) routing via LiteLLM → OpenAI `gpt-4o`. The agent has 5 registered tools:

| Tool | Purpose |
|---|---|
| `vector_search` | Semantic search over merchant narratives and daily reports |
| `sql_query` | Read-only `SELECT` on gold/clean schemas; returns JSON rows |
| `get_merchant_detail` | Full merchant stats + risk profile from `gold.merchant_stats` |
| `explain_fraud_transaction` | SHAP breakdown for a specific `trans_num` |
| `get_kpi_summary` | Portfolio KPIs for a named time window (today/7d/30d/mtd) |

### 4.4 System Prompt (`rag/prompts.py`)
The system prompt includes:
- Complete Gold schema reference with exact table and column names (prevents hallucinated table names like `gold.payouts`)
- **Date anchoring rule:** "NEVER use `CURRENT_DATE`, `NOW()`. Dataset covers Jan 2019–Dec 2020. Always anchor to `(SELECT MAX(date) FROM gold.kpi_daily)`." Without this, the agent produced empty results for every time-window query because no data exists in 2025/2026.

### 4.5 Dependency Fixes for google-adk + LiteLLM + OpenAI

Three separate dependency conflicts were encountered and resolved:

| Error | Root Cause | Fix |
|---|---|---|
| `No module named 'deprecated'` | `google-adk` depends on the `deprecated` package but does not declare it | `pip install deprecated==1.3.1 wrapt==2.2.1` |
| `cannot import name 'ChatCompletionDeveloperMessage' from 'litellm'` | `litellm` 1.55.x is too old; google-adk internal imports need 1.67+ | `pip install "litellm>=1.88.1"` (also upgraded openai 1.x → 2.x) |
| `Failed to parse parameter query: 'str' of function vector_search` | `google-adk` 1.0.0 incompatible with openai v2's type schema system for automatic function calling | `pip install "google-adk==1.4.2"` |

**Working version matrix** (pinned in `requirements.txt`):
```
openai==2.41.1
litellm==1.88.1
google-adk==1.4.2
deprecated==1.3.1
wrapt==2.2.1
```

---

## Phase 5 — Dashboard

### 5.1 Architecture

**Entry point:** `dashboard/app.py` — runs `st.set_page_config`, injects all CSS, renders the sidebar, routes to the active view.

**Views directory:** `dashboard/views/` (renamed from `dashboard/pages/` to prevent Streamlit's auto-detection of the `pages/` convention, which was generating a duplicate auto-nav sidebar on top of the custom radio nav).

**Navigation pattern:** `st.session_state["page"]` holds the current page name string. `st.radio` in the sidebar controls it. Any view can navigate by setting `st.session_state["page"] = "Target"` then calling `st.rerun()`. This gives full SPA-like navigation without URL changes.

**Global merchant filter:** `st.session_state["selected_merchant"]` is set by a sidebar selectbox populated from `gold.merchant_stats` (693 options + "All Merchants"). Every view reads this and branches into either merchant-specific or portfolio mode. The AI Analyst prepends `[Context: focusing on merchant 'X']` to every query when a merchant is selected.

### 5.2 Pages

| Page | File | What it shows |
|---|---|---|
| Overview | `views/overview.py` | KPI summary cards with navigation buttons, revenue + fraud trend chart, top categories donut, recent transactions table |
| Transactions | `views/transactions.py` | Filter bar (category/state/status/risk tier/min amount), selectable table with SHAP detail panel on row click, CSV export |
| Performance | `views/performance.py` | Revenue trend, approval/fraud rate trends, category volume breakdown, state volume bars, demographics chart, peer comparison table |
| Fraud & Risk | `views/fraud.py` | Fraud heatmap (hour × day), risk score histogram, merchant watchlist panel, top fraud transactions with SHAP inline, watchlist toggle |
| Payouts | `views/payouts.py` | Weekly payout bar chart, fee mix donut, fee-by-network bar, payout detail table, next payout estimate, CSV export |
| AI Analyst | `views/ai_analyst.py` | GPT-4o + pgvector RAG chat UI, merchant-aware quick prompts, cross-page prefill from "Ask AI" buttons |

### 5.3 Data Layer (`dashboard/data.py`)

All query functions use `@st.cache_data(ttl=300)` to avoid re-querying on every Streamlit rerun. Key merchant-aware functions added:

```python
merchant_list()          # 693 merchants for sidebar selectbox
merchant_card(merchant)  # Single-merchant stats from gold.merchant_stats
merchant_kpi_daily(m)    # Daily KPIs computed live from clean.transactions WHERE merchant=m
transaction_detail(tn)   # Full detail + SHAP from clean.transactions JOIN gold.risk_scores
```

`recent_transactions()`, `transactions()`, and `top_fraud_transactions()` all accept an optional `merchant` parameter that adds a `WHERE merchant = :m` clause.

### 5.4 Row Selection + SHAP Panel

Uses Streamlit 1.35's native `st.dataframe(on_select="rerun", selection_mode="single-row")`. When a row is selected, the view calls `transaction_detail(trans_num)` to fetch `gold.risk_scores.top_shap_features` (stored as JSON), then renders each factor as:

- Red arrow (↑) + explanation text for positive SHAP values (increases fraud risk)
- Green arrow (↓) + explanation text for negative SHAP values (decreases fraud risk)

This bridges the ML model (XGBoost SHAP) to human language without requiring the RAG agent for every explanation.

### 5.5 Cross-Page "Ask AI" Buttons

Any page can deep-link to the AI Analyst with a pre-filled question by setting:
```python
st.session_state["page"] = "AI Analyst"
st.session_state["ai_prefill"] = "Analyze fraud patterns for merchant 'X'..."
st.rerun()
```
The AI Analyst view checks `st.session_state.get("ai_prefill")` on load and submits it automatically.

### 5.6 Watchlist

`st.session_state.setdefault("watchlist", set())` — a session-scoped set of merchant names. Any page can add/remove merchants. The Fraud & Risk page renders a watchlist panel showing KPI cards for each watched merchant, with one-click drill-in. The sidebar shows a "Watching N merchants" pill when the watchlist is non-empty.

---

## Phase 6 — UI Polish (Sidebar Redesign)

### Problem
The original sidebar had two issues:
1. **Invisible selectbox text** — `[data-testid="stSidebar"] * { color: #c9d1d9 !important }` wildcard applied light text colour to ALL sidebar elements, including the selected value inside selectbox components. Selectbox value text renders inside a light-background Baseui component outside the sidebar's background scope → white text on white background.
2. **Dark theme inconsistency** — sidebar was `#0f1117` (near-black) while the main canvas was `#f7f8fa` (off-white), making the UI feel like two separate products.

### Solution
Complete sidebar CSS rewrite to a light theme that matches the main canvas:

| Element | Before | After |
|---|---|---|
| Sidebar background | `#0f1117` (near-black) | `#ffffff` (white) |
| Sidebar border | `#1c1f26` | `#e2e8f0` |
| Nav items | Left-border-only active indicator, no border on inactive | **Bordered cards** — `#f8fafc` bg + `#e2e8f0` border on all items; active = `#eef2ff` bg + `#a5b4fc` border + `#3730a3` bold text |
| Selectbox | Dark (`#1c1f26` bg, light text) | Light (`#f8fafc` bg, `#1a202c` text, `#cbd5e1` border) |
| Dropdown popup | `color: inherit` (inherited dark, invisible) | Explicit `#1a202c` text, `#f8fafc` hover, `#eef2ff` selected — always readable |
| Section labels | `#4a5568` | `#94a3b8` (softer, subordinate to nav) |
| Brand mark | Purple circle dot | Indigo square accent (`border-radius: 2px`) |
| Merchant badge | Dark card `#1c1f26` | Light card `#f8fafc` with `#e2e8f0` border |

The wildcard `* { color: inherit }` is kept (not removed) so Streamlit's own components stay inheritable, but no `!important` light-on-dark rule is applied. Selectbox components get their own specific rules that explicitly set `color: #1a202c` on just the `[data-baseweb="select"]` subtree.

### Navigation Label Cleanup
Removed emoji prefixes from all page names. Old: `"📊 Overview"`, `"🤖 AI Analyst"`, etc. New: `"Overview"`, `"AI Analyst"`, etc. All `st.session_state["page"]` assignments across all 6 view files updated to match.

---

## All Bugs Fixed (Chronological)

| # | Error | Fix |
|---|---|---|
| 1 | `numpy.int64 can't adapt` in psycopg2 | Added `_native()` helper: `.item()` for numpy scalars before batch insert |
| 2 | `ReadOnlySqlTransaction` via SQLAlchemy | Rewrote `db.py` to use direct psycopg2 with `autocommit=True` throughout |
| 3 | Supabase disk full (1007 MB > 500 MB limit) | Switched to local Docker Postgres |
| 4 | `pd.array(...).str.zfill` AttributeError | Changed to `pd.Series(last4_num, dtype=str).str.zfill(4)` |
| 5 | `duplicate key on merchant_stats` | Changed GROUP BY from `(merchant, category)` to `merchant` only |
| 6 | `mlflow ImportError: google.protobuf.service` | Upgraded MLflow 2.14.1 → 3.13.0 |
| 7 | `MLflow file-store maintenance mode` | Switched tracking URI to `sqlite:///mlruns/mlflow.db` |
| 8 | `UnicodeEncodeError cp1252` in logging | Set `encoding='utf-8'` on file log handler |
| 9 | SSL error on local Docker Postgres | Added `SSLMODE=disable` env var; made sslmode configurable |
| 10 | `scale_pos_weight` wrong for 80% split | Compute dynamically from `y_train` (≈190) instead of hardcoded 578 |
| 11 | `No module named 'deprecated'` (google-adk) | `pip install deprecated==1.3.1 wrapt==2.2.1` |
| 12 | `cannot import 'ChatCompletionDeveloperMessage'` | `pip install "litellm>=1.88.1"` (also upgraded openai 1.x → 2.41.1) |
| 13 | `Failed to parse parameter 'query': 'str'` | `pip install "google-adk==1.4.2"` |
| 14 | Agent returned empty results for date queries | System prompt: never use `CURRENT_DATE`; always anchor to `MAX(date)` from data |
| 15 | Agent used `gold.payouts` (nonexistent table) | Added full schema reference to `SYSTEM_PROMPT` in `rag/prompts.py` |
| 16 | Duplicate nav sidebar (radio + auto-generated) | Renamed `dashboard/pages/` → `dashboard/views/` to bypass Streamlit auto-detection |
| 17 | Port 8501 conflict on restart | `Stop-Process` on `Get-NetTCPConnection -LocalPort 8501` to kill stale Streamlit |
| 18 | Invisible dropdown text (selectbox in sidebar) | Replaced wildcard `* { color: light }` with targeted `[data-baseweb="select"] *` rule and explicit `[data-baseweb="popover"]` rules |
| 19 | Stale emoji page names in views after nav rename | Updated all `st.session_state["page"] = "📊 Overview"` etc. to plain-text names |

---

## How to Run (from scratch)

```bash
# 1. Start Postgres
docker compose up -d

# 2. Set up Python env
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# 3. Copy and fill in env vars
copy .env.example .env       # then add your OPENAI_API_KEY

# 4. Apply schema
python -c "from config.db import apply_schema; apply_schema()"

# 5. Full pipeline (ETL → ML → RAG) — ~75 min total
python run_pipeline.py

# 6. Launch dashboard
.venv\Scripts\streamlit.exe run dashboard/app.py

# Optional: view MLflow experiment runs
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db
```

---

## Current Status

| Phase | Status | Notes |
|---|---|---|
| Infrastructure (Docker + schema) | DONE | pgvector HNSW index created |
| Bronze ETL | DONE | 1,852,394 rows → parquet |
| Silver Clean | DONE | Dedup, type cast, enrichment fields |
| Silver Enrich | DONE | 10 synthetic fields, deterministic seeding |
| Gold Features | DONE | 19 ML features, velocity windows |
| Gold Aggregations (pre-ML) | DONE | 6 gold tables |
| ML Training | DONE | ROC-AUC 0.9997, PR-AUC 0.9806 |
| ML Evaluation | DONE | 4 plots in `ml/artifacts/` |
| ML Batch Scoring | DONE | All 1,852,394 rows scored + SHAP |
| Gold Re-aggregation (post-ML) | DONE | Risk scores reflected in merchant stats |
| RAG Embeddings | DONE | 693 merchant + 90 daily report vectors |
| HNSW Index | DONE | m=16, ef=64, cosine, 0.4 s build time |
| RAG Agent | DONE | 5 tools, GPT-4o, date-anchored SQL |
| Dashboard — 6 pages | DONE | All merchant-aware with cross-page nav |
| Dashboard — merchant selector | DONE | 693 options, flows into all pages + RAG |
| Dashboard — row selection + SHAP | DONE | Streamlit `on_select="rerun"` |
| Dashboard — CSV export | DONE | Transactions + payouts |
| Dashboard — watchlist | DONE | Session-scoped, fraud page + sidebar pill |
| Dashboard — AI cross-links | DONE | "Ask AI" buttons on all pages |
| Sidebar — light theme | DONE | White bg, dark text, bordered nav cards |
| Sidebar — dropdown visibility | DONE | Explicit CSS for selectbox + popover |
