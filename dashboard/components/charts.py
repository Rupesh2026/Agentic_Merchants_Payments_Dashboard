"""
dashboard/components/charts.py — Plotly chart builders (Stripe-style theme).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings

PURPLE = settings.PRIMARY_COLOR
DANGER = settings.DANGER_COLOR
SUCCESS = settings.SUCCESS_COLOR
WARNING = settings.WARNING_COLOR

_BASE_LAYOUT = dict(
    margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="#fff",
    paper_bgcolor="#fff",
    font=dict(color="#33373d", size=12),
)

_GRAIN_TO_PERIOD = {"Month": "M", "Quarter": "Q", "Year": "Y"}


def _style(fig: go.Figure, height: int = 280) -> go.Figure:
    fig.update_layout(height=height, **_BASE_LAYOUT)
    fig.update_xaxes(gridcolor="#f0f0f3", zeroline=False)
    fig.update_yaxes(gridcolor="#f0f0f3", zeroline=False)
    return fig


def aggregate_kpi_timeseries(df, grain: str = "Month", date_col: str = "date") -> pd.DataFrame:
    """Aggregate KPI time-series into month, quarter, or year buckets."""
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()

    period_code = _GRAIN_TO_PERIOD.get(grain, "M")
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col])
    if out.empty:
        return out

    out["_period"] = out[date_col].dt.to_period(period_code)

    def _weighted_mean(frame: pd.DataFrame, value_col: str) -> float:
        if value_col not in frame.columns:
            return float("nan")
        weights = frame["total_transactions"] if "total_transactions" in frame.columns else None
        values = pd.to_numeric(frame[value_col], errors="coerce")
        if weights is not None:
            weights = pd.to_numeric(weights, errors="coerce").fillna(0)
            mask = values.notna() & weights.notna()
            if mask.any() and weights[mask].sum() > 0:
                return float((values[mask] * weights[mask]).sum() / weights[mask].sum())
        values = values.dropna()
        return float(values.mean()) if not values.empty else float("nan")

    rows = []
    for period, frame in out.groupby("_period", sort=True):
        row = {date_col: period.to_timestamp(how="start")}
        if period_code == "M":
            row["period_label"] = period.start_time.strftime("%b %Y")
        elif period_code == "Q":
            row["period_label"] = f"Q{period.quarter} {period.year}"
        else:
            row["period_label"] = str(period.year)

        if "gross_volume" in frame.columns:
            row["gross_volume"] = pd.to_numeric(frame["gross_volume"], errors="coerce").sum()
        if "total_transactions" in frame.columns:
            row["total_transactions"] = pd.to_numeric(frame["total_transactions"], errors="coerce").sum()
        if "fraud_count" in frame.columns:
            row["fraud_count"] = pd.to_numeric(frame["fraud_count"], errors="coerce").sum()
        if "chargeback_count" in frame.columns:
            row["chargeback_count"] = pd.to_numeric(frame["chargeback_count"], errors="coerce").sum()

        if "gross_volume" in row and "total_transactions" in row and row["total_transactions"]:
            row["avg_ticket"] = row["gross_volume"] / row["total_transactions"]
        elif "avg_ticket" in frame.columns:
            row["avg_ticket"] = _weighted_mean(frame, "avg_ticket")

        for rate_col in ("approval_rate", "fraud_rate"):
            if rate_col in frame.columns:
                row[rate_col] = _weighted_mean(frame, rate_col)

        rows.append(row)

    result = pd.DataFrame(rows).sort_values(date_col).reset_index(drop=True)
    return result


def revenue_chart(df, x="date", y="gross_volume", fraud="fraud_count") -> go.Figure:
    """Revenue bars + fraud trend line on a secondary axis."""
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df[x],
            y=df[y],
            name="Revenue",
            marker_color=PURPLE,
            opacity=0.85,
            hovertemplate="<b>%{x}</b><br>Revenue: $%{y:,.0f}<extra></extra>",
        )
    )
    fraud_col = fraud if fraud in df.columns else "fraud_rate" if "fraud_rate" in df.columns else None
    if fraud_col:
        is_rate = fraud_col.endswith("rate")
        y_title = "Fraud rate" if is_rate else "Fraud"
        fig.add_trace(
            go.Scatter(
                x=df[x],
                y=df[fraud_col],
                name=y_title,
                mode="lines+markers",
                line=dict(color=DANGER, width=3),
                marker=dict(size=6),
                yaxis="y2",
                hovertemplate=(
                    "<b>%{x}</b><br>Fraud rate: %{y:.2%}<extra></extra>"
                    if is_rate
                    else "<b>%{x}</b><br>Fraud: %{y:,}<extra></extra>"
                ),
            )
        )
        fig.update_layout(
            yaxis2=dict(
                overlaying="y",
                side="right",
                showgrid=False,
                title=y_title,
            )
        )
    fig.update_layout(
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
        yaxis=dict(title="Revenue ($)"),
    )
    return _style(fig)


def line_chart(df, x, y, color=PURPLE, title_y="") -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines",
                               line=dict(color=color, width=2)))
    fig.update_layout(yaxis=dict(title=title_y))
    return _style(fig)


def time_bar_chart(df, x, y, color=PURPLE, title_y="", percent=False) -> go.Figure:
    fmt = ".2%" if percent else ",.0f"
    title = title_y or y.replace("_", " ").title()
    fig = go.Figure(
        go.Bar(
            x=df[x],
            y=df[y],
            marker_color=color,
            opacity=0.88,
            hovertemplate=f"<b>%{{x}}</b><br>{title}: %{{y:{fmt}}}<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        hovermode="x",
        yaxis=dict(title=title),
    )
    if percent:
        fig.update_yaxes(tickformat=".0%")
    return _style(fig)


def hbar(df, x, y, color=PURPLE, pct=False) -> go.Figure:
    fig = px.bar(df, x=x, y=y, orientation="h", color_discrete_sequence=[color])
    if pct:
        fig.update_xaxes(tickformat=".0%")
    fig.update_layout(yaxis=dict(title=""), xaxis=dict(title=""), showlegend=False)
    return _style(fig)


def vbar(df, x, y, color=PURPLE) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color_discrete_sequence=[color])
    fig.update_layout(yaxis=dict(title=""), xaxis=dict(title=""), showlegend=False)
    return _style(fig)


def fraud_heatmap_fig(df) -> go.Figure:
    """hour_of_day × day_of_week fraud-rate heatmap."""
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    pivot = (df.pivot(index="day_of_week", columns="hour_of_day", values="fraud_rate")
               .reindex(range(7)).reindex(columns=range(24)))
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h:02d}" for h in range(24)],
        y=days,
        colorscale="Purples",
        hovertemplate="Day %{y}, Hour %{x}<br>Fraud rate %{z:.4%}<extra></extra>",
        colorbar=dict(title="Fraud rate"),
    ))
    return _style(fig, height=300)


def risk_histogram(df, col="risk_score") -> go.Figure:
    fig = px.histogram(df, x=col, nbins=50, color_discrete_sequence=[PURPLE])
    fig.add_vline(x=70, line_dash="dash", line_color=DANGER,
                  annotation_text="flag ≥ 70")
    fig.update_layout(yaxis=dict(title="Transactions"),
                      xaxis=dict(title="Risk score"), showlegend=False)
    return _style(fig)


def payout_bar(df) -> go.Figure:
    """Stacked net payout + fee components per payout period."""
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["payout_date"], y=df["net_payout"],
                         name="Net payout", marker_color=SUCCESS))
    for col, color, label in [
        ("interchange_fee", "#9b8cff", "Interchange"),
        ("processing_fee", "#c4b5fd", "Processing"),
        ("network_fee", WARNING, "Network"),
        ("scheme_fee", "#e2c7a0", "Scheme"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Bar(x=df["payout_date"], y=df[col], name=label, marker_color=color))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=-0.2),
                      yaxis=dict(title="$"))
    return _style(fig, height=300)


def donut(labels, values, colors=None) -> go.Figure:
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.55,
                           marker=dict(colors=colors)))
    fig.update_layout(legend=dict(orientation="h", y=-0.1), showlegend=True)
    return _style(fig, height=260)


def grouped_bar(df, x, y, color) -> go.Figure:
    fig = px.bar(df, x=x, y=y, color=color, barmode="group",
                 color_discrete_sequence=[PURPLE, "#b3aaff"])
    fig.update_layout(yaxis=dict(title=""), xaxis=dict(title=""))
    return _style(fig)
