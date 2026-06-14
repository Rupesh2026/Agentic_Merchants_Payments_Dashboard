-- sql/gold_aggregations.sql
-- GOLD layer — KPI aggregation queries (Spark SQL).
--
-- Input temp views:
--   clean_transactions  — enriched Silver rows
--   risk_scores         — gold.risk_scores read back from Supabase (may be empty
--                         on the first pass, before the ML model has scored)
--
-- Each section below is one query, delimited by `-- @@name:`. etl/gold/aggregations.py
-- runs each, TRUNCATEs the matching Supabase table, then appends the result via JDBC.
-- Column aliases match the target gold.* table columns exactly.

-- @@name: kpi_daily
WITH daily AS (
    SELECT
        to_date(trans_at)                                                   AS date,
        sum(amt)                                                            AS gross_volume,
        count(*)                                                            AS total_transactions,
        avg(amt)                                                            AS avg_ticket,
        sum(CASE WHEN txn_status = 'approved' THEN 1 ELSE 0 END)            AS approved_count,
        sum(CASE WHEN txn_status = 'declined' THEN 1 ELSE 0 END)            AS declined_count,
        sum(cast(is_fraud AS int))                                          AS fraud_count,
        sum(cast(has_chargeback AS int))                                    AS chargeback_count,
        sum(CASE WHEN txn_status = 'approved' THEN 1.0 ELSE 0 END) / count(*) AS approval_rate,
        sum(cast(is_fraud AS int)) / count(*)                              AS fraud_rate,
        sum(amt * CASE card_network
                      WHEN 'Visa'       THEN 0.0215
                      WHEN 'Mastercard' THEN 0.0220
                      WHEN 'Amex'       THEN 0.0350
                      WHEN 'ACH'        THEN 0.0080
                      ELSE 0.0250 END)                                      AS processing_fees,
        count(DISTINCT concat(city, state, gender))                        AS unique_customers
    FROM clean_transactions
    GROUP BY to_date(trans_at)
),
topcat AS (
    SELECT date, top_category FROM (
        SELECT
            to_date(trans_at) AS date,
            category          AS top_category,
            row_number() OVER (PARTITION BY to_date(trans_at) ORDER BY sum(amt) DESC) AS rn
        FROM clean_transactions
        GROUP BY to_date(trans_at), category
    ) WHERE rn = 1
),
repeat_keys AS (
    SELECT concat(city, state, gender) AS ckey
    FROM clean_transactions
    GROUP BY concat(city, state, gender)
    HAVING count(*) > 1
),
repeats AS (
    SELECT to_date(trans_at) AS date,
           count(DISTINCT concat(city, state, gender)) AS repeat_customers
    FROM clean_transactions
    WHERE concat(city, state, gender) IN (SELECT ckey FROM repeat_keys)
    GROUP BY to_date(trans_at)
)
SELECT
    d.date,
    d.gross_volume,
    d.total_transactions,
    d.avg_ticket,
    d.approved_count,
    d.declined_count,
    d.fraud_count,
    d.chargeback_count,
    d.approval_rate,
    d.fraud_rate,
    d.gross_volume - coalesce(d.processing_fees, 0)  AS net_volume,
    coalesce(d.processing_fees, 0)                   AS processing_fees,
    d.unique_customers,
    coalesce(r.repeat_customers, 0)                  AS repeat_customers,
    t.top_category
FROM daily d
LEFT JOIN topcat  t ON d.date = t.date
LEFT JOIN repeats r ON d.date = r.date

-- @@name: merchant_stats
SELECT
    ct.merchant,
    ct.category,
    sum(ct.amt)                                                         AS total_volume,
    count(*)                                                            AS total_transactions,
    avg(ct.amt)                                                         AS avg_ticket,
    sum(cast(ct.is_fraud AS int))                                       AS fraud_count,
    sum(cast(ct.is_fraud AS int)) / count(*)                           AS fraud_rate,
    sum(cast(ct.has_chargeback AS int))                                AS chargeback_count,
    sum(CASE WHEN ct.txn_status = 'approved' THEN 1.0 ELSE 0 END) / count(*) AS approval_rate,
    coalesce(avg(rs.risk_score), 0)                                    AS risk_score_avg,
    min(to_date(ct.trans_at))                                          AS first_seen,
    max(to_date(ct.trans_at))                                          AS last_seen
FROM clean_transactions ct
LEFT JOIN risk_scores rs ON ct.trans_id = rs.trans_id
GROUP BY ct.merchant, ct.category

-- @@name: category_stats
WITH totals AS (SELECT sum(amt) AS grand FROM clean_transactions)
SELECT
    category,
    sum(amt)                                                           AS total_volume,
    count(*)                                                           AS total_transactions,
    avg(amt)                                                           AS avg_ticket,
    sum(cast(is_fraud AS int)) / count(*)                             AS fraud_rate,
    sum(CASE WHEN txn_status = 'approved' THEN 1.0 ELSE 0 END) / count(*) AS approval_rate,
    sum(amt) / (SELECT grand FROM totals)                            AS pct_of_volume
FROM clean_transactions
GROUP BY category

-- @@name: fraud_heatmap
SELECT
    cast(hour(ct.trans_at) AS smallint)                  AS hour_of_day,
    cast(pmod(dayofweek(ct.trans_at) - 1, 7) AS smallint) AS day_of_week,
    count(*)                                             AS total_transactions,
    sum(cast(ct.is_fraud AS int))                        AS fraud_count,
    sum(cast(ct.is_fraud AS int)) / count(*)            AS fraud_rate,
    coalesce(avg(rs.risk_score), 0)                      AS avg_risk_score
FROM clean_transactions ct
LEFT JOIN risk_scores rs ON ct.trans_id = rs.trans_id
GROUP BY hour(ct.trans_at), pmod(dayofweek(ct.trans_at) - 1, 7)

-- @@name: state_stats
SELECT
    state,
    sum(amt)                                  AS total_volume,
    count(*)                                  AS total_transactions,
    sum(cast(is_fraud AS int)) / count(*)    AS fraud_rate,
    avg(amt)                                  AS avg_ticket,
    sum(cast(is_fraud AS int))                AS fraud_count
FROM clean_transactions
WHERE state IS NOT NULL
GROUP BY state

-- @@name: payout_history
WITH approved AS (
    SELECT date_trunc('week', settlement_date) AS payout_week, amt, card_network
    FROM clean_transactions
    WHERE txn_status = 'approved' AND settlement_date IS NOT NULL
),
calc AS (
    SELECT
        payout_week,
        sum(amt)  AS gross,
        count(*)  AS tx_count,
        sum(CASE WHEN card_network = 'Visa' THEN amt * 0.0175 ELSE 0 END) AS interchange,
        sum(CASE card_network
                 WHEN 'Visa'       THEN amt * 0.0040
                 WHEN 'Mastercard' THEN amt * 0.0045
                 WHEN 'Amex'       THEN amt * 0.0100
                 WHEN 'ACH'        THEN amt * 0.0030
                 ELSE amt * 0.0050 END)                                   AS processing,
        sum(amt) * 0.0020 AS network,
        sum(amt) * 0.0008 AS scheme
    FROM approved
    GROUP BY payout_week
)
SELECT
    to_date(payout_week)                                       AS payout_date,
    gross                                                      AS gross_amount,
    interchange                                                AS interchange_fee,
    processing                                                 AS processing_fee,
    network                                                    AS network_fee,
    scheme                                                     AS scheme_fee,
    gross - interchange - processing - network - scheme        AS net_payout,
    tx_count                                                   AS transaction_count
FROM calc
ORDER BY payout_week
