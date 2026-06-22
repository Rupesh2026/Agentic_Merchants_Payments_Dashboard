# Deep-Dive Project Blueprint: Payments Merchant Dashboard

This document serves as a comprehensive study guide for the project's architecture, implementation, and the "why" behind every major engineering decision.

---

## 1. The Core Question: Postgres vs. Supabase?
**The Answer:** We are using **Supabase**, which is a managed platform built on top of **PostgreSQL**.

### Technical Context
- **Engine:** The actual database engine is PostgreSQL 15.
- **Extensions:** We specifically use the `pgvector` extension, which allows Postgres to store and query high-dimensional vectors (embeddings) using index types like HNSW (Hierarchical Navigable Small World).
- **Why Supabase?** 
    - **Developer Velocity:** It provides an instant cloud-hosted Postgres instance with a built-in SQL editor and API.
    - **Integrated Vector Store:** Instead of managing a separate vector database (like Pinecone or Milvus), we keep the transactional data and the embeddings in the *same* database. This simplifies backups, consistency, and joins.
    - **Interview Story:** Using a managed service like Supabase demonstrates a "production-first" mindset—leveraging existing cloud ecosystems rather than over-engineering infrastructure.

---

## 2. The Core Question: RAG or Agent-SQL?
**The Answer:** It is a **Hybrid Agentic System**. It is not "just one or the other"; it is a reasoning engine that orchestrates both.

### How it works (The Orchestration)
The system uses the **Google ADK (Agent Development Kit)** with `gpt-4o`. The agent is given a set of tools. When a user asks a question, the agent performs a "Reasoning" step to decide which tool is most appropriate:

#### A. The RAG Path (Semantic Retrieval)
- **What is it?** Retrieval Augmented Generation.
- **Process:** 
    1. `rag/embeddings.py` takes structured data (e.g., Merchant Stats) and turns it into a narrative: *"Merchant X has a high fraud rate of 1.2%, which is 2x the industry average..."*
    2. This text is converted into a 153 la-dimensional vector using OpenAI's `text-embedding-3-small`.
    3. These are stored in `gold.embeddings` via `pgvector`.
- **When the Agent uses it:** For "qualitative" or "summarization" queries. 
    - *Example:* "Give me a risk assessment for TravelBook." $\to$ The agent calls `vector_search` $\to$ retrieves the pre-written AI narrative $\to$ synthesizes it for the user.

#### B. The Agent-SQL Path (Quantitative Retrieval)
- **What is it?** Natural Language to SQL (NL2SQL).
- **Process:** The agent uses tools like `sql_query` or `get_kpi_summary` to run real-time `SELECT` statements against the Gold and Clean schemas.
- **When the Agent uses it:** For "quantitative" or "precise" queries.
    - *Example:* "What was the total volume on June 8th?" $\to$ The agent calls `sql_query("SELECT SUM(gross_volume) FROM gold.kpi_daily...")` $\to$ gets the exact number $\to$ reports it.

### Why this Hybrid Approach?
- **Pure SQL** is blind to "narrative" and "context." It can't tell you if a merchant *feels* risky; it can only tell you the fraud rate.
- **Pure RAG** often hallucinates numbers. If you ask a RAG system for a sum, it might retrieve a document that says "Volume was high" and guess the number.
- **The Hybrid Result:** The agent acts as a **Controller**. It uses SQL for precision and RAG for context, combining the two into a single, accurate, and nuanced answer.

---

## 3. Medallion Architecture: The "Why"

### Bronze Layer (The Immutable Log)
- **Implementation:** Local Parquet files (`bronze_raw.parquet`).
- **Decision:** We *do not* upload the raw 1.85M rows to Supabase.
- **Why?** Supabase free tier has strict disk limits. By keeping the "raw" layer as a local Parquet file, we adhere to the Medallion principle (having an original source of truth) without crashing the database.

### Silver Layer (The Trusted Source)
- **Implementation:** `clean.transactions`, `clean.merchants`, `clean.customers`.
- **Decision:** Deterministic "Faker" enrichment.
- **Why?** The raw dataset is great for ML but lacks "Business Logic" fields (like `card_network` or `decline_codes`). We use deterministic hashing of the `trans_num` to generate these. This means if you re-run the pipeline, "Transaction A" always gets the same "Visa" network and the same "Insufficient Funds" decline code. It makes the demo reproducible.

### Gold Layer (The Serving Layer)
- **Implementation:** `gold.features`, `gold.kpi_daily`, `gold.risk_scores`, etc.
- **Decision:** Pre-calculating "Velocity Windows" and "Aggregations."
- **Why?** Calculating a "rolling 24-hour transaction count" for 1.85M rows on the fly would be too slow for a dashboard. We move the heavy computation to the ETL phase, so the Dashboard and Agent only perform simple `SELECT` queries.

---

## 4. Machine Learning: XGBoost + SHAP

### Why XGBoost?
For tabular data (columns and rows), Gradient Boosted Decision Trees (GBDT) like XGBoost almost always outperform Deep Learning. It is faster to train, requires less data normalization, and is the industry standard for fraud detection.

### Handling the "Needle in a Haystack" (Class Imbalance)
Fraud is rare (~0.17%). A model that simply guesses "NOT FRAUD" for everything would be 99.8% accurate but useless.
- **Solution:** `scale_pos_weight`. We tell XGBoost to penalize the misclassification of a fraud case $\sim$578 times more than a legit case. This forces the model to actually learn the fraud patterns.

### Bridging the Gap: SHAP $\to$ RAG
This is the most advanced part of the project. 
1. **ML Model:** Predicts `fraud_probability`.
2. **SHAP Explainer:** Breaks down *why* that probability is high. (e.g., "Distance: +0.41, Velocity: +0.38").
3. **Storage:** These SHAP values are stored as `JSONB` in `gold.risk_scores`.
4. **Agent Integration:** When the user asks "Why was this flagged?", the agent calls `explain_fraud_transaction`, reads the SHAP JSON, and uses `gpt-4o` to translate: *"The transaction was flagged primarily because it occurred 800km from home and the account had 8 transactions in one hour."*

---

## 5. Summary Table for Study

| Component | Tool/Tech | Purpose | Key Decision |
| :--- | :--- | :--- | :--- |
| **Database** | Supabase (Postgres) | Serving & Vector Store | One DB for both relational data and vectors. |
| **ETL** | PySpark / Pandas | Medallion Pipeline | Local Parquet for Bronze to save cloud disk space. |
| **Enrichment** | Faker + Hashing | Operational Context | Deterministic generation for reproducibility. |
| **ML Model** | XGBoost | Fraud Detection | `scale_pos_weight` to handle extreme imbalance. |
| **Explainability** | SHAP | Model Transparency | Store SHAP as JSONB to feed the AI Agent. |
| **RAG** | OpenAI + pgvector | Semantic Analysis | Embed AI-generated narratives, not just raw rows. |
| **Agent** | Google ADK + gpt-4o | Intelligent Analyst | Tool-use (Function Calling) to hybridize SQL + RAG. |
| **UI** | Streamlit | Merchant Dashboard | Fast delivery of professional-grade analytics. |

---

## 6. Security Guardrails Added

The AI Analyst now includes a lightweight production guardrail layer focused on prompt-injection resistance and canary-token detection.

### What Was Implemented
- Shared sanitizer in `rag/security.py` for user input normalization, control-character stripping, and canary-token detection.
- Canary tokens added to `rag/prompts.py` inside the system prompt as internal security markers that must never be revealed.
- Tool-output redaction in `rag/agent.py` so retrieved context cannot leak canary tokens back into the model.
- Final-response validation in `rag/agent.py` so any assistant output containing canary tokens is replaced with a safe refusal.
- Streamlit input-path sanitization in `dashboard/views/ai_analyst.py` so the UI does not store raw canary text in chat history.

### Validation Notes
- The sanitizer redacts exact canary tokens before forwarding text to the model.
- The assistant output validator blocks any leaked canary token and returns a fixed refusal message.
- The system prompt explicitly instructs the agent to ignore prompt-injection attempts and treat user/tool content as untrusted data.
- The implementation is intentionally conservative: it focuses on exact canary identification and safe refusal, not broad semantic filtering that could hide legitimate analytics questions.

### Files Changed
- `rag/security.py`
- `rag/prompts.py`
- `rag/agent.py`
- `dashboard/views/ai_analyst.py`
