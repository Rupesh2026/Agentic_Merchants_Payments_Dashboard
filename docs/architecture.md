# architecture.md — System Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA SOURCES                                                    │
│  fraudTrain.csv + fraudTest.csv  (Sparkov / Kaggle)             │
│  + Faker enrichment (decline codes, card_network, chargebacks)  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  BRONZE LAYER  —  schema: raw                                    │
│  Exact copy of source. Append-only. No transforms.              │
│  Tables: raw.transactions                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  SILVER LAYER  —  schema: clean                                  │
│  Cleaned, typed, deduplicated, PII dropped, Faker enriched.     │
│  Tables: clean.transactions, clean.merchants, clean.customers   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOLD LAYER  —  schema: gold                                     │
│  ML features, KPI aggregates, risk scores, embeddings.          │
│  Tables: gold.features, gold.risk_scores, gold.kpi_daily,       │
│          gold.merchant_stats, gold.fraud_heatmap,               │
│          gold.category_stats, gold.embeddings                   │
└──────────┬──────────────────────────────────┬───────────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐          ┌────────────────────────────────┐
│  ML SERVICE          │          │  RAG AGENT SERVICE             │
│  XGBoost model       │          │  LangChain + Claude API        │
│  SHAP explainer      │          │  pgvector similarity search    │
│  → gold.risk_scores  │          │  → natural language answers    │
└──────────┬──────────┘          └──────────────┬─────────────────┘
           │                                    │
           └─────────────────┬──────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  DASHBOARD  —  Streamlit + Plotly                               │
│  6 pages: Overview · Transactions · Performance ·               │
│           Fraud & Risk · Payouts · AI Analyst                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## PostgreSQL Schema — Full DDL

### Raw Schema (Bronze)

```sql
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.transactions (
    id                    BIGSERIAL PRIMARY KEY,
    trans_date_trans_time TEXT,
    cc_num                TEXT,          -- kept in raw only, dropped in silver
    merchant              TEXT,
    category              TEXT,
    amt                   TEXT,
    first                 TEXT,          -- PII: kept in raw only
    last                  TEXT,          -- PII: kept in raw only
    gender                TEXT,
    street                TEXT,          -- PII: kept in raw only
    city                  TEXT,
    state                 TEXT,
    zip                   TEXT,          -- dropped in silver
    lat                   TEXT,
    long                  TEXT,
    city_pop              TEXT,
    job                   TEXT,
    dob                   TEXT,
    trans_num             TEXT,
    unix_time             TEXT,          -- dropped in silver
    merch_lat             TEXT,
    merch_long            TEXT,
    is_fraud              TEXT,
    source_file           TEXT,          -- 'fraudTrain.csv' or 'fraudTest.csv'
    loaded_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_raw_trans_num ON raw.transactions(trans_num);
CREATE INDEX idx_raw_loaded_at ON raw.transactions(loaded_at);
```

### Clean Schema (Silver)

```sql
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.transactions (
    -- Core identifiers
    trans_id              BIGSERIAL PRIMARY KEY,
    trans_num             TEXT UNIQUE NOT NULL,
    trans_at              TIMESTAMPTZ NOT NULL,

    -- Merchant
    merchant              TEXT NOT NULL,
    category              TEXT NOT NULL,
    merch_lat             DOUBLE PRECISION,
    merch_long            DOUBLE PRECISION,

    -- Transaction
    amt                   NUMERIC(12,2) NOT NULL,
    is_fraud              BOOLEAN NOT NULL,

    -- Customer (anonymized)
    gender                CHAR(1),
    age_group             TEXT,          -- derived from dob: '18-25','26-35','36-50','51+'
    city                  TEXT,
    state                 TEXT,
    city_pop              INTEGER,
    job_category          TEXT,          -- grouped from job field
    cust_lat              DOUBLE PRECISION,
    cust_long             DOUBLE PRECISION,

    -- Faker-enriched fields
    card_network          TEXT,          -- 'Visa','Mastercard','Amex','ACH','Other'
    card_last4            CHAR(4),
    txn_status            TEXT,          -- 'approved','declined','flagged'
    decline_code          TEXT,          -- NULL if approved, ISO 8583 code if declined
    decline_reason        TEXT,          -- human readable decline reason
    auth_latency_ms       INTEGER,       -- 150-300ms realistic range
    settlement_date       DATE,          -- T+1 to T+3

    -- Chargeback (only for fraud rows, ~8%)
    has_chargeback        BOOLEAN DEFAULT FALSE,
    chargeback_date       DATE,
    chargeback_reason     TEXT,

    -- Audit
    source_file           TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_clean_trans_at      ON clean.transactions(trans_at);
CREATE INDEX idx_clean_merchant      ON clean.transactions(merchant);
CREATE INDEX idx_clean_category      ON clean.transactions(category);
CREATE INDEX idx_clean_is_fraud      ON clean.transactions(is_fraud);
CREATE INDEX idx_clean_state         ON clean.transactions(state);
CREATE INDEX idx_clean_txn_status    ON clean.transactions(txn_status);
CREATE INDEX idx_clean_card_network  ON clean.transactions(card_network);

-- Merchant dimension table
CREATE TABLE IF NOT EXISTS clean.merchants (
    merchant_id     BIGSERIAL PRIMARY KEY,
    merchant_name   TEXT UNIQUE NOT NULL,
    category        TEXT NOT NULL,
    merch_lat       DOUBLE PRECISION,
    merch_long      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Customer dimension table (anonymized)
CREATE TABLE IF NOT EXISTS clean.customers (
    customer_id     BIGSERIAL PRIMARY KEY,
    gender          CHAR(1),
    age_group       TEXT,
    city            TEXT,
    state           TEXT,
    city_pop        INTEGER,
    job_category    TEXT,
    cust_lat        DOUBLE PRECISION,
    cust_long       DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### Gold Schema (Features + KPIs)

```sql
CREATE SCHEMA IF NOT EXISTS gold;

-- ML feature table (one row per transaction)
CREATE TABLE IF NOT EXISTS gold.features (
    trans_id              BIGINT PRIMARY KEY REFERENCES clean.transactions(trans_id),
    trans_num             TEXT NOT NULL,
    trans_at              TIMESTAMPTZ,
    amt                   NUMERIC(12,2),
    is_fraud              BOOLEAN,

    -- Temporal features
    hour_of_day           INTEGER,       -- 0-23
    day_of_week           INTEGER,       -- 0=Mon, 6=Sun
    is_weekend            BOOLEAN,
    month                 INTEGER,

    -- Geographic features
    geo_distance_km       DOUBLE PRECISION,   -- Haversine(cust, merch)
    city_pop_log          DOUBLE PRECISION,   -- log(city_pop)
    is_rural              BOOLEAN,            -- city_pop < 50000

    -- Velocity features (rolling windows)
    tx_count_1h           INTEGER,       -- txns by same customer in last 1h
    tx_count_24h          INTEGER,       -- txns by same customer in last 24h
    tx_amount_1h          NUMERIC(12,2), -- total spent in last 1h
    tx_amount_24h         NUMERIC(12,2), -- total spent in last 24h
    amt_zscore            DOUBLE PRECISION,   -- z-score vs customer historical avg

    -- Category features
    category_encoded      INTEGER,       -- label encoded category
    is_online             BOOLEAN,       -- category ends in _net

    -- Customer features
    gender_encoded        INTEGER,       -- 0=F, 1=M
    age_group_encoded     INTEGER,

    -- Merchant risk (from historical)
    merchant_fraud_rate   DOUBLE PRECISION,   -- historical fraud % at merchant
    category_fraud_rate   DOUBLE PRECISION,   -- historical fraud % in category

    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ML risk scores (written by ml/predict.py)
CREATE TABLE IF NOT EXISTS gold.risk_scores (
    trans_id              BIGINT PRIMARY KEY REFERENCES clean.transactions(trans_id),
    trans_num             TEXT NOT NULL,
    risk_score            INTEGER NOT NULL,   -- 0-100
    fraud_probability     DOUBLE PRECISION,  -- raw model output 0.0-1.0
    risk_tier             TEXT,              -- 'low','medium','high','critical'
    top_shap_features     JSONB,             -- top 3 SHAP features for explainability
    scored_at             TIMESTAMPTZ DEFAULT NOW()
);

-- Daily KPI aggregation (dashboard performance page)
CREATE TABLE IF NOT EXISTS gold.kpi_daily (
    date                  DATE PRIMARY KEY,
    gross_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    approved_count        INTEGER,
    declined_count        INTEGER,
    fraud_count           INTEGER,
    chargeback_count      INTEGER,
    approval_rate         NUMERIC(5,4),
    fraud_rate            NUMERIC(8,6),
    net_volume            NUMERIC(15,2),      -- gross - fraud - fees
    processing_fees       NUMERIC(12,2),
    unique_customers      INTEGER,
    repeat_customers      INTEGER,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Merchant-level stats
CREATE TABLE IF NOT EXISTS gold.merchant_stats (
    merchant              TEXT PRIMARY KEY,
    category              TEXT,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    fraud_count           INTEGER,
    fraud_rate            NUMERIC(8,6),
    chargeback_count      INTEGER,
    approval_rate         NUMERIC(5,4),
    risk_score_avg        NUMERIC(6,2),
    first_seen            DATE,
    last_seen             DATE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Category-level stats
CREATE TABLE IF NOT EXISTS gold.category_stats (
    category              TEXT PRIMARY KEY,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    fraud_rate            NUMERIC(8,6),
    approval_rate         NUMERIC(5,4),
    pct_of_volume         NUMERIC(5,4),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Fraud heatmap (hour × day_of_week)
CREATE TABLE IF NOT EXISTS gold.fraud_heatmap (
    hour_of_day           INTEGER,
    day_of_week           INTEGER,
    total_transactions    INTEGER,
    fraud_count           INTEGER,
    fraud_rate            NUMERIC(8,6),
    avg_risk_score        NUMERIC(6,2),
    PRIMARY KEY (hour_of_day, day_of_week)
);

-- Payout history (bi-weekly buckets)
CREATE TABLE IF NOT EXISTS gold.payout_history (
    payout_id             BIGSERIAL PRIMARY KEY,
    payout_date           DATE,
    gross_amount          NUMERIC(15,2),
    interchange_fee       NUMERIC(12,2),
    processing_fee        NUMERIC(12,2),
    network_fee           NUMERIC(12,2),
    scheme_fee            NUMERIC(12,2),
    net_payout            NUMERIC(15,2),
    transaction_count     INTEGER,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- State-level geographic stats
CREATE TABLE IF NOT EXISTS gold.state_stats (
    state                 TEXT PRIMARY KEY,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    fraud_rate            NUMERIC(8,6),
    avg_ticket            NUMERIC(10,2),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector embeddings for RAG
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS gold.embeddings (
    id                    BIGSERIAL PRIMARY KEY,
    doc_type              TEXT NOT NULL,   -- 'transaction','merchant_summary','daily_report'
    doc_id                TEXT NOT NULL,   -- trans_num or merchant name or date
    content               TEXT NOT NULL,   -- the text that was embedded
    embedding             vector(1536),    -- text-embedding-3-small dimension
    metadata              JSONB,           -- arbitrary key-value for filtering
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_embeddings_type    ON gold.embeddings(doc_type);
CREATE INDEX idx_embeddings_doc_id  ON gold.embeddings(doc_id);
CREATE INDEX idx_embeddings_hnsw    ON gold.embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

---

## ETL Data Flow — Column by Column

### Bronze → Silver Transforms

| Raw Column | Silver Action | Silver Column |
|---|---|---|
| `trans_date_trans_time` | Parse to TIMESTAMPTZ | `trans_at` |
| `cc_num` | **DROP** (PII) | — |
| `merchant` | Trim whitespace, strip `fraud_` prefix | `merchant` |
| `category` | Keep as-is (14 categories) | `category` |
| `amt` | Cast to NUMERIC(12,2) | `amt` |
| `first`, `last` | **DROP** (PII) | — |
| `gender` | Keep M/F | `gender` |
| `street` | **DROP** (PII) | — |
| `city` | Title case | `city` |
| `state` | Uppercase | `state` |
| `zip` | **DROP** (unnecessary) | — |
| `lat` | Cast to DOUBLE | `cust_lat` |
| `long` | Cast to DOUBLE | `cust_long` |
| `city_pop` | Cast to INTEGER | `city_pop` |
| `job` | Map to 10 job categories | `job_category` |
| `dob` | Compute age → bucket | `age_group` |
| `trans_num` | Keep as unique key | `trans_num` |
| `unix_time` | **DROP** (redundant) | — |
| `merch_lat` | Cast to DOUBLE | `merch_lat` |
| `merch_long` | Cast to DOUBLE | `merch_long` |
| `is_fraud` | Cast to BOOLEAN | `is_fraud` |
| — | **Faker**: random weighted | `card_network` |
| — | **Faker**: random 4 digits | `card_last4` |
| — | **Faker**: ISO 8583 code | `decline_code` |
| — | **Faker**: T+1/T+2/T+3 | `settlement_date` |
| — | **Faker**: 150-300ms | `auth_latency_ms` |
| — | Derived from decline_code | `txn_status` |
| — | **Faker**: 8% of fraud rows | `chargeback_date` |

### Silver → Gold Feature Engineering

| Feature | Formula |
|---|---|
| `hour_of_day` | `EXTRACT(HOUR FROM trans_at)` |
| `day_of_week` | `EXTRACT(DOW FROM trans_at)` |
| `is_weekend` | `day_of_week IN (0,6)` |
| `geo_distance_km` | Haversine(cust_lat/long, merch_lat/long) |
| `city_pop_log` | `LOG(city_pop + 1)` |
| `is_rural` | `city_pop < 50000` |
| `tx_count_1h` | Window: COUNT over 1h per customer |
| `tx_count_24h` | Window: COUNT over 24h per customer |
| `tx_amount_1h` | Window: SUM(amt) over 1h per customer |
| `amt_zscore` | `(amt - mean) / std` per customer |
| `is_online` | `category LIKE '%_net'` |
| `merchant_fraud_rate` | Historical fraud% per merchant |
| `category_fraud_rate` | Historical fraud% per category |

---

## Merchant Categories (14 in dataset)

```
grocery_pos    grocery_net    shopping_pos   shopping_net
food_dining    gas_transport  entertainment  travel
health_fitness home           kids_pets      personal_care
misc_pos       misc_net
```

Map to display names in `config/settings.py`:
```python
CATEGORY_DISPLAY = {
    "grocery_pos":    "Grocery (In-store)",
    "grocery_net":    "Grocery (Online)",
    "shopping_pos":   "Shopping (In-store)",
    "shopping_net":   "Shopping (Online)",
    "food_dining":    "Food & Dining",
    "gas_transport":  "Gas & Transport",
    "entertainment":  "Entertainment",
    "travel":         "Travel",
    "health_fitness": "Health & Fitness",
    "home":           "Home",
    "kids_pets":      "Kids & Pets",
    "personal_care":  "Personal Care",
    "misc_pos":       "Misc (In-store)",
    "misc_net":       "Misc (Online)",
}
```

---

## Faker Enrichment Rules

### card_network — assign by market share weights
```python
CARD_NETWORK_WEIGHTS = {
    "Visa":       0.44,
    "Mastercard": 0.31,
    "Amex":       0.12,
    "ACH":        0.09,
    "Other":      0.04,
}
```

### txn_status — derived logic
```python
# For is_fraud=True rows: 92% approved (slipped through), 8% flagged
# For is_fraud=False rows: 97.3% approved, 2.7% declined
# Declined rows get a decline_code, approved/flagged do not
```

### decline_code — ISO 8583 weighted distribution
```python
DECLINE_CODES = {
    "51": ("Insufficient funds",  0.38),
    "05": ("Do not honour",       0.24),
    "14": ("Invalid card number", 0.16),
    "41": ("Lost card",           0.09),
    "43": ("Stolen card",         0.05),
    "59": ("Suspected fraud",     0.08),
}
```

### chargeback — 8% of fraud rows
```python
# chargeback_date = trans_at + random 30-90 days
# chargeback_reason: weighted from
#   "Item not received" 35%
#   "Unauthorized transaction" 40%
#   "Item not as described" 15%
#   "Duplicate charge" 10%
```

### settlement_date — T+1/T+2/T+3
```python
# Visa/Mastercard: T+1 (60%), T+2 (40%)
# Amex: T+2 (50%), T+3 (50%)
# ACH: T+3 (100%)
```

### auth_latency_ms
```python
# Approved: normal distribution mean=180ms, std=30ms
# Declined: mean=240ms, std=40ms  (extra checks)
# Fraud: mean=160ms, std=20ms  (fast pass-through, flag later)
```

### processing fee rates
```python
FEE_RATES = {
    "Visa":       0.0215,   # interchange + processing
    "Mastercard": 0.0220,
    "Amex":       0.0350,
    "ACH":        0.0080,
    "Other":      0.0250,
}
```

---

## Dashboard Pages — What Each Queries

### Page 1: Overview
- `gold.kpi_daily` — last row for KPI cards
- `gold.kpi_daily` last 7 days — sparklines
- `gold.merchant_stats` ORDER BY total_volume DESC LIMIT 5
- `clean.transactions` last 20 rows JOIN `gold.risk_scores`

### Page 2: Transaction Explorer
- `clean.transactions` JOIN `gold.risk_scores` — filterable table
- Filters: date range, category, state, status, risk tier, min/max amount

### Page 3: Performance
- `gold.kpi_daily` — revenue line chart (30d)
- `gold.category_stats` — category bar chart
- `gold.state_stats` — geographic breakdown
- `clean.customers` GROUP BY age_group, gender — demographics

### Page 4: Fraud & Risk
- `gold.fraud_heatmap` — heatmap grid
- `gold.risk_scores` — risk distribution histogram
- `clean.transactions` WHERE is_fraud=TRUE — fraud transaction table
- `gold.merchant_stats` ORDER BY fraud_rate DESC LIMIT 10

### Page 5: Payouts
- `gold.payout_history` — payout bar chart
- `gold.kpi_daily` — fee breakdown by type
- `clean.transactions` GROUP BY card_network — fee by network

### Page 6: AI Analyst
- `rag/agent.py` — LangChain agent with pgvector retrieval
- Suggested prompts wired to agent tools

---

## Docker Compose

```yaml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: payments_db
      POSTGRES_USER: payments_user
      POSTGRES_PASSWORD: payments_pass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./config/schema.sql:/docker-entrypoint-initdb.d/schema.sql
volumes:
  pgdata:
```

---

## Performance Notes

- Load Bronze in chunks of 50,000 rows using `pd.read_csv(chunksize=50000)`
- Silver transforms run as SQL INSERT...SELECT — do not load into pandas
- Gold aggregations are INSERT...SELECT from Silver — run after full Silver load
- ML training uses the combined 1.85M rows — expect ~3-5 min on laptop
- Embedding generation: batch 100 texts per API call, ~18,500 API calls for all merchants
  (generate merchant-level summaries only, not per-transaction embeddings — 800 merchants)
- pgvector HNSW index builds after all embeddings are inserted
