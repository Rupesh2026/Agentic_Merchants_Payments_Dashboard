"""
etl/spark_session.py — Shared SparkSession builder for the Medallion ETL.

Configures Spark (local mode) with:
  • Delta Lake   — intermediate Bronze/Silver/Gold storage
  • Postgres JDBC — writes the serving tables to Supabase
  • Windows-friendly defaults (temp dir, arrow, timezone)

The Delta + Postgres JARs are pulled from Maven on first run via
`spark.jars.packages` (needs internet once; cached in ~/.ivy2 afterwards).

NOTE on environment:
  - Requires a JDK (Java 17 recommended) with JAVA_HOME set.
  - PySpark 3.5 supports Python 3.8–3.11 (3.12 works in practice). Do NOT use
    Python 3.13/3.14 for the Spark steps.
  - On Windows, set HADOOP_HOME to a folder containing bin/winutils.exe and
    bin/hadoop.dll (see README "Spark on Windows").
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `config` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402

_SPARK = None


def get_spark(app_name: str | None = None):
    """Return a singleton SparkSession configured for Delta + Postgres JDBC."""
    global _SPARK
    if _SPARK is not None:
        return _SPARK

    from pyspark.sql import SparkSession

    # Local scratch dir (avoids Windows %TEMP% permission quirks)
    scratch = settings.DATA_DIR / "spark-warehouse"
    scratch.mkdir(parents=True, exist_ok=True)
    local_tmp = settings.DATA_DIR / "spark-tmp"
    local_tmp.mkdir(parents=True, exist_ok=True)

    builder = (
        SparkSession.builder
        .appName(app_name or settings.SPARK_APP_NAME)
        .master(settings.SPARK_MASTER)
        .config("spark.jars.packages", settings.SPARK_JARS_PACKAGES)
        # Delta Lake
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        # Resources
        .config("spark.driver.memory", settings.SPARK_DRIVER_MEMORY)
        .config("spark.sql.shuffle.partitions", "64")
        # Locations / temp
        .config("spark.sql.warehouse.dir", scratch.as_uri())
        .config("spark.local.dir", str(local_tmp))
        # Correctness / perf
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.sql.legacy.timeParserPolicy", "CORRECTED")
    )

    _SPARK = builder.getOrCreate()
    _SPARK.sparkContext.setLogLevel("WARN")
    return _SPARK


def write_jdbc(df, table: str, mode: str = "append") -> None:
    """Write a Spark DataFrame to a Supabase table via JDBC.

    Args:
        df:    Spark DataFrame whose columns match the target table columns.
        table: schema-qualified table name, e.g. 'clean.transactions'.
        mode:  'append' (default) or 'overwrite'. We use 'append' into tables
               whose DDL already exists (schema.sql) so we never let Spark
               recreate them with the wrong types.

    Writes are coalesced to settings.JDBC_WRITE_PARTITIONS so Spark stays within
    Supabase's pooler connection limit (one JDBC connection per partition).
    """
    parts = max(1, settings.JDBC_WRITE_PARTITIONS)
    if df.rdd.getNumPartitions() > parts:
        df = df.coalesce(parts)
    (
        df.write
        .format("jdbc")
        .option("url", settings.JDBC_URL)
        .option("dbtable", table)
        .option("user", settings.JDBC_PROPERTIES["user"])
        .option("password", settings.JDBC_PROPERTIES["password"])
        .option("driver", settings.JDBC_PROPERTIES["driver"])
        .option("stringtype", settings.JDBC_PROPERTIES["stringtype"])
        .option("batchsize", settings.JDBC_WRITE_BATCHSIZE)
        .option("reWriteBatchedInserts", "true")
        .mode(mode)
        .save()
    )


def read_jdbc(table_or_query: str):
    """Read a Supabase table (or '(SELECT ...) alias' subquery) into Spark."""
    return (
        get_spark().read
        .format("jdbc")
        .option("url", settings.JDBC_URL)
        .option("dbtable", table_or_query)
        .option("user", settings.JDBC_PROPERTIES["user"])
        .option("password", settings.JDBC_PROPERTIES["password"])
        .option("driver", settings.JDBC_PROPERTIES["driver"])
        .load()
    )


def stop_spark() -> None:
    global _SPARK
    if _SPARK is not None:
        _SPARK.stop()
        _SPARK = None


if __name__ == "__main__":
    spark = get_spark("spark-smoketest")
    print("Spark version:", spark.version)
    print("Master:", spark.sparkContext.master)
    spark.range(5).show()
    stop_spark()
