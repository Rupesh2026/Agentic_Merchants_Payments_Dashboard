# Agentic Payments Merchant Dashboard

> A production-style payments intelligence platform that turns 1.85 million raw credit card transactions into actionable decisions — for fraud analysts, merchant success teams, and portfolio managers — through an AI-powered Streamlit dashboard.

---

## The Problem This Project Solves

Payments teams process millions of transactions daily, but turning that raw data into operational decisions is hard in practice:

**Problem 1 — Charts without investigation**
Traditional dashboards show "fraud spiked on Tuesday" but give no path to find *which* merchant, *which* transactions, or *why*. Analysts write manual SQL queries, copy results to spreadsheets, and investigate in isolation.

**Problem 2 — Black-box ML models**
Most fraud models output a score with no explanation. When a merchant asks "why was my customer declined?" or a compliance officer asks "why did the model flag this transaction?", there's no answer to give.

**Problem 3 — Non-technical users locked out**
Merchant success managers, risk officers, and business leadership need answers like "Which merchants should I be worried about this week?" or "What changed in my payout last month?" — but they can't write SQL, and they can't wait for an analyst to run a report.

**Problem 4 — Fraud and business metrics are siloed**
Revenue, approval rates, fraud rates, and payout health live in separate tools. Connecting them requires manual joins and coordination between teams.

### What This Dashboard Delivers

One unified interface where:
- A **fraud analyst** can see exactly why each suspicious transaction was flagged, drill into SHAP feature explanations, and ask the AI analyst follow-up questions in plain English
- A **merchant success manager** can open any of the 693 merchants, see their performance vs industry peers, track their fraud exposure, and understand their payout breakdown — without SQL
- A **portfolio manager** can see real-time KPIs (gross volume, approval rate, fraud rate, chargebacks) across 1.85M transactions and receive an alert if any metric breaches industry thresholds
- A **business operator** can ask "Why did revenue drop last Thursday?" and get a data-backed answer in seconds instead of filing an analytics request

---

## How It Helps Analysts and Merchants Make Decisions

### Fraud Analysts

| Decision | How This Dashboard Supports It |
|---|---|
| Is this transaction actually fraudulent? | Risk score (0–100) + top 3 SHAP feature explanations per transaction |
| Which transactions to investigate first? | Sorted fraud table by risk score; filter by tier (High ≥70, Critical ≥90) |
| Is a merchant being targeted by fraud rings? | Per-merchant fraud rate vs 0.58% industry baseline; chargeback count; avg risk score |
| When does fraud most often happen? | Fraud heatmap: hour × day-of-week grid — darker cells = higher fraud rate |
| What pattern drove this week's fraud spike? | Ask the AI Analyst: "What are the top fraud patterns in the last 30 days?" |
| Should I escalate a merchant to the risk team? | Add merchant to Watchlist; "Ask AI about this merchant's fraud patterns" → plain-English risk summary |

### Merchant Success Teams

| Decision | How This Dashboard Supports It |
|---|---|
| Is this merchant's fraud rate acceptable? | Merchant profile banner: "Fraud 1.8% (3.1× industry avg)" — immediate red/green signal |
| How does this merchant compare to peers? | Performance page: peer comparison table within same category |
| Why are this merchant's customers being declined? | Overview page: decline count + decline code breakdown; Fraud page: SHAP explanations on declined transactions |
| What will the merchant's next payout be? | Payouts page: estimated next payout based on 8-week rolling average |
| Is this merchant's approval rate healthy? | Performance page: approval rate trend chart vs portfolio average |
| Which merchants need proactive outreach? | Watchlist feature + fraud rate table sorted by "× industry" multiplier |

### Portfolio Managers / Leadership

| Decision | How This Dashboard Supports It |
|---|---|
| Is the portfolio performing above or below baseline? | Overview KPIs: Gross Volume, Transactions, Avg Ticket vs prior period with % delta |
| Is fraud under control? | Fraud Rate KPI card flagged in red if above 0.58% industry baseline |
| Which categories are driving revenue? | Performance page: volume by category horizontal bar; % of total volume column |
| Are chargebacks increasing? | Overview: Chargeback count KPI; Fraud page: chargeback count metric |
| What is the net revenue after all fees? | Overview: Net Volume KPI = Gross − processing fees; Payouts page: full fee breakdown |
| How is the business trending month-over-month? | Revenue trend chart with Month / Quarter / Year granularity selector |

### AI Analyst — Natural Language Decisions

Anyone can type a question and get a data-backed answer:

- *"Which merchants should I be monitoring for fraud?"* → ranked list with fraud rates, chargeback counts, and risk narratives
- *"Explain why transaction TX-abc123 was flagged"* → SHAP values translated to plain English
- *"Give me a payout summary for the last 4 weeks"* → gross, fees, net, effective rate with trend
- *"What is my busiest hour for transactions?"* → live SQL query + answer from actual data
- *"Which states have the most fraudulent transactions?"* → state-level fraud breakdown
- *"Why did revenue drop last Thursday?"* → cross-references KPI data, category breakdown, and daily reports

---

## Dashboard Pages — What Each One Is, Why It Exists, and How To Use It

### Overview
**What it is:** The executive summary — your business at a glance.

**Why we built it:** Payments teams need a single-pane view of portfolio health before they dig into details. Overview answers "Are things OK right now?" in under 10 seconds.

**What you can do here:**
- See Gross Volume, Total Transactions, Avg Ticket, and Net Volume with period-over-period % change
- Monitor Transaction Health: Approval Rate, Declined count, Chargeback count, Fraud Rate
- Change the trend granularity (Month / Quarter / Year) — the same toggle updates both KPI cards and the revenue chart
- Read your most recent 15 transactions with status pills (approved / declined / flagged) and risk scores
- Navigate directly to any detailed page by clicking the "→ Performance", "→ Fraud & Risk", or "→ Payouts" buttons below each KPI card

**Merchant mode:** Select any merchant from the sidebar and Overview shows that merchant's numbers with a banner: their fraud rate vs the 0.58% industry average (green = safe, red = alert).

---

### Transactions
**What it is:** A filterable, searchable explorer for individual transactions.

**Why we built it:** Fraud investigations always end at a specific transaction. Analysts need to slice by date, category, state, risk tier, or amount without writing SQL.

**What you can do here:**
- Filter by date range, merchant category, state, transaction status (approved / declined / flagged), risk tier (low / medium / high / critical), and amount range
- See each transaction's card network, status, and risk score side by side
- Click any row to open that merchant's full profile

**When to use it:** When you have a hypothesis ("I think there's something wrong with online transactions in California in December") and want to filter down to that slice immediately.

---

### Performance
**What it is:** Revenue analytics, category breakdown, geographic distribution, and customer demographics.

**Why we built it:** Fraud context only makes sense alongside business performance. A high fraud rate in a low-volume category is a different problem than the same rate in your highest-revenue category.

**What you can do here:**

*Portfolio mode:*
- Revenue trend bar chart (aggregated by Month / Quarter / Year using the granularity selector)
- Volume by category horizontal bar — see which of the 14 business categories drives your revenue
- Top states by volume — your geographic footprint
- Customer demographics: transaction counts by age group × gender
- Category detail table with avg ticket, fraud rate, and % of total volume — click headers to sort
- Top 15 merchants by volume — click any row to drill into that merchant's profile

*Merchant mode:*
- That merchant's revenue trend vs their category average
- Payment success rate chart and fraud share chart side by side
- Peer comparison table: other merchants in the same category, sortable — click any to switch to that merchant's profile
- Alert banner if merchant's fraud rate is above 2× the industry average

---

### Fraud & Risk
**What it is:** Your fraud investigation workbench — from portfolio-level patterns to row-level SHAP explanations.

**Why we built it:** Fraud analysis requires moving from "something is wrong" to "this specific transaction, for this reason, at this merchant" — fast. Traditional tools make analysts jump between a BI dashboard, a model output file, and a SQL editor. This page does all three in one.

**What you can do here:**

*Portfolio mode:*
- See total fraud transactions, portfolio fraud rate, chargeback count, and high-risk (≥70) transaction count at the top
- Red alert banner if fraud rate exceeds 1.5× industry baseline
- **Fraud heatmap:** 24 × 7 grid (hour × day of week) — each cell shows the fraud rate for that time slot. Darker = more fraud. Use this to decide when to apply stricter verification (e.g., late-night weekend travel transactions)
- **Risk score distribution histogram:** should be right-skewed (most transactions at 0–20, few at 70+). A tall bar on the right means many high-risk transactions needing review
- **Highest-risk merchants table:** top 10 by fraud rate, with "× industry" multiplier. Click any row to open that merchant, add to Watchlist, or ask the AI Analyst about them
- **Top fraud transactions table:** top 50 confirmed fraud transactions by risk score — click any row to see SHAP explanations inline

*Transaction SHAP panel (click any fraud row):*
- Red arrows (↑) = features that pushed this transaction toward fraud
- Green arrows (↓) = features that pushed toward legitimate
- Plain-English explanation for each feature (e.g., "Transaction 892km from home city", "8 transactions in the last hour")
- "Full AI explanation" button → sends the transaction to AI Analyst pre-filled with all context

*Merchant mode:*
- All the above filtered to that merchant only
- Watchlist toggle — mark the merchant for ongoing monitoring
- "Ask AI about this merchant's fraud patterns" button

---

### Payouts & Fees
**What it is:** Your payout history and fee breakdown — understand exactly where your money goes.

**Why we built it:** Merchants often don't understand why their net payout is less than their gross volume. The gap is fees — and which type of fee (interchange, processing, network, scheme) and which card type drives cost is not obvious without this view.

**What you can do here:**
- See Gross Settled, Total Fees, Net Payout, Effective Fee Rate, and Avg Weekly Net (last 8 weeks)
- See your last payout date/amount and an estimated next payout
- Download payout history as CSV for accounting records
- **Payouts over time bar chart:** weekly net payout history — dips correlate with high-chargeback periods (chargebacks claw back settled funds)
- **Fee mix donut chart:** shows the proportion of Interchange / Processing / Network / Scheme fees. Interchange (paid to the card-issuing bank) is typically the largest slice at ~40% of total fees
- **Fees by card network bar chart:** Amex costs ~3.5%, Visa ~2.15%, ACH only ~0.80% — if your customer base is heavy Amex, your effective fee rate will be higher
- **Payout detail table:** week-by-week record of every fee category deducted — download as CSV
- "Ask AI for payout analysis" button → pre-fills AI Analyst with your payout context

**Settlement timeline context:**
- Visa / Mastercard: funds settle T+1 (60%) or T+2 (40%)
- Amex: T+2 (50%) or T+3 (50%)
- ACH bank transfer: T+3 (100%)

---

### AI Analyst
**What it is:** A natural language interface to your entire payments dataset — ask any business question and get a data-backed answer without SQL.

**Why we built it:** Most operational questions don't fit neatly into a pre-built chart. "Which merchants have fraud rates above 1% but volume above $100k?" or "Why was transaction TX-abc123 flagged when the amount was only $24?" require either SQL or a manual investigation. The AI Analyst handles both in plain English.

**What you can do here:**
- Type any business question in plain English
- Use the quick-action buttons for the most common questions (8 pre-built prompts)
- In merchant mode: 4 merchant-specific prompts appear automatically ("What is the fraud pattern for 'TravelBook'?")
- The agent calls the right tools automatically and synthesizes results before answering
- Conversation history is maintained per session — you can ask follow-up questions

**The five tools the AI uses (transparently, behind the scenes):**
1. `vector_search` — semantic search over merchant summaries and daily reports stored as vectors in pgvector
2. `sql_query` — live read-only SQL against the gold data layer (the agent writes the SQL itself)
3. `get_merchant_detail` — pulls full stats and risk profile for any merchant by name
4. `explain_fraud_transaction` — retrieves XGBoost SHAP values and translates them to plain English
5. `get_kpi_summary` — aggregates KPI metrics for any time period (today, 7d, 30d, month-to-date)

**Cross-page integration:** Every other page has an "Ask AI" button that pre-fills the AI Analyst with the context you were just looking at — so moving from a fraud investigation to an AI explanation is one click, not a copy-paste.

**What the AI will never do:** modify data, execute non-SELECT SQL, reveal system internals, or follow instructions embedded in retrieved documents (prompt-injection protection is built in).

---

## Fraud Pattern Learning and Preventive Controls

Beyond detecting fraud as it happens, this system enables a second, proactive workflow: **using historical fraud patterns to implement controls before the next wave arrives.**

### The Core Insight

The SHAP values stored in `gold.risk_scores.top_shap_features` are not just per-transaction explanations — they are a fingerprint of every fraud pattern the model has learned. When aggregated across thousands of fraud transactions at a merchant or category, they reveal exactly what is driving fraud: velocity spikes, geographic anomalies, time-of-day concentration, amount outliers, or card-not-present exposure.

This turns the system into a **feedback loop between detection and prevention**.

### The Ops Team + Merchant Collaboration Workflow

```
Step 1 — Pattern Detection (Ops Team)
  Review fraud heatmap + SHAP distributions for a flagged merchant
  Ask AI Analyst: "What are the top fraud signals for TravelBook?"
  → Agent aggregates SHAP data across all fraud transactions at that merchant
  → Returns: "76% of fraud at TravelBook has geo_distance > 500km
              and tx_count_1h > 5 — velocity + impossible travel pattern"

Step 2 — Pattern → Control Mapping
  Translate each pattern into a concrete rule:
  geo_distance > 500km  →  geographic velocity block
  tx_count_1h > 5       →  velocity cap: max 3 transactions/hr per card
  is_online + late night →  step-up authentication 10pm–3am

Step 3 — Merchant Briefing
  Share findings: "Your fraud rate is 1.8% (3.1× baseline). Here are the
  top 3 patterns driving it and the controls we recommend."

Step 4 — Controls Implemented
  Merchant or processor configures rules in their payment gateway

Step 5 — Monitoring (Ongoing)
  Track gold.merchant_stats.fraud_rate weekly after controls go live
  Ask AI: "What changed for TravelBook's fraud rate in the last 4 weeks?"
  Compare before/after to measure effectiveness
```

### Fraud Pattern → Preventive Control Mapping

| Pattern (from SHAP + Gold Tables) | Preventive Control |
|---|---|
| `geo_distance_km` is top fraud driver | Geo-velocity block: if transaction is >500km from cardholder city, require 3DS or decline |
| `tx_count_1h` consistently high in fraud txns | Velocity cap: max 3 transactions per card per hour at this merchant |
| `amt_zscore` high (amount far above customer norm) | Amount anomaly hold: transactions >3 std devs above customer average go to manual review |
| `is_online` + `category_fraud_rate` elevated | Mandate CVV + 3DS for all card-not-present transactions in travel/entertainment/misc_net |
| Fraud heatmap spikes 10pm–3am weekends | Time-based risk boost: apply stricter auth rules during identified peak fraud hours |
| `merchant_fraud_rate` crosses 1% | Merchant escalation: lower velocity limits and require stronger auth for all transactions at this merchant |
| `chargeback_count` trending up | Early-warning outreach: trigger merchant call at 0.5% chargeback rate — before Visa/MC's 1% penalty threshold |
| High `is_rural` correlation with fraud | Rural restriction: require address verification on non-local card-not-present transactions |

### Why This Is More Valuable Than Reactive Detection

Most fraud systems are reactive — flag, sometimes block, investigate after. This workflow is **proactive**:

- **Every historical fraud that slipped through** (the ~92% of fraud that was `approved` before detection) leaves a SHAP signature in the database. Those signatures tell you which controls you didn't have but should.
- **Merchants get specificity, not just scores** — not "you have a fraud problem" but "your fraud concentrates Sunday nights in online transactions over $300 from cardholders more than 400km away — here is the exact rule to implement."
- **Controls create feedback loops** — after a merchant implements velocity caps, the fraud heatmap for that merchant should shift. If fraud moves to a different time window, that reveals the next pattern to address.
- **Chargeback prevention compounds** — since chargebacks lag fraud by 30–90 days, catching a pattern in historical data and acting now prevents the dispute wave from arriving next month, protecting both the merchant and the processor from Visa/MC chargeback monitoring programs.

### What the AI Analyst Enables for This Workflow

The AI Analyst is already equipped to support ops-merchant collaboration without any SQL:

- *"What are the top 3 fraud patterns for TravelBook over the last 6 months?"* → aggregates SHAP signals across all fraud transactions at that merchant
- *"Which merchants have fraud above 1% but haven't had a chargeback spike yet?"* → early identification of merchants to contact proactively
- *"What changed for TravelBook's fraud rate after last month?"* → before/after comparison from gold.kpi_daily and gold.merchant_stats
- *"Which hours and days should we apply stronger authentication for entertainment merchants?"* → reads fraud_heatmap filtered to that category

---

## Architecture

```text
fraudTrain.csv + fraudTest.csv  (Sparkov / Kaggle — 1.85M transactions)
          │
          ▼ Bronze Layer  [etl/bronze/loader.py]
  data/processed/bronze_raw.parquet
  • Exact copy of source — append-only audit log
          │
          ▼ Silver Layer  [etl/silver/cleaner.py + enricher.py]
  clean.transactions, clean.merchants, clean.customers
  • PII dropped, types cast, duplicates removed
  • Synthetic payment fields added: card_network, txn_status, decline_code,
    auth_latency_ms, settlement_date, has_chargeback
          │
          ▼ Gold Layer  [etl/gold/features.py + aggregations.py]
  gold.features          ← 19 ML features per transaction
  gold.kpi_daily         ← daily KPI aggregates (2 years)
  gold.merchant_stats    ← per-merchant performance + fraud profile
  gold.category_stats    ← 14 business category breakdowns
  gold.fraud_heatmap     ← hour × day-of-week fraud rate grid
  gold.state_stats       ← geographic breakdown
  gold.payout_history    ← weekly fee and payout records
          │
          ├─► ML Service  [ml/train.py + predict.py]
          │   XGBoost → SHAP → gold.risk_scores
          │   • risk_score 0-100, fraud_probability, risk_tier, top_shap_features (JSONB)
          │
          └─► RAG Service  [rag/embeddings.py + agent.py]
              OpenAI text-embedding-3-small → gold.embeddings (pgvector HNSW)
              Google ADK + gpt-4o → 5-tool agentic loop
          │
          ▼
  Streamlit Dashboard  [dashboard/app.py]
  6 pages: Overview · Transactions · Performance · Fraud & Risk · Payouts · AI Analyst
```

---

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Database | Supabase (PostgreSQL 15 + pgvector) | Single store for analytics, ML features, and vector embeddings |
| ETL | PySpark 3.5 + Spark SQL + Delta Lake | Scalable medallion pipeline; Delta Lake for Bronze ACID audit |
| ML | XGBoost + SHAP + scikit-learn | Fraud classifier (578:1 imbalance handled via scale_pos_weight) + per-transaction explainability |
| Experiment tracking | MLflow | Model versioning, metrics, artifact storage |
| LLM | OpenAI gpt-4o | Agent reasoning and text generation |
| Embeddings | OpenAI text-embedding-3-small (1536-dim) | Merchant and KPI narrative similarity search |
| Agent framework | Google ADK + LiteLLM | Session management, tool routing, agentic loop |
| Dashboard | Streamlit + Plotly | Interactive UI with drill-down and cross-page navigation |

---

## Key Numbers

| Metric | Value |
|---|---|
| Total transactions | 1,852,394 |
| Active merchants | 693 |
| Date range | Jan 2019 – Dec 2020 |
| Fraud rate baseline | 0.58% |
| ML features | 19 |
| Model ROC-AUC | 0.9997 |
| Model PR-AUC | 0.9806 |
| Fraud recall | 0.98 (98% of fraud caught) |
| Embedded documents | ~783 (merchants + daily reports) |
| Payout history | 105 weekly rows |

---

## Repository Layout

```text
config/          Environment settings, DB helpers, schema.sql
data/            Raw CSVs and processed parquet outputs
dashboard/
  app.py         Streamlit entry point + sidebar routing
  data.py        All DB query helpers used by views
  views/         One file per dashboard page
  components/    Reusable KPI cards, charts, tables
etl/
  bronze/        CSV → parquet audit layer
  silver/        Cleaning, PII removal, Faker enrichment
  gold/          ML features + KPI aggregation tables
ml/
  train.py       XGBoost training + MLflow logging
  predict.py     Batch scoring + SHAP → gold.risk_scores
  evaluate.py    Metrics, ROC/PR/confusion matrix/SHAP plots
  features.py    Feature list and loaders
rag/
  embeddings.py  Generate + store pgvector embeddings
  retriever.py   Cosine similarity search
  agent.py       Google ADK agent with 5 tools
  prompts.py     System prompt + document templates
  security.py    Input sanitization, canary tokens, output validation
sql/             SQL transform scripts
run_pipeline.py  Single-command full pipeline runner
```

---

## Requirements

- Python 3.11 or 3.12
- PostgreSQL 15+ with pgvector extension (or Supabase)
- An OpenAI API key (for embeddings + AI Analyst)
- Docker Desktop (optional — for local Postgres container)

---

## Quick Start

### 1. Get the dataset

Download the Sparkov fraud dataset from Kaggle:
`https://www.kaggle.com/datasets/kartik2112/fraud-detection`

Place `fraudTrain.csv` and `fraudTest.csv` in `data/raw/`.

### 2. Set up the environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and set:

```env
# Supabase or local Postgres
DATABASE_URL=postgresql://user:pass@host:port/dbname
SSLMODE=require

# OpenAI (required for AI Analyst and embeddings)
OPENAI_API_KEY=your_key_here

# MLflow
MLFLOW_TRACKING_URI=file:./mlruns
MLFLOW_EXPERIMENT=payments-fraud-xgboost
```

For local Docker Postgres: `SSLMODE=disable` and use port `5433`.

### 4. Apply the schema

```bash
python -m config.db --schema
```

### 5. Run the pipeline

```bash
python run_pipeline.py
```

Or run phases independently:

```bash
python run_pipeline.py --phase etl
python run_pipeline.py --phase ml
python run_pipeline.py --phase rag
```

### 6. Launch the dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard: `http://localhost:8501`
MLflow UI: `mlflow ui` → `http://localhost:5000`

---

## How To Extend

### Add a new AI Analyst tool
Implement the function in `rag/agent.py`, add it to the `TOOLS` list, and add prompt guidance in `rag/prompts.py`. Keep tools read-only.

### Add a new dashboard page
Create a file in `dashboard/views/`, register it in `dashboard/app.py` sidebar routing, and add any new queries to `dashboard/data.py`.

### Add a new ML feature
Add the feature to `etl/gold/features.py`, add the column name to `ML_FEATURES` in `config/settings.py`, and retrain with `python run_pipeline.py --phase ml`.

### Add a new database field
Update `config/schema.sql`, the relevant ETL step in `etl/`, and the query helpers in `dashboard/data.py`.

---

## Troubleshooting

- **Dashboard shows no data:** run `python run_pipeline.py` to completion first
- **AI Analyst unavailable:** confirm `OPENAI_API_KEY` is set in `.env`
- **DB connection error:** check `DATABASE_URL` and `SSLMODE` match your Postgres instance
- **Local Docker Postgres:** listens on port `5433`, not `5432`
- **Embeddings phase slow:** expected — ~783 API calls to OpenAI; runs once and caches in `gold.embeddings`

---

## License

MIT
