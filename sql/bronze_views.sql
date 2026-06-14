-- sql/bronze_views.sql
-- BRONZE layer — Spark SQL view over the raw Sparkov CSVs.
--
-- The Bronze loader (etl/bronze/loader.py) reads the CSVs as all-strings and
-- registers them as the temp view `bronze`. This file documents the exact
-- column projection used (the leading unnamed CSV index column is dropped) and
-- can be used to re-derive the Bronze view from a registered `raw_csv` view.
--
-- Input  : temp view `raw_csv`  (all original CSV columns, every value a string)
-- Output : the 22 source columns + source_file, nothing typed or transformed.

SELECT
    trans_date_trans_time,
    cc_num,
    merchant,
    category,
    amt,
    first,
    last,
    gender,
    street,
    city,
    state,
    zip,
    lat,
    long,
    city_pop,
    job,
    dob,
    trans_num,
    unix_time,
    merch_lat,
    merch_long,
    is_fraud,
    source_file
FROM raw_csv
