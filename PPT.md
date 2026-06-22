# Payments Merchant Dashboard - Presentation Deck Outline

Use this file as the source for a slide deck on how the application was built.
The structure is intentionally presentation-ready: each section can map to one slide.

---

## Slide 1. Title

**Payments Merchant Dashboard**

**Subtitle:** End-to-end fraud analytics, merchant intelligence, and AI-assisted investigation

**What to say**
- I built a production-style merchant dashboard that combines ETL, ML, RAG, and a Streamlit UI.
- The goal was to simulate the kind of internal analytics platform a payment processor would use to monitor merchants, fraud, and payouts.

**Visual idea**
- Architecture strip: raw data -> ETL -> ML -> RAG -> dashboard

---

## Slide 2. The Problem

**Problem statement**
- Payments teams need to monitor portfolio health, fraud risk, and merchant performance across millions of transactions.
- Traditional dashboards are good at charts, but poor at investigation.
- Non-technical users still need answers like:
  - Which merchants are risky?
  - Why was this transaction flagged?
  - What changed this week?
  - What should I investigate first?

**Why this matters**
- Fraud decisions are time-sensitive.
- Merchant support teams need fast context, not manual SQL.
- Analysts need both aggregate KPIs and row-level explanations.

**What to say**
- The core gap is not data availability. It is turning raw payment data into an operational decision tool.

---

## Slide 3. Users

**Primary users**
- Portfolio / risk managers
- Fraud analysts
- Merchant success teams
- Business operators and leadership

**What each user needs**
- Portfolio managers: trends, approval rates, fraud rates, payout performance
- Fraud analysts: suspicious transactions, SHAP explanations, anomaly patterns
- Merchant success: merchant-level drill down and peer comparison
- Leadership: a concise business view of risk and performance

**What to say**
- I designed the product so the same dataset can serve both strategic and investigative workflows.

---

## Slide 4. Data Scope

**Dataset**
- Sparkov credit card fraud dataset from Kaggle
- 1,852,394 transactions total
- 693 active merchants
- Date range: 2019-01-01 to 2020-12-31

**Why this dataset**
- It includes merchant names, categories, timestamps, and geography.
- That makes it useful for merchant analytics, not just fraud classification.

**What to say**
- I chose Sparkov because it supports both ML modeling and realistic business reporting.

---

## Slide 5. Business Problem -> Solution

**Business goal**
- Give payments teams a single interface for monitoring, explaining, and investigating payment behavior.

**Solution**
- Build a medallion-style data pipeline
- Train a fraud model with explainability
- Add retrieval-based AI for natural-language Q&A
- Present everything through a merchant dashboard

**One-line value prop**
- Turn raw payment events into actionable merchant intelligence.

---

## Slide 6. Architecture Overview

**High-level flow**
- Raw CSVs
- Bronze: local parquet audit layer
- Silver: cleaned and enriched Postgres tables
- Gold: feature tables, KPIs, merchant stats, fraud scores, embeddings
- Dashboard: Streamlit UI
- AI Analyst: pgvector + agent tools + GPT-4o

**Core design principle**
- Keep the data warehouse, feature store, analytics, and AI assistant on a shared gold layer.

**What to say**
- The architecture is intentionally layered so each piece can be rerun and inspected independently.

---

## Slide 7. ETL Design

**What I built**
- Bronze loader reads the raw CSVs and writes a local parquet audit file.
- Silver cleaner standardizes types, removes PII, deduplicates transactions, and builds merchant/customer dimensions.
- Silver enricher adds deterministic operational fields like card network, decline code, auth latency, settlement date, and chargebacks.
- Gold feature builder creates ML features.
- Gold aggregations build dashboard-ready tables.

**Why this design**
- Bronze is cheap and reproducible.
- Silver creates trustworthy normalized data.
- Gold optimizes for dashboard and model usage.

**What to say**
- I separated raw retention from analytics so I could scale the pipeline without polluting the reporting layer.

---

## Slide 8. Why Enrichment Was Needed

**Gap in the original dataset**
- The source data did not look like a real payments processor system.

**What I added**
- `card_network`
- `txn_status`
- `decline_code`
- `auth_latency_ms`
- `settlement_date`
- `has_chargeback`
- `card_last4`

**Why**
- To make the dashboard feel operational, not academic.
- To support payout analysis and approval/decline behavior.

**Important implementation detail**
- Enrichment is deterministic from `trans_num`, so the pipeline is reproducible.

---

## Slide 9. ML Layer

**Model**
- XGBoost fraud classifier

**Why XGBoost**
- Strong fit for tabular fraud data
- Fast to train
- High signal on engineered features

**Explainability**
- SHAP values are stored in `gold.risk_scores`
- The dashboard can explain why a transaction was flagged

**Key features**
- Geo distance
- 1h/24h velocity
- Amount z-score
- Merchant fraud rate
- Category fraud rate

---

## Slide 10. RAG and AI Analyst

**What it does**
- Embeds merchant and KPI narratives into `gold.embeddings`
- Lets the agent answer natural language questions with live DB tools

**Tools**
- `vector_search`
- `sql_query`
- `get_merchant_detail`
- `explain_fraud_transaction`
- `get_kpi_summary`

**Why this matters**
- Users can ask questions in plain English instead of writing SQL.
- The assistant can combine semantic retrieval with exact database queries.

**What to say**
- This is not chat for novelty. It is a practical query interface for operational analysis.

---

## Slide 11. Security and Guardrails

**What I added**
- Input sanitization
- Output validation
- Canary token detection
- Tool-output redaction
- System prompt hardening against prompt injection

**Why**
- AI features are vulnerable to prompt injection and hidden-instruction leakage.
- I wanted a production-style defense layer instead of trusting the model blindly.

**Implementation pattern**
- Untrusted input is normalized before the agent sees it.
- Retrieved content is sanitized before being passed to the model.
- Assistant output is checked before returning to the user.

**What to say**
- I treated prompt injection as a system-design problem, not just a prompt-writing problem.

---

## Slide 12. Dashboard UX

**Pages**
- Overview
- Transactions
- Performance
- Fraud and Risk
- Payouts
- AI Analyst

**Key interactions**
- Global merchant selector
- Row-level drill down
- SHAP explanation panel
- Cross-page AI context injection

**Why Streamlit**
- Fast to build
- Good enough for operational analytics
- Easy to keep data + UI tightly coupled

---

## Slide 13. Validation and KPIs

**Pipeline validation**
- Bronze row count: 1,852,394
- Silver merchants: 693
- Gold daily KPI span: 730 days
- Embeddings: 783 total documents

**Model KPIs**
- ROC-AUC: 0.9997
- PR-AUC: 0.9806
- Fraud recall: 0.98
- Fraud precision: 0.73

**Operational KPIs**
- Approval rate baseline: about 97.3% for non-fraud rows
- Industry fraud benchmark: 0.58%
- Payout history: 105 weekly rows

**What to say**
- The dataset is synthetic, so the model metrics are very strong. The value of the project is the end-to-end system, not just the classifier.

---

## Slide 14. Business Impact

**Impact for analysts**
- Faster investigation of suspicious transactions
- Less manual SQL and spreadsheet work
- Built-in explanation for model decisions

**Impact for merchant teams**
- Clear merchant-level risk and performance view
- Peer comparison by category
- Payout visibility

**Impact for leadership**
- Single-pane view of portfolio health
- Better prioritization of risk and support work

**What to say**
- The product compresses a multi-step analyst workflow into one interface.

---

## Slide 15. Build Sequence

**How I built it**
1. Defined the business problem and target user workflows
2. Loaded the Kaggle dataset into a bronze audit layer
3. Cleaned, typed, deduplicated, and enriched the silver layer
4. Built gold feature tables and KPI aggregations
5. Trained XGBoost and added SHAP explainability
6. Created embeddings for merchant and daily narratives
7. Built the agent and tool layer
8. Shipped the Streamlit dashboard
9. Added prompt-injection defenses and canary validation
10. Validated counts, model metrics, and dashboard behavior

**What to say**
- I followed the sequence data -> model -> retrieval -> interface -> guardrails.

---

## Slide 16. Design Decisions and Why

**Key decisions**
- Local parquet for Bronze to keep raw audit data cheap and reproducible
- Postgres gold layer for structured analytics and joins
- Deterministic enrichment to preserve reproducibility
- XGBoost + SHAP for fast, interpretable fraud modeling
- pgvector + agent tools for natural language analysis
- Streamlit for fast delivery of a polished internal dashboard
- Canary tokens and validation to defend against prompt injection

**What to say**
- Each choice was made to optimize for a demo that still behaves like a real system.

---

## Slide 17. Final Outcome

**Result**
- A full-stack payments intelligence application
- Ready for merchant monitoring, fraud investigation, and AI-assisted analysis
- Built as an interview-quality demonstration of architecture and product thinking

**Short closing**
- I turned a raw fraud dataset into a production-style merchant analytics platform with ETL, ML, RAG, dashboarding, and security guardrails.

---

## Appendix. Optional Speaker Notes

If you want a stronger presentation, emphasize these points:
- The project solves a real operational problem, not a toy dashboard problem.
- The data model is layered so the system can be rebuilt, tested, and explained.
- The AI assistant is grounded in SQL and embeddings, not free-form guessing.
- The security layer was added deliberately to handle prompt injection and hidden instruction leakage.
- The strongest evidence of quality is the full set of validation metrics and counts.

