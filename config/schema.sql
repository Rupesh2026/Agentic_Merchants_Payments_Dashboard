-- config/schema.sql
-- Complete PostgreSQL schema for Payments Merchant Dashboard (Supabase).
--
-- Apply it ONE of these ways:
--   1. Supabase Dashboard → SQL Editor → New query → paste this file → Run
--   2. python -m config.db --schema        (uses DATABASE_URL from .env)
--   3. psql "$DATABASE_URL" -f config/schema.sql
--
-- pgvector ('vector') and pg_trgm ship with Supabase; the CREATE EXTENSION
-- lines below just enable them (idempotent).

-- ─────────────────────────────────────────────────────────────────────────────
-- EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- for text search on merchant names

-- ─────────────────────────────────────────────────────────────────────────────
-- BRONZE — schema: raw
-- Exact copy of source data. Append-only. No transforms. All columns as TEXT.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.transactions CASCADE;
CREATE TABLE raw.transactions (
    id                    BIGSERIAL PRIMARY KEY,
    trans_date_trans_time TEXT,
    cc_num                TEXT,
    merchant              TEXT,
    category              TEXT,
    amt                   TEXT,
    first                 TEXT,
    last                  TEXT,
    gender                TEXT,
    street                TEXT,
    city                  TEXT,
    state                 TEXT,
    zip                   TEXT,
    lat                   TEXT,
    long                  TEXT,
    city_pop              TEXT,
    job                   TEXT,
    dob                   TEXT,
    trans_num             TEXT,
    unix_time             TEXT,
    merch_lat             TEXT,
    merch_long            TEXT,
    is_fraud              TEXT,
    source_file           TEXT,
    loaded_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_trans_num  ON raw.transactions(trans_num);
CREATE INDEX IF NOT EXISTS idx_raw_loaded_at  ON raw.transactions(loaded_at);
CREATE INDEX IF NOT EXISTS idx_raw_source     ON raw.transactions(source_file);

-- ─────────────────────────────────────────────────────────────────────────────
-- SILVER — schema: clean
-- Cleaned, typed, PII-dropped, Faker-enriched
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS clean;

DROP TABLE IF EXISTS clean.transactions CASCADE;
CREATE TABLE clean.transactions (
    -- Core identifiers
    -- trans_id is a DETERMINISTIC surrogate key computed in Spark as
    -- abs(xxhash64(trans_num)) so the Gold layer can join features without a
    -- DB round-trip and the whole pipeline stays idempotent across re-runs.
    trans_id              BIGINT PRIMARY KEY,
    trans_num             TEXT UNIQUE NOT NULL,
    trans_at              TIMESTAMPTZ NOT NULL,

    -- Merchant
    merchant              TEXT NOT NULL,
    category              TEXT NOT NULL,
    merch_lat             DOUBLE PRECISION,
    merch_long            DOUBLE PRECISION,

    -- Transaction amounts
    amt                   NUMERIC(12,2) NOT NULL,
    is_fraud              BOOLEAN NOT NULL,

    -- Customer (anonymized — no PII)
    gender                CHAR(1),
    age_group             TEXT,
    city                  TEXT,
    state                 TEXT,
    city_pop              INTEGER,
    job_category          TEXT,
    cust_lat              DOUBLE PRECISION,
    cust_long             DOUBLE PRECISION,

    -- Faker-enriched operational fields
    card_network          TEXT,
    card_last4            CHAR(4),
    txn_status            TEXT          CHECK (txn_status IN ('approved','declined','flagged')),
    decline_code          TEXT,
    decline_reason        TEXT,
    auth_latency_ms       INTEGER,
    settlement_date       DATE,

    -- Chargeback info (populated for ~8% of fraud rows)
    has_chargeback        BOOLEAN DEFAULT FALSE,
    chargeback_date       DATE,
    chargeback_reason     TEXT,

    -- Audit
    source_file           TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clean_trans_at     ON clean.transactions(trans_at);
CREATE INDEX IF NOT EXISTS idx_clean_merchant     ON clean.transactions(merchant);
CREATE INDEX IF NOT EXISTS idx_clean_category     ON clean.transactions(category);
CREATE INDEX IF NOT EXISTS idx_clean_is_fraud     ON clean.transactions(is_fraud);
CREATE INDEX IF NOT EXISTS idx_clean_state        ON clean.transactions(state);
CREATE INDEX IF NOT EXISTS idx_clean_txn_status   ON clean.transactions(txn_status);
CREATE INDEX IF NOT EXISTS idx_clean_card_network ON clean.transactions(card_network);
CREATE INDEX IF NOT EXISTS idx_clean_settlement   ON clean.transactions(settlement_date);
CREATE INDEX IF NOT EXISTS idx_clean_chargeback   ON clean.transactions(has_chargeback) WHERE has_chargeback = TRUE;

-- Merchant dimension
DROP TABLE IF EXISTS clean.merchants CASCADE;
CREATE TABLE clean.merchants (
    merchant_id     BIGSERIAL PRIMARY KEY,
    merchant_name   TEXT UNIQUE NOT NULL,
    category        TEXT NOT NULL,
    merch_lat       DOUBLE PRECISION,
    merch_long      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_merchants_name ON clean.merchants USING gin(merchant_name gin_trgm_ops);

-- ─────────────────────────────────────────────────────────────────────────────
-- GOLD — schema: gold
-- ML features, KPI aggregations, risk scores, embeddings
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS gold;

-- ML feature table
DROP TABLE IF EXISTS gold.features CASCADE;
CREATE TABLE gold.features (
    trans_id              BIGINT PRIMARY KEY REFERENCES clean.transactions(trans_id),
    trans_num             TEXT NOT NULL,
    trans_at              TIMESTAMPTZ,
    amt                   NUMERIC(12,2),
    is_fraud              BOOLEAN,

    -- Temporal
    hour_of_day           SMALLINT,
    day_of_week           SMALLINT,
    is_weekend            BOOLEAN,
    month                 SMALLINT,

    -- Geographic
    geo_distance_km       DOUBLE PRECISION,
    city_pop_log          DOUBLE PRECISION,
    is_rural              BOOLEAN,

    -- Velocity (rolling windows)
    tx_count_1h           INTEGER,
    tx_count_24h          INTEGER,
    tx_amount_1h          NUMERIC(12,2),
    tx_amount_24h         NUMERIC(12,2),
    amt_zscore            DOUBLE PRECISION,

    -- Category
    category_encoded      SMALLINT,
    is_online             BOOLEAN,

    -- Customer
    gender_encoded        SMALLINT,
    age_group_encoded     SMALLINT,

    -- Historical risk rates
    merchant_fraud_rate   DOUBLE PRECISION,
    category_fraud_rate   DOUBLE PRECISION,

    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_features_trans_at ON gold.features(trans_at);
CREATE INDEX IF NOT EXISTS idx_features_is_fraud ON gold.features(is_fraud);

-- ML risk scores (written by ml/predict.py after model training)
DROP TABLE IF EXISTS gold.risk_scores CASCADE;
CREATE TABLE gold.risk_scores (
    trans_id              BIGINT PRIMARY KEY REFERENCES clean.transactions(trans_id),
    trans_num             TEXT NOT NULL,
    risk_score            SMALLINT NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    fraud_probability     DOUBLE PRECISION NOT NULL,
    risk_tier             TEXT CHECK (risk_tier IN ('low','medium','high','critical')),
    top_shap_features     JSONB,
    scored_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_trans_num  ON gold.risk_scores(trans_num);
CREATE INDEX IF NOT EXISTS idx_risk_score      ON gold.risk_scores(risk_score);
CREATE INDEX IF NOT EXISTS idx_risk_tier       ON gold.risk_scores(risk_tier);

-- Daily KPI aggregations
DROP TABLE IF EXISTS gold.kpi_daily CASCADE;
CREATE TABLE gold.kpi_daily (
    date                  DATE PRIMARY KEY,
    gross_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    approved_count        INTEGER,
    declined_count        INTEGER,
    fraud_count           INTEGER,
    chargeback_count      INTEGER,
    approval_rate         NUMERIC(7,6),
    fraud_rate            NUMERIC(8,7),
    net_volume            NUMERIC(15,2),
    processing_fees       NUMERIC(12,2),
    unique_customers      INTEGER,
    repeat_customers      INTEGER,
    top_category          TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Merchant-level statistics
DROP TABLE IF EXISTS gold.merchant_stats CASCADE;
CREATE TABLE gold.merchant_stats (
    merchant              TEXT PRIMARY KEY,
    category              TEXT,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    fraud_count           INTEGER,
    fraud_rate            NUMERIC(8,7),
    chargeback_count      INTEGER,
    approval_rate         NUMERIC(7,6),
    risk_score_avg        NUMERIC(6,2),
    first_seen            DATE,
    last_seen             DATE,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_merchant_stats_fraud ON gold.merchant_stats(fraud_rate DESC);
CREATE INDEX IF NOT EXISTS idx_merchant_stats_vol   ON gold.merchant_stats(total_volume DESC);

-- Category-level statistics
DROP TABLE IF EXISTS gold.category_stats CASCADE;
CREATE TABLE gold.category_stats (
    category              TEXT PRIMARY KEY,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    avg_ticket            NUMERIC(10,2),
    fraud_rate            NUMERIC(8,7),
    approval_rate         NUMERIC(7,6),
    pct_of_volume         NUMERIC(7,6),
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- Fraud heatmap (hour × day_of_week)
DROP TABLE IF EXISTS gold.fraud_heatmap CASCADE;
CREATE TABLE gold.fraud_heatmap (
    hour_of_day           SMALLINT,
    day_of_week           SMALLINT,
    total_transactions    INTEGER,
    fraud_count           INTEGER,
    fraud_rate            NUMERIC(8,7),
    avg_risk_score        NUMERIC(6,2),
    PRIMARY KEY (hour_of_day, day_of_week)
);

-- Payout history
DROP TABLE IF EXISTS gold.payout_history CASCADE;
CREATE TABLE gold.payout_history (
    payout_id             BIGSERIAL PRIMARY KEY,
    payout_date           DATE UNIQUE,
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
DROP TABLE IF EXISTS gold.state_stats CASCADE;
CREATE TABLE gold.state_stats (
    state                 TEXT PRIMARY KEY,
    total_volume          NUMERIC(15,2),
    total_transactions    INTEGER,
    fraud_rate            NUMERIC(8,7),
    avg_ticket            NUMERIC(10,2),
    fraud_count           INTEGER,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector embeddings for RAG
DROP TABLE IF EXISTS gold.embeddings CASCADE;
CREATE TABLE gold.embeddings (
    id                    BIGSERIAL PRIMARY KEY,
    doc_type              TEXT NOT NULL,
    doc_id                TEXT NOT NULL,
    content               TEXT NOT NULL,
    embedding             vector(1536),
    metadata              JSONB,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_type   ON gold.embeddings(doc_type);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc_id ON gold.embeddings(doc_id);

-- HNSW index for fast similarity search (build AFTER all embeddings inserted)
-- Run separately after rag/embeddings.py completes:
-- CREATE INDEX idx_embeddings_hnsw ON gold.embeddings
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- ─────────────────────────────────────────────────────────────────────────────
-- HELPER VIEWS — convenience queries for dashboard
-- ─────────────────────────────────────────────────────────────────────────────

-- Full transaction view (Silver + Gold risk scores)
CREATE OR REPLACE VIEW gold.v_transactions AS
SELECT
    ct.trans_id,
    ct.trans_num,
    ct.trans_at,
    ct.merchant,
    ct.category,
    ct.amt,
    ct.is_fraud,
    ct.gender,
    ct.age_group,
    ct.city,
    ct.state,
    ct.city_pop,
    ct.job_category,
    ct.card_network,
    ct.card_last4,
    ct.txn_status,
    ct.decline_code,
    ct.decline_reason,
    ct.auth_latency_ms,
    ct.settlement_date,
    ct.has_chargeback,
    ct.chargeback_date,
    ct.chargeback_reason,
    rs.risk_score,
    rs.fraud_probability,
    rs.risk_tier,
    rs.top_shap_features
FROM clean.transactions ct
LEFT JOIN gold.risk_scores rs ON ct.trans_id = rs.trans_id;

-- Latest KPI (today or most recent day)
CREATE OR REPLACE VIEW gold.v_latest_kpi AS
SELECT * FROM gold.kpi_daily
ORDER BY date DESC
LIMIT 1;

-- 7-day KPI trend
CREATE OR REPLACE VIEW gold.v_kpi_7d AS
SELECT * FROM gold.kpi_daily
ORDER BY date DESC
LIMIT 7;

-- 30-day KPI trend
CREATE OR REPLACE VIEW gold.v_kpi_30d AS
SELECT * FROM gold.kpi_daily
ORDER BY date DESC
LIMIT 30;

-- Top 10 merchants by volume
CREATE OR REPLACE VIEW gold.v_top_merchants AS
SELECT * FROM gold.merchant_stats
ORDER BY total_volume DESC
LIMIT 10;

-- High risk merchants (fraud rate > 2x industry average 0.58%)
CREATE OR REPLACE VIEW gold.v_high_risk_merchants AS
SELECT * FROM gold.merchant_stats
WHERE fraud_rate > 0.0116
ORDER BY fraud_rate DESC;

COMMENT ON TABLE raw.transactions   IS 'Bronze layer: raw CSV ingest, append-only, no transforms';
COMMENT ON TABLE clean.transactions IS 'Silver layer: cleaned, typed, PII-dropped, Faker-enriched';
COMMENT ON TABLE gold.features      IS 'Gold layer: engineered ML features per transaction';
COMMENT ON TABLE gold.risk_scores   IS 'Gold layer: XGBoost fraud scores + SHAP explanations';
COMMENT ON TABLE gold.kpi_daily     IS 'Gold layer: daily KPI aggregations for dashboard';
COMMENT ON TABLE gold.embeddings    IS 'Gold layer: pgvector embeddings for RAG agent';
