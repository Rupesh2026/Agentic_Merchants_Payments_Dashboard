-- sql/silver_enrich.sql
-- SILVER layer (2/2) — Faker-style operational enrichment (Spark SQL).
--
-- Input  : temp view `silver_clean`  (output of silver_transforms.sql)
-- Output : the cleaned columns + 10 enriched fields. All randomness is DERIVED
--          from xxhash64(trans_num, '<salt>') so it is fully deterministic and
--          reproducible regardless of Spark partitioning (no global RNG).
--
-- Distributions mirror config/settings.py:
--   card_network  Visa .44 / MC .31 / Amex .12 / ACH .09 / Other .04
--   txn_status    fraud → 8% flagged else approved; clean → 2.7% declined else approved
--   decline_code  ISO-8583 weighted (51/05/14/41/43/59)
--   auth_latency  Box–Muller normal by status, clipped 80..800 ms
--   settlement    T+1/T+2/T+3 by network
--   chargeback    8% of fraud rows, +30..90 days, weighted reason

WITH u AS (
    SELECT
        sc.*,
        (pmod(xxhash64(trans_num, 'net'),      1000000) / 1000000.0)        AS u_net,
        (pmod(xxhash64(trans_num, 'status'),   1000000) / 1000000.0)        AS u_status,
        (pmod(xxhash64(trans_num, 'decline'),  1000000) / 1000000.0)        AS u_decline,
        ((pmod(xxhash64(trans_num, 'lat1'),    1000000) + 1) / 1000001.0)   AS u_lat1,
        ((pmod(xxhash64(trans_num, 'lat2'),    1000000) + 1) / 1000001.0)   AS u_lat2,
        (pmod(xxhash64(trans_num, 'settle'),   1000000) / 1000000.0)        AS u_settle,
        (pmod(xxhash64(trans_num, 'cbflag'),   1000000) / 1000000.0)        AS u_cbflag,
        (pmod(xxhash64(trans_num, 'cbdays'),   1000000) / 1000000.0)        AS u_cbdays,
        (pmod(xxhash64(trans_num, 'cbreason'), 1000000) / 1000000.0)        AS u_cbreason,
        (pmod(xxhash64(trans_num, 'last4'),    9000) + 1000)                AS last4_num
    FROM silver_clean sc
),
s AS (
    SELECT
        u.*,
        CASE
            WHEN u_net < 0.44 THEN 'Visa'
            WHEN u_net < 0.75 THEN 'Mastercard'
            WHEN u_net < 0.87 THEN 'Amex'
            WHEN u_net < 0.96 THEN 'ACH'
            ELSE 'Other'
        END                                                AS card_network,
        lpad(cast(last4_num AS string), 4, '0')            AS card_last4,
        CASE
            WHEN is_fraud THEN CASE WHEN u_status < 0.08  THEN 'flagged'  ELSE 'approved' END
            ELSE              CASE WHEN u_status < 0.027 THEN 'declined' ELSE 'approved' END
        END                                                AS txn_status
    FROM u
)
SELECT
    trans_id, trans_num, trans_at, merchant, category, merch_lat, merch_long,
    amt, is_fraud, gender, age_group, city, state, city_pop, job_category,
    cust_lat, cust_long,

    card_network,
    card_last4,
    txn_status,

    CASE WHEN txn_status = 'declined' THEN
        CASE
            WHEN u_decline < 0.38 THEN '51'
            WHEN u_decline < 0.62 THEN '05'
            WHEN u_decline < 0.78 THEN '14'
            WHEN u_decline < 0.87 THEN '41'
            WHEN u_decline < 0.92 THEN '43'
            ELSE '59'
        END
    END                                                    AS decline_code,

    CASE WHEN txn_status = 'declined' THEN
        CASE
            WHEN u_decline < 0.38 THEN 'Insufficient funds'
            WHEN u_decline < 0.62 THEN 'Do not honour'
            WHEN u_decline < 0.78 THEN 'Invalid card number'
            WHEN u_decline < 0.87 THEN 'Lost card'
            WHEN u_decline < 0.92 THEN 'Stolen card'
            ELSE 'Suspected fraud'
        END
    END                                                    AS decline_reason,

    -- Box–Muller normal latency by status, clipped to [80, 800] ms
    cast(greatest(80, least(800, round(
        (CASE txn_status WHEN 'approved' THEN 180 WHEN 'declined' THEN 240 WHEN 'flagged' THEN 160 ELSE 180 END)
        + (CASE txn_status WHEN 'approved' THEN 30 WHEN 'declined' THEN 40 WHEN 'flagged' THEN 20 ELSE 30 END)
          * (sqrt(-2.0 * ln(u_lat1)) * cos(2.0 * 3.141592653589793 * u_lat2))
    ))) AS int)                                            AS auth_latency_ms,

    -- settlement T+n by network
    date_add(to_date(trans_at),
        CASE
            WHEN card_network IN ('Visa', 'Mastercard') THEN CASE WHEN u_settle < 0.60 THEN 1 ELSE 2 END
            WHEN card_network = 'Amex'                   THEN CASE WHEN u_settle < 0.50 THEN 2 ELSE 3 END
            WHEN card_network = 'ACH'                    THEN 3
            ELSE                                              CASE WHEN u_settle < 0.50 THEN 2 ELSE 3 END
        END
    )                                                      AS settlement_date,

    (is_fraud AND u_cbflag < 0.08)                         AS has_chargeback,

    CASE WHEN (is_fraud AND u_cbflag < 0.08)
         THEN date_add(to_date(trans_at), cast(30 + floor(u_cbdays * 61) AS int))
    END                                                    AS chargeback_date,

    CASE WHEN (is_fraud AND u_cbflag < 0.08) THEN
        CASE
            WHEN u_cbreason < 0.40 THEN 'Unauthorized transaction'
            WHEN u_cbreason < 0.75 THEN 'Item not received'
            WHEN u_cbreason < 0.90 THEN 'Item not as described'
            ELSE 'Duplicate charge'
        END
    END                                                    AS chargeback_reason,

    source_file
FROM s
