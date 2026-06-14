"""
dashboard/components/tables.py — styled HTML table helpers (status pills, risk bars).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

_PILL = {"approved": "pill-approved", "flagged": "pill-flagged", "declined": "pill-declined"}


def status_pill(status: str) -> str:
    return f'<span class="{_PILL.get(status, "")}">{status}</span>'


def risk_badge(score) -> str:
    if score is None or pd.isna(score):
        return "—"
    score = int(score)
    color = "#e24b4a" if score >= 70 else "#ba7517" if score >= 30 else "#1d9e75"
    return (
        f'<span style="display:inline-block;min-width:28px;text-align:center;'
        f'background:{color}1a;color:{color};padding:2px 8px;border-radius:10px;'
        f'font-size:11px;font-weight:600">{score}</span>'
    )


def render_transactions(df: pd.DataFrame, columns: dict) -> None:
    """Render a transactions DataFrame as an HTML table with pills + risk badges.

    `columns` maps source column → display header. Special source columns
    'Status' and 'Risk' are expected to already be HTML.
    """
    show = df[list(columns.keys())].rename(columns=columns)
    st.write(
        show.to_html(escape=False, index=False, classes="dataframe", border=0),
        unsafe_allow_html=True,
    )


def money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return "—"
