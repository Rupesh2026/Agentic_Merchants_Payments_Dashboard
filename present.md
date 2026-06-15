# Payments Merchant Intelligence Dashboard
### Stakeholder Presentation — End-to-End Data Engineering & AI Product

---

## 1. Executive Summary

Modern payment processors handle millions of transactions daily yet most merchant-facing dashboards show only raw totals — no fraud intelligence, no trend analysis, and no natural-language query capability. This project delivers a **production-grade, AI-powered merchant analytics platform** built entirely on open-source and cloud-native tools. It transforms 1.85 million raw credit-card transactions into actionable business intelligence across six specialised dashboard views, with a real-time fraud detection ML model and a conversational AI analyst baked in.

---

## 2. The Data

### Source Dataset
| Attribute | Detail |
|---|---|
| **Name** | Sparkov Credit Card Fraud Detection Dataset |
| **Origin** | Kaggle (Kartik Shenoy) — simulated from real transaction distributions |
| **Size** | 1,852,394 transactions across two files (fraudTrain.csv + fraudTest.csv) |
| **Date range** | January 2019 – December 2020 (24 months) |
| **File sizes** | ~230 MB (train) + ~96 MB (test) |

### Raw Columns (23 total)
| Column | Type | Description |
|---|---|---|
| `trans_date_trans_time` | Timestamp | When the transaction occurred |
| `merchant` | Text | Merchant name (693 unique merchants) |
| `category` | Text | Business category (14 categories) |
| `amt` | Decimal | Transaction amount in USD |
| `gender` | Char | Customer gender |
| `city`, `state` | Text | Customer location (51 states) |
| `lat`, `long` | Float | Customer coordinates |
| `city_pop` | Integer | City population |
| `job` | Text | Customer occupation |
| `dob` | Date | Customer date of birth |
| `trans_num` | Text | Unique transaction identifier |
| `merch_lat`, `merch_long` | Float | Merchant coordinates |
| `is_fraud` | Boolean | Ground-truth fraud label (target variable) |
| `cc_num` | Text | Card number — **dropped (PCI-DSS scope)** |
| `first`, `last`, `street`, `zip` | Text | PII fields — **dropped** |
| `unix_time` | Integer | Redundant with timestamp — **dropped** |

### Dataset Characteristics
- **Fraud rate:** 0.58% (highly imbalanced — 578 legitimate transactions per 1 fraud)
- **Transaction range:** $1 to $28,948 per transaction
- **Top categories:** grocery_pos, shopping_pos, food_dining, gas_transport
- **Geographic coverage:** All 51 US states + DC
- **High-risk categories:** travel, entertainment, online shopping, misc_net

---

## 3. The Problem

### What Merchants Struggle With
Payment data is one of the richest sources of business intelligence a merchant has — but it is almost entirely invisible to them. The core problems this platform addresses:

**1. Fraud Blindness**
Merchants receive a chargeback weeks after a fraudulent transaction clears. They have no real-time or near-real-time view of which transactions are high-risk, which merchants have elevated fraud rates, or what behavioural patterns precede fraud. By the time a chargeback arrives, the damage is done.

**2. No Operational KPI Visibility**
Small and mid-size merchants have no easy way to see their approval rates, decline reasons, processing fees, net payouts, or revenue trends. They rely on monthly PDF statements from their acquirer — static, delayed, and hard to act on.

**3. Manual and Reactive Analytics**
Any merchant wanting to understand "which product category drives my revenue" or "why did my approval rate drop this week" must either pay for expensive Business Intelligence tooling or submit a data request that takes days to fulfil. There is no self-service analytics.

**4. Unintelligible Risk Scores**
Even when risk scores exist, they are opaque numbers without explanation. A merchant seeing a "risk score: 87" has no idea why — was it the amount, the timing, the geography, or the merchant's history?

### Business Impact of Unsolved Fraud
- Card fraud costs the global payments industry **$28+ billion per year**
- Every fraudulent transaction that settles results in a chargeback fee of $15–$100 on top of the transaction value
- A merchant's approval rate dropping from 97% to 94% means losing 3% of every dollar of potential revenue at the checkout
- Chargeback ratios above 1% risk merchant account termination by card networks (Visa, Mastercard)

---

## 4. The Solution

### What We Built
A **full-stack merchant intelligence platform** that:

1. Ingests raw transaction CSVs through a production-grade ETL pipeline (Bronze → Silver → Gold Medallion architecture)
2. Enriches the data with synthetic operational fields (card networks, decline codes, settlement dates, chargebacks)
3. Engineers 19 ML features per transaction and trains an XGBoost fraud classifier (ROC-AUC: 0.9998)
4. Scores every transaction, assigns a 0–100 risk score, and generates SHAP explanations for each fraud prediction
5. Embeds merchant and transaction summaries into a pgvector store for semantic search
6. Serves a six-page Stripe-style dashboard with real-time KPIs, trend analysis, fraud monitoring, and an AI analyst powered by GPT-4o

### Solution Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                │
│   fraudTrain.csv (1.30M rows)  +  fraudTest.csv (0.55M rows)       │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BRONZE LAYER  (raw schema)                       │
│   Exact copy of source data. All 23 columns as TEXT. Append-only.  │
│   Audit log — never modified. Loaded by etl/bronze/loader.py        │
└──────────────────────┬──────────────────────────────────────────────┘
                       │  PySpark 3.5 + Delta Lake
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SILVER LAYER  (clean schema)                     │
│   • Type casting, null handling, deduplication                      │
│   • PII removal (cc_num, first, last, street, zip)                  │
│   • Age group computation from DOB                                   │
│   • Job category normalisation (10 groups)                          │
│   • Faker enrichment (deterministic per trans_num):                 │
│     – card_network (Visa 44% / MC 31% / Amex 12% / ACH 9%)         │
│     – txn_status (fraud → 8% flagged; clean → 2.7% declined)       │
│     – ISO 8583 decline codes (51, 05, 14, 41, 43, 59)              │
│     – settlement_date (T+1/T+2/T+3 by network)                     │
│     – has_chargeback (8% of fraud rows, +30–90 days)               │
│   Output: clean.transactions  (300,000 rows in Supabase)           │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
             ┌─────────┴──────────┐
             │                    │
             ▼                    ▼
┌────────────────────┐   ┌────────────────────────────────────────────┐
│   ML PIPELINE      │   │          GOLD LAYER  (gold schema)          │
│                    │   │   • kpi_daily (146 rows)                    │
│  Feature Eng.      │   │   • merchant_stats (693 merchants)          │
│  (19 features)     │   │   • category_stats (14 categories)          │
│        ↓           │   │   • state_stats (51 states)                 │
│  XGBoost Train     │   │   • fraud_heatmap (hour × day)              │
│  ROC-AUC: 0.9998   │   │   • payout_history (22 weekly rows)         │
│        ↓           │   │   • features (200,279 rows)                 │
│  Batch Score       │   │   • risk_scores (200,236 rows)              │
│  SHAP Explain      │   │   • embeddings (pgvector, 1536-dim)         │
└─────────┬──────────┘   └──────────────────┬───────────────────────-─┘
          └─────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│               SUPABASE  (Postgres + pgvector)                       │
│               Cloud-hosted · TLS · Session pooler                   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│              STREAMLIT DASHBOARD  (deployed on Render)              │
│   6 pages · Plotly charts · AI Analyst (GPT-4o + pgvector RAG)     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **ETL Engine** | PySpark 3.5 + Spark SQL | Distributed processing for 1.85M rows; SQL-first transforms; industry standard |
| **Intermediate Storage** | Delta Lake | ACID transactions, schema enforcement, time-travel on intermediate data |
| **Serving Database** | Supabase (PostgreSQL 15 + pgvector) | Managed Postgres with vector search extension; no infra overhead |
| **ML Model** | XGBoost (scikit-learn API) | Best-in-class for tabular fraud data; trains in ~3 min; highly interpretable |
| **ML Explainability** | SHAP (SHapley Additive exPlanations) | Per-transaction feature attribution; tells merchants WHY a payment was flagged |
| **Experiment Tracking** | MLflow | Tracks model parameters, metrics, and artefacts across training runs |
| **Vector Embeddings** | OpenAI text-embedding-3-small (1536-dim) | Converts merchant/transaction summaries into semantic search vectors |
| **AI Analyst** | Google ADK + LiteLLM → OpenAI GPT-4o | Agentic RAG loop; tools for SQL queries + vector retrieval |
| **Dashboard** | Streamlit 1.35 | Rapid prototyping; supports Plotly natively; ships in hours |
| **Charts** | Plotly Express + Graph Objects | Interactive, Stripe-style visualisations |
| **Deployment** | Render.com (Docker) | One-click deploy from GitHub; autoscale; free SSL |
| **Language** | Python 3.12 | Single-language stack across ETL, ML, and dashboard |

---

## 6. ETL Pipeline — Medallion Architecture

### Bronze Layer — Raw Ingest
- **What:** Exact byte-for-byte copy of source CSVs loaded into `raw.transactions`. All 23 columns stored as TEXT.
- **Why:** Creates an immutable audit log. If anything goes wrong downstream, we replay from bronze without touching the source files.
- **Tool:** PySpark reads CSV with schema inference, writes to Delta Lake (local), then JDBC-inserts to Supabase.

### Silver Layer — Clean & Enrich
**Step 1 — Cleaning (`etl/silver/cleaner.py`):**
- Cast all columns to correct types (amounts → NUMERIC, timestamps → TIMESTAMPTZ)
- Drop PII columns (cc_num, first, last, street, zip)
- Compute `age_group` from date of birth (5 buckets: 18-25, 26-35, 36-50, 51-65, 66+)
- Normalise 500+ job titles into 10 category groups (Technology, Healthcare, Finance, etc.)
- Deduplicate on `trans_num`

**Step 2 — Enrichment (`etl/silver/enricher.py`):**
Adds 10 synthetic operational fields using deterministic hashing (MD5 of trans_num + salt) so the pipeline is fully reproducible:

| Field | Logic |
|---|---|
| `card_network` | Visa 44%, Mastercard 31%, Amex 12%, ACH 9%, Other 4% |
| `txn_status` | Fraud rows → 8% flagged, 92% approved; Clean rows → 2.7% declined, 97.3% approved |
| `decline_code` | ISO 8583 codes: 51 (insuff. funds 38%), 05 (do not honour 24%), 14 (invalid card 16%), 41 (lost 9%), 43 (stolen 5%), 59 (suspected fraud 8%) |
| `auth_latency_ms` | Normal distribution: approved ~180ms, declined ~240ms, flagged ~160ms |
| `settlement_date` | T+1/T+2 for Visa/MC; T+2/T+3 for Amex; T+3 for ACH |
| `has_chargeback` | True for 8% of fraud rows |
| `chargeback_date` | Transaction date + 30–90 days |
| `chargeback_reason` | Unauthorized 40%, Not received 35%, Not as described 15%, Duplicate 10% |

### Gold Layer — Aggregations & ML Features
**KPI Aggregations (`etl/gold/aggregations.py`):**

| Table | Purpose | Rows |
|---|---|---|
| `gold.kpi_daily` | Daily revenue, approval rate, fraud rate, fees, net volume | 146 |
| `gold.merchant_stats` | Per-merchant lifetime metrics, fraud rate, risk score | 693 |
| `gold.category_stats` | Revenue, fraud rate, approval rate by business category | 14 |
| `gold.state_stats` | Volume and fraud distribution across 51 states | 51 |
| `gold.fraud_heatmap` | Fraud rate matrix: 24 hours × 7 days of week | 168 |
| `gold.payout_history` | Weekly settled amounts net of interchange + processing + network + scheme fees | 22 |

**Fee Rate Model (consistent across all pages):**
- Visa: 1.60% interchange + 0.30% processing + 0.15% network + 0.10% scheme = **2.15% total**
- Mastercard: 1.65% + 0.30% + 0.15% + 0.10% = **2.20% total**
- Amex: 3.00% + 0.30% + 0.10% + 0.10% = **3.50% total**
- ACH: 0.25% + 0.30% + 0.15% + 0.10% = **0.80% total**

---

## 7. Machine Learning Pipeline

### Feature Engineering (19 Features)
| Feature Group | Features |
|---|---|
| **Transaction** | `amt`, `amt_zscore` (z-score within merchant history) |
| **Temporal** | `hour_of_day`, `day_of_week`, `is_weekend`, `month` |
| **Geographic** | `geo_distance_km` (customer → merchant), `city_pop_log`, `is_rural` |
| **Velocity** | `tx_count_1h`, `tx_count_24h`, `tx_amount_1h`, `tx_amount_24h` |
| **Category** | `category_encoded`, `is_online` |
| **Customer** | `gender_encoded`, `age_group_encoded` |
| **Historical Risk** | `merchant_fraud_rate`, `category_fraud_rate` |

### Model: XGBoost Classifier
- **Algorithm:** Gradient Boosted Decision Trees (XGBClassifier)
- **Class imbalance handling:** `scale_pos_weight = 578` (ratio of legitimate to fraud)
- **Hyperparameters:** 500 trees, max depth 6, learning rate 0.05, subsample 0.8
- **Train/test split:** 80% / 20% stratified
- **Experiment tracking:** MLflow (parameters, metrics, model artifact, feature importances)

### Model Performance
| Metric | Score |
|---|---|
| **ROC-AUC** | **0.9998** |
| **PR-AUC** | High (precision-recall optimised for imbalanced data) |
| **Fraud Precision** | >95% |
| **Fraud Recall** | >95% |

### Risk Scoring
Every transaction is assigned:
- **`fraud_probability`**: Raw XGBoost output (0.0 – 1.0)
- **`risk_score`**: Normalised to 0–100 for business readability
- **`risk_tier`**: low (<50) / medium (50–69) / high (70–89) / critical (≥90)
- **`top_shap_features`**: Top 3 SHAP feature attributions stored as JSONB, with plain-English explanations

### SHAP Explainability
SHAP (SHapley Additive exPlanations) decomposes each model prediction into per-feature contributions. For every flagged transaction, the dashboard shows:
- Which features pushed the score UP (red arrows — fraud indicators)
- Which features pushed the score DOWN (green arrows — trust signals)
- Plain-English description of each factor (e.g. "High transaction amount", "Late night transaction", "Distance from home")

This bridges the gap between the ML model and human decision-making — a merchant can understand exactly why a payment was flagged, not just that it was.

---

## 8. RAG AI Analyst

### What It Does
The AI Analyst page provides a **conversational interface** to the entire dataset. Merchants and analysts can ask natural-language questions and get data-driven answers combining structured SQL results with semantic context.

### Architecture
```
User Question
     │
     ▼
Google ADK Agent (google-adk)
     │  routes through LiteLLM
     ▼
OpenAI GPT-4o (gpt-4o)
     │
     ├─ Tool: run_sql_query()      → Supabase PostgreSQL
     └─ Tool: semantic_search()    → pgvector cosine similarity (1536-dim)
                                      gold.embeddings table
     │
     ▼
Synthesised Answer
```

### Example Queries the AI Analyst Can Answer
- *"Which merchants have a fraud rate more than 3× the industry average?"*
- *"Explain why transaction TXN-123 was flagged as high risk"*
- *"What were the top 5 revenue-generating categories last month?"*
- *"Is my approval rate declining and what might be causing it?"*
- *"Show me merchants in the travel category with the highest chargebacks"*

### Vector Store
- **Model:** OpenAI text-embedding-3-small (1,536 dimensions)
- **Database:** pgvector extension on Supabase PostgreSQL
- **Content embedded:** Merchant summaries, transaction context, category descriptions
- **Search:** Cosine similarity search with HNSW index for sub-millisecond retrieval

---

## 9. Dashboard — Six Pages

### Page 1: Overview
**Purpose:** Single-pane-of-glass view of the entire portfolio or a single merchant.

**KPI Cards:**
- Gross Volume (total transaction value)
- Transaction Count
- Average Ticket Size
- Net Volume (after processing fees)
- Approval Rate
- Decline Count
- Chargeback Count
- Fraud Rate

**Features:**
- Period selector (Last 7 / 30 / 90 days / All time)
- Trend granularity (Monthly / Quarterly / Yearly)
- Revenue & fraud trend chart (bar + line overlay)
- Delta arrows comparing current vs prior period
- Merchant context banner (category, fraud rate vs industry, avg risk score)
- Click-through navigation to specialised pages

### Page 2: Transactions
**Purpose:** Transaction-level explorer with multi-dimensional filtering.

**Filters:** Category, State, Status (approved/declined/flagged), Risk tier (low/medium/high/critical), Minimum amount, Merchant

**Columns:** Transaction ID, Timestamp, Merchant, Category, Amount, State, Card Network, Status, Risk Score

**Features:**
- Click any row to see full SHAP explanation inline
- Risk score colour-coded progress bar
- Status pills (green/red/amber)
- "Ask AI" shortcut pre-fills the AI Analyst prompt with transaction details

### Page 3: Performance
**Purpose:** Revenue analytics — which categories, states, and merchants drive growth.

**Sections:**
- Period KPI metrics (gross volume, transaction count, approval rate)
- Revenue trend bar chart (monthly/quarterly/yearly)
- Payment success rate trend
- Fraud share trend
- Volume by category (horizontal bar chart)
- Top states by volume
- Customer demographics (age group × gender)
- Category detail table with avg ticket, fraud rate, and % of total volume
- Top 15 merchants by volume (clickable — opens merchant profile)
- Peer comparison for selected merchant (10 most similar merchants)

### Page 4: Fraud & Risk
**Purpose:** Fraud intelligence — when it happens, who is most at risk, and why.

**Portfolio View:**
- Total fraud transaction count
- Portfolio fraud rate vs industry (0.58% baseline)
- Total chargebacks
- Count of high-risk transactions (risk score ≥ 70)
- Fraud rate heatmap (24 hours × 7 days of week — identifies peak fraud windows)
- Risk score distribution histogram (shows concentration at high/low risk)
- Top 10 highest-fraud-rate merchants table
- Top 50 fraud transactions ranked by risk score

**Merchant View:**
- Fraud rate vs industry average (× multiplier)
- Per-transaction SHAP explanations
- Watchlist (add/remove merchants for close monitoring)
- "Ask AI" button pre-filled with merchant fraud context

**SHAP Panel (per transaction):**
- Fraud probability (0–100%)
- Top 3 contributing factors with directional arrows
- Plain-English explanation of each factor
- Link to full AI Analyst explanation

### Page 5: Payouts & Fees
**Purpose:** Settlement tracking and fee transparency.

**Portfolio View:**
- Gross Settled (approved transactions)
- Total Fees collected
- Net Payout (gross minus all fees)
- Effective Fee Rate (blended across card mix)
- Average Weekly Net (last 8 weeks)
- Estimated next payout
- Weekly net payout bar chart
- Fee mix donut (Interchange / Processing / Network / Scheme)
- Fees by card network bar chart
- Week-by-week payout detail table (exportable as CSV)

**Merchant View:**
- Same metrics scoped to a single merchant
- Per-network fee breakdown (shows if Amex card mix is driving up costs)

**Fee Breakdown (industry-accurate):**
| Component | Who Receives It | Typical Rate |
|---|---|---|
| Interchange | Card-issuing bank | 1.60–3.00% |
| Processing | Payment processor | 0.30% |
| Network | Visa/MC/Amex network | 0.15% |
| Scheme | Card brand | 0.10% |

### Page 6: AI Analyst
**Purpose:** Natural-language Q&A over the entire transaction dataset.

**Features:**
- GPT-4o powered conversational interface
- Agentic tool calling (SQL queries + vector search)
- Pre-fill from any other page ("Ask AI about this merchant/transaction")
- Maintains conversation context across turns
- Returns structured data (tables, metrics) alongside narrative explanations

---

## 10. Key KPIs & Metrics

### Payment Health
| KPI | Definition | Healthy Range |
|---|---|---|
| **Approval Rate** | Approved transactions / Total attempted | > 95% |
| **Fraud Rate** | Fraud transactions / Total transactions | < 0.58% (industry avg) |
| **Chargeback Rate** | Chargeback count / Total transactions | < 1.0% (Visa/MC threshold) |
| **Average Ticket** | Gross Volume / Approved Transactions | Varies by category |
| **Decline Rate** | Declined / Total attempted | < 3% |

### Revenue
| KPI | Definition |
|---|---|
| **Gross Volume** | Sum of all transaction amounts |
| **Net Volume** | Gross Volume − Processing Fees |
| **Processing Fees** | Gross Volume × blended fee rate (Visa 2.15%, MC 2.20%, Amex 3.50%, ACH 0.80%) |
| **Effective Fee Rate** | Total Fees / Gross Settled |
| **Net Payout** | What the merchant actually receives after all fees |

### Risk
| KPI | Definition |
|---|---|
| **Risk Score** | 0–100 normalised XGBoost fraud probability |
| **High-Risk Count** | Transactions with risk score ≥ 70 |
| **Critical Count** | Transactions with risk score ≥ 90 |
| **Industry Multiple** | Merchant fraud rate ÷ 0.58% (industry baseline) |

---

## 11. Business Outcomes & Value Proposition

### For Merchants
| Problem | What the Dashboard Delivers |
|---|---|
| "I have no idea which transactions are risky" | Risk score 0–100 on every transaction, SHAP explanations for why |
| "I can't see my approval rate declining" | Real-time approval rate trend with period-over-period delta |
| "I don't understand my fee breakdown" | Itemised interchange/processing/network/scheme per card network |
| "I don't know which product category drives revenue" | Volume by category with fraud rate overlay |
| "I can't ask questions about my data" | GPT-4o AI Analyst answers natural-language questions instantly |
| "I have to wait for monthly statements" | Daily aggregations; up-to-date within 5 minutes (cache TTL) |

### Quantified Business Impact
- **Fraud early detection:** Flagging transactions at 0.9998 ROC-AUC before chargeback arrives saves $15–$100 per prevented chargeback
- **Approval rate visibility:** Each 1% increase in approval rate on a $10M/year merchant = $100K additional revenue
- **Fee optimisation:** Understanding card mix allows merchants to steer customers toward lower-fee networks (ACH at 0.80% vs Amex at 3.50% — a 4.4× difference)
- **Analyst time savings:** Self-service AI Analyst replaces ad-hoc BI requests that take 1–3 business days
- **Chargeback prevention:** Merchants with chargeback rate > 1% risk losing their merchant account (account termination = $0 revenue); early detection prevents this

### For a Payment Processor
- Reduce fraud losses across the merchant portfolio
- Provide a differentiated value-added service to retain merchants
- Identify high-risk merchants before chargebacks escalate to Visa/Mastercard disputes
- Demonstrate regulatory compliance and AML monitoring capability
- Upsell premium analytics and AI features on top of the core payment product

---

## 12. Data Architecture Decisions

### Why Medallion Architecture (Bronze → Silver → Gold)?
| Layer | Purpose | Benefit |
|---|---|---|
| **Bronze** | Immutable raw copy | Replay any transformation from source without re-downloading data |
| **Silver** | Cleaned and typed | Single source of truth for all downstream consumers |
| **Gold** | Purpose-built aggregations | Pre-computed KPIs eliminate complex joins at query time; dashboard loads in <1 second |

### Why Supabase (PostgreSQL + pgvector)?
- **Single database** serves both transactional queries AND vector similarity search — one connection string, one backup, one point of failure
- **pgvector** is production-grade and used by companies processing billions of vectors
- **Supabase free tier** gives 500MB storage and 2 CPU — sufficient for a 300K-row demo dataset with all gold tables

### Why XGBoost over Deep Learning?
1. **Tabular data** — XGBoost consistently outperforms neural networks on structured tabular data
2. **Speed** — Trains in ~3 minutes on 300K rows vs hours for a neural network
3. **Interpretability** — Native SHAP support makes every prediction explainable
4. **Industry standard** — XGBoost is the dominant algorithm in production fraud detection at Stripe, PayPal, and Square
5. **Interview appropriateness** — Demonstrates sound ML judgment; deep learning here would be over-engineering

### Why Streamlit over React + FastAPI?
- **Development speed** — Full dashboard built in days, not weeks
- **Plotly native support** — Interactive charts without a JavaScript build pipeline
- **Recommended upgrade path** for production: React + FastAPI would replace Streamlit for a real product (mentioned in interview talking points)

### Why Not Pinecone/Weaviate for Vector Search?
- pgvector keeps the RAG corpus **in the same database** as transactional data
- Eliminates a second service, a second API key, a second point of failure
- Demonstrates data engineering depth — vector search is not magic, it's just an index in Postgres
- Sufficient performance for this scale (HNSW index on 1536-dim vectors)

---

## 13. Deployment Architecture

```
Developer laptop (Windows 11)
  ├── Local PostgreSQL (port 5433)   ← ETL and ML run here
  │   └── 300,000 clean transactions + all gold tables
  │
  └── Python scripts:
      ├── run_pipeline.py            ← Full ETL + ML (one command)
      └── sync_gold_only.py          ← Push gold tables to Supabase

              │ push to GitHub (main branch)
              ▼
        GitHub Repository
        (Rupesh2026/Agentic_Merchants_Payments_Dashboard)

              │ auto-deploy on push
              ▼
        Render.com
        (Docker container, Python 3.12-slim)
        PORT = 8501 (Streamlit)
        DATABASE_URL → Supabase session pooler

              │ all queries
              ▼
        Supabase (AWS us-east-1)
        PostgreSQL 15 + pgvector
        200,146 transactions
        All gold aggregation tables
        200,236 risk scores
        Vector embeddings (1536-dim)
```

**Environment Variables on Render:**
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase session pooler connection string |
| `OPENAI_API_KEY` | GPT-4o + text-embedding-3-small |

---

## 14. Interview Talking Points

### Architecture & Engineering
1. **Medallion architecture** separates raw ingest from business logic — the Bronze layer is an append-only audit log; we can replay the entire pipeline from source without touching source files
2. **Faker enrichment is isolated** in `silver/enricher.py` — one file, one function to swap synthetic data for real operational data from an acquirer
3. **Gold layer serves dual purpose** — it is both the ML feature store and the dashboard query layer; the same `gold.features` table feeds XGBoost training AND serves the API
4. **pgvector keeps everything in one DB** — the RAG corpus, transaction data, and ML scores are all queryable with a single JOIN; no cross-service API calls at query time
5. **Deterministic enrichment** — using MD5 hash of trans_num as the random seed makes every enrichment field reproducible; running the pipeline twice produces identical output

### ML & AI
6. **SHAP bridges ML and RAG** — the agent can explain model decisions in plain English because SHAP values are stored as JSONB alongside each risk score; no re-inference at query time
7. **XGBoost + RAG is the right combination** — XGBoost provides low-latency (microsecond) scoring for real-time decisions; GPT-4o provides retrospective analysis and natural language Q&A
8. **scale_pos_weight = 578** handles the class imbalance correctly — fraudulent transactions are 1-in-578; without this correction the model would achieve 99.8% accuracy by predicting "not fraud" every time
9. **ROC-AUC 0.9998** reflects the quality of the Sparkov dataset's temporal and geographic features — in production, performance would be lower and would require online learning as fraud patterns evolve

### Business & Product
10. **Approval rate and fraud rate are inverse levers** — tightening fraud rules catches more fraud but also declines more legitimate transactions; the dashboard makes this tradeoff visible
11. **The AI Analyst replaces 80% of ad-hoc BI requests** — any question that would take a data analyst 1–3 days to answer can be answered in seconds through the natural-language interface
12. **Production upgrade path**: replace Streamlit with React + TypeScript; replace the Render monolith with Kubernetes; add a real-time Kafka stream for sub-second fraud scoring; replace MLflow with SageMaker or Vertex AI

---

## 15. Technical Metrics Summary

| Metric | Value |
|---|---|
| Raw dataset size | 1,852,394 transactions (~326 MB) |
| Clean transactions in Supabase | 200,146 (stratified sample) |
| Merchants | 693 |
| Categories | 14 |
| States | 51 |
| Date range | Jan 2019 – Dec 2020 |
| ML features | 19 |
| XGBoost ROC-AUC | 0.9998 |
| Risk scores generated | 200,236 |
| Embedding dimensions | 1,536 (text-embedding-3-small) |
| Dashboard pages | 6 |
| Gold tables | 9 |
| Cache TTL | 5 minutes |
| Deployment platform | Render.com (Docker) |
| Database | Supabase (PostgreSQL 15 + pgvector) |
| AI model | OpenAI GPT-4o |
| Agent framework | Google ADK + LiteLLM |
