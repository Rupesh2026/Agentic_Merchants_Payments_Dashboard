"""
etl/sqlutil.py — load the Spark SQL transform files in sql/.

The Medallion transforms live as plain .sql files (the source of truth for the
"Spark SQL ETL" story). Single-query files are loaded whole; the multi-query
gold_aggregations.sql is split on `-- @@name:` markers into a {name: sql} dict.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import settings

SQL_DIR = settings.BASE_DIR / "sql"


def load_sql(filename: str) -> str:
    """Return the full text of sql/<filename>."""
    return (SQL_DIR / filename).read_text(encoding="utf-8")


def load_named_sql(filename: str) -> dict[str, str]:
    """Split a multi-query .sql file into {name: query}.

    Sections are delimited by lines like `-- @@name: kpi_daily`.
    """
    text = load_sql(filename)
    parts: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s*--\s*@@name:\s*(\w+)\s*$", line)
        if m:
            if current is not None:
                parts[current] = "\n".join(buf).strip()
            current = m.group(1)
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        parts[current] = "\n".join(buf).strip()
    return parts
