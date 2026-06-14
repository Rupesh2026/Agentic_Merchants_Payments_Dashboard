-- sql/gold_features.sql
-- GOLD layer — ML feature engineering (Spark SQL window functions).
--
-- Input  : temp view `silver`  (enriched clean.transactions)
-- Output : one row per transaction with the 19 engineered model features.
--
-- Velocity uses time-range windows (seconds) over a customer proxy key
-- (city_state_gender, since cc_num is dropped). day_of_week is 0=Sun..6=Sat to
-- match the Postgres EXTRACT(DOW) convention used elsewhere.

WITH base AS (
    SELECT
        trans_id, trans_num, trans_at, amt, is_fraud,
        merchant, category, cust_lat, cust_long, merch_lat, merch_long,
        city_pop, gender, age_group,
        concat(coalesce(city, ''), '_', coalesce(state, ''), '_', coalesce(gender, '')) AS cust_key,
        cast(unix_timestamp(trans_at) AS long)  AS ts_sec,
        hour(trans_at)                          AS hour_of_day,
        pmod(dayofweek(trans_at) - 1, 7)        AS day_of_week,   -- 0=Sun..6=Sat
        month(trans_at)                         AS month
    FROM silver
)
SELECT
    trans_id,
    trans_num,
    trans_at,
    cast(amt AS decimal(12,2))                              AS amt,
    is_fraud,

    -- Temporal
    cast(hour_of_day AS smallint)                           AS hour_of_day,
    cast(day_of_week AS smallint)                           AS day_of_week,
    (day_of_week IN (0, 6))                                 AS is_weekend,
    cast(month AS smallint)                                 AS month,

    -- Geographic (Haversine km between customer & merchant)
    CASE WHEN cust_lat IS NOT NULL AND merch_lat IS NOT NULL THEN
        6371.0 * 2 * asin(sqrt(
            power(sin(radians(merch_lat - cust_lat) / 2), 2) +
            cos(radians(cust_lat)) * cos(radians(merch_lat)) *
            power(sin(radians(merch_long - cust_long) / 2), 2)
        ))
    END                                                     AS geo_distance_km,
    ln(greatest(coalesce(city_pop, 1), 1))                 AS city_pop_log,
    (coalesce(city_pop, 0) < 50000)                        AS is_rural,

    -- Velocity (rolling windows per customer proxy; exclude current row via -1/-amt)
    cast(count(*) OVER w1  - 1 AS int)                      AS tx_count_1h,
    cast(count(*) OVER w24 - 1 AS int)                      AS tx_count_24h,
    cast(sum(amt) OVER w1  - amt AS decimal(12,2))          AS tx_amount_1h,
    cast(sum(amt) OVER w24 - amt AS decimal(12,2))          AS tx_amount_24h,
    CASE WHEN stddev_samp(amt) OVER wc > 0
         THEN (amt - avg(amt) OVER wc) / stddev_samp(amt) OVER wc
         ELSE 0.0
    END                                                     AS amt_zscore,

    -- Category
    cast(CASE category
        WHEN 'grocery_pos'    THEN 0
        WHEN 'grocery_net'    THEN 1
        WHEN 'shopping_pos'   THEN 2
        WHEN 'shopping_net'   THEN 3
        WHEN 'food_dining'    THEN 4
        WHEN 'gas_transport'  THEN 5
        WHEN 'entertainment'  THEN 6
        WHEN 'travel'         THEN 7
        WHEN 'health_fitness' THEN 8
        WHEN 'home'           THEN 9
        WHEN 'kids_pets'      THEN 10
        WHEN 'personal_care'  THEN 11
        WHEN 'misc_pos'       THEN 12
        WHEN 'misc_net'       THEN 13
        ELSE 12
    END AS smallint)                                        AS category_encoded,
    (category RLIKE '_net$')                                AS is_online,

    -- Customer
    cast(CASE gender WHEN 'F' THEN 0 WHEN 'M' THEN 1 ELSE -1 END AS smallint) AS gender_encoded,
    cast(CASE age_group
        WHEN '18-25' THEN 0
        WHEN '26-35' THEN 1
        WHEN '36-50' THEN 2
        WHEN '51-65' THEN 3
        WHEN '66+'   THEN 4
        ELSE 2
    END AS smallint)                                        AS age_group_encoded,

    -- Historical risk rates (computed over the whole dataset)
    (sum(cast(is_fraud AS int)) OVER wm)   / (count(*) OVER wm)   AS merchant_fraud_rate,
    (sum(cast(is_fraud AS int)) OVER wcat) / (count(*) OVER wcat) AS category_fraud_rate
FROM base
WINDOW
    w1   AS (PARTITION BY cust_key ORDER BY ts_sec RANGE BETWEEN 3600 PRECEDING AND CURRENT ROW),
    w24  AS (PARTITION BY cust_key ORDER BY ts_sec RANGE BETWEEN 86400 PRECEDING AND CURRENT ROW),
    wc   AS (PARTITION BY cust_key),
    wm   AS (PARTITION BY merchant),
    wcat AS (PARTITION BY category)
