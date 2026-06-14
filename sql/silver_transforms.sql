-- sql/silver_transforms.sql
-- SILVER layer (1/2) — clean & conform (Spark SQL).
--
-- Input  : temp view `bronze`  (raw text columns + source_file)
-- Output : cleaned, typed, PII-dropped rows with a DETERMINISTIC surrogate key
--          trans_id = abs(xxhash64(trans_num)). PII columns (first, last, street,
--          zip, cc_num) and the redundant unix_time are simply not selected.
--
-- Dedup  : keep one row per trans_num (earliest by timestamp).

WITH deduped AS (
    SELECT *
    FROM (
        SELECT
            b.*,
            row_number() OVER (
                PARTITION BY trans_num
                ORDER BY trans_date_trans_time
            ) AS rn
        FROM bronze b
        WHERE trans_num IS NOT NULL
          AND amt IS NOT NULL
    )
    WHERE rn = 1
)
SELECT
    abs(xxhash64(trans_num))                                   AS trans_id,
    trans_num,
    to_timestamp(trans_date_trans_time, 'yyyy-MM-dd HH:mm:ss') AS trans_at,

    -- Merchant: strip the Sparkov 'fraud_' prefix, trim whitespace
    trim(regexp_replace(merchant, '^fraud_', ''))             AS merchant,
    category,
    cast(merch_lat  AS double)                                AS merch_lat,
    cast(merch_long AS double)                                AS merch_long,

    cast(amt AS decimal(12,2))                                AS amt,
    (cast(is_fraud AS int) = 1)                               AS is_fraud,

    -- Customer (anonymized)
    upper(substr(gender, 1, 1))                               AS gender,

    -- age_group derived from dob (dataset ends 2020-12-31)
    CASE
        WHEN floor(datediff(date('2020-12-31'), to_date(dob)) / 365.25) BETWEEN 18 AND 25 THEN '18-25'
        WHEN floor(datediff(date('2020-12-31'), to_date(dob)) / 365.25) BETWEEN 26 AND 35 THEN '26-35'
        WHEN floor(datediff(date('2020-12-31'), to_date(dob)) / 365.25) BETWEEN 36 AND 50 THEN '36-50'
        WHEN floor(datediff(date('2020-12-31'), to_date(dob)) / 365.25) BETWEEN 51 AND 65 THEN '51-65'
        WHEN floor(datediff(date('2020-12-31'), to_date(dob)) / 365.25) >= 66            THEN '66+'
        ELSE 'Unknown'
    END                                                       AS age_group,

    initcap(city)                                             AS city,
    upper(state)                                              AS state,
    cast(city_pop AS int)                                     AS city_pop,

    -- job grouped into 10 categories (first keyword match wins)
    CASE
        WHEN lower(job) RLIKE 'engineer|developer|programmer|analyst|software|information technology|tech' THEN 'Technology'
        WHEN lower(job) RLIKE 'doctor|nurse|medical|health|physician|therapist|dental'                     THEN 'Healthcare'
        WHEN lower(job) RLIKE 'accountant|banker|financial|broker|trader|economist'                        THEN 'Finance'
        WHEN lower(job) RLIKE 'teacher|professor|lecturer|educator|instructor|tutor'                       THEN 'Education'
        WHEN lower(job) RLIKE 'lawyer|attorney|paralegal|judge|solicitor'                                  THEN 'Legal'
        WHEN lower(job) RLIKE 'manager|director|executive|ceo|officer|administrator'                       THEN 'Management'
        WHEN lower(job) RLIKE 'driver|clerk|assistant|worker|operator|technician'                          THEN 'Service'
        WHEN lower(job) RLIKE 'sales|marketing|representative|agent|consultant'                            THEN 'Sales'
        WHEN lower(job) RLIKE 'designer|artist|writer|journalist|architect'                                THEN 'Creative'
        ELSE 'Other'
    END                                                       AS job_category,

    cast(lat  AS double)                                      AS cust_lat,
    cast(long AS double)                                      AS cust_long,
    source_file
FROM deduped
WHERE to_timestamp(trans_date_trans_time, 'yyyy-MM-dd HH:mm:ss') IS NOT NULL
  AND merchant IS NOT NULL
  AND category IS NOT NULL
  AND is_fraud IS NOT NULL
