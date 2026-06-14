# config/settings.py — All configuration, constants, and env vars
# Stack: Supabase Postgres (+pgvector) · PySpark/Delta · OpenAI · MLflow · Google ADK

import os
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
DATA_DIR        = BASE_DIR / "data"
RAW_DIR         = DATA_DIR / "raw"
PROCESSED_DIR   = DATA_DIR / "processed"
DELTA_DIR       = DATA_DIR / "delta"          # Delta Lake intermediate store
MODELS_DIR      = BASE_DIR / "ml" / "artifacts"
for _d in (PROCESSED_DIR, DELTA_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Delta table locations (Bronze/Silver/Gold intermediate storage)
DELTA_BRONZE  = str(DELTA_DIR / "bronze" / "transactions")
DELTA_SILVER  = str(DELTA_DIR / "silver" / "transactions")
DELTA_FEATURES = str(DELTA_DIR / "gold" / "features")

# Raw data files (Kaggle Sparkov dataset)
TRAIN_CSV = RAW_DIR / "fraudTrain.csv"
TEST_CSV  = RAW_DIR / "fraudTest.csv"

# ── Database: Supabase Postgres ────────────────────────────────────────────
# Prefer a full DATABASE_URL (copy the Session-pooler string from Supabase).
# Fall back to discrete POSTGRES_* vars for local/dev parity.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    POSTGRES_HOST     = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT     = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB       = os.getenv("POSTGRES_DB", "postgres")
    POSTGRES_USER     = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    DATABASE_URL = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

_parsed = urlparse(DATABASE_URL)
PG_HOST     = _parsed.hostname or "localhost"
PG_PORT     = _parsed.port or 5432
PG_DB       = (_parsed.path or "/postgres").lstrip("/") or "postgres"
PG_USER     = unquote(_parsed.username or "postgres")
PG_PASSWORD = unquote(_parsed.password or "")

# Supabase requires TLS. URL-encode user/password so special characters in the
# DB password (e.g. '@', '!', '#') don't break the SQLAlchemy connection URL.
_ENC_USER = quote(PG_USER, safe="")
_ENC_PW = quote(PG_PASSWORD, safe="")
PG_SSLMODE = os.getenv("SSLMODE", "require")
SQLALCHEMY_URL = (
    f"postgresql+psycopg2://{_ENC_USER}:{_ENC_PW}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    f"?sslmode={PG_SSLMODE}"
)

# JDBC URL + properties for Spark writes to Supabase
JDBC_URL = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}?sslmode=require"
JDBC_PROPERTIES = {
    "user":     PG_USER,
    "password": PG_PASSWORD,
    "driver":   "org.postgresql.Driver",
    "stringtype": "unspecified",   # lets text->jsonb / ::numeric casts pass through
}

SUPABASE_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "jshnnfzqgiwcnznwieje")

DB_POOL_SIZE    = 5
DB_MAX_OVERFLOW = 10

# ── Spark / Delta config ───────────────────────────────────────────────────
SPARK_MASTER          = os.getenv("SPARK_MASTER", "local[*]")
SPARK_DRIVER_MEMORY   = os.getenv("SPARK_DRIVER_MEMORY", "4g")
SPARK_APP_NAME        = "payments-medallion-etl"
POSTGRES_JDBC_VERSION = os.getenv("POSTGRES_JDBC_VERSION", "42.7.3")
DELTA_SPARK_VERSION   = os.getenv("DELTA_SPARK_VERSION", "3.2.0")
# Maven packages Spark pulls on first run (needs internet once; cached after).
SPARK_JARS_PACKAGES = ",".join([
    f"io.delta:delta-spark_2.12:{DELTA_SPARK_VERSION}",
    f"org.postgresql:postgresql:{POSTGRES_JDBC_VERSION}",
])
JDBC_WRITE_BATCHSIZE = 10_000   # rows per JDBC batch insert
# Spark opens one JDBC connection per partition; cap concurrency so we stay
# within Supabase's pooler connection limit.
JDBC_WRITE_PARTITIONS = 8

# ── OpenAI (only model provider) ───────────────────────────────────────────
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
EMBEDDING_MODEL   = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM     = 1536          # text-embedding-3-small dimension
EMBEDDING_BATCH   = 100           # texts per API call
# Google ADK routes to OpenAI through LiteLLM using this model string.
ADK_MODEL         = f"openai/{OPENAI_CHAT_MODEL}"

# ── MLflow ─────────────────────────────────────────────────────────────────
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "file:./mlruns")
MLFLOW_EXPERIMENT   = os.getenv("MLFLOW_EXPERIMENT", "payments-fraud-xgboost")

# ── ETL Config ─────────────────────────────────────────────────────────────
CHUNK_SIZE        = 50_000        # fallback row chunking (non-Spark utilities)
SILVER_BATCH      = 100_000

# Set to a positive integer to limit rows written to the DB (e.g. for cloud
# free-tier demos). 0 = write all rows (default for local Postgres).
SUPABASE_SAMPLE_ROWS = int(os.getenv("SUPABASE_SAMPLE_ROWS", "0"))

# ── ML Config ──────────────────────────────────────────────────────────────
FRAUD_THRESHOLD   = 0.5
RISK_HIGH         = 70            # risk_score >= 70 → flagged
RISK_CRITICAL     = 90            # risk_score >= 90 → blocked
RANDOM_STATE      = 42
TEST_SIZE         = 0.2

XGBOOST_PARAMS = {
    "n_estimators":      500,
    "max_depth":         6,
    "learning_rate":     0.05,
    "subsample":         0.8,
    "colsample_bytree":  0.8,
    "scale_pos_weight":  578,     # ~578:1 class imbalance in Sparkov
    "eval_metric":       "auc",
    "tree_method":       "hist",
    "random_state":      RANDOM_STATE,
    "n_jobs":            -1,
}

# ML feature columns (must match gold.features columns)
ML_FEATURES = [
    "amt",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "month",
    "geo_distance_km",
    "city_pop_log",
    "is_rural",
    "tx_count_1h",
    "tx_count_24h",
    "tx_amount_1h",
    "tx_amount_24h",
    "amt_zscore",
    "category_encoded",
    "is_online",
    "gender_encoded",
    "age_group_encoded",
    "merchant_fraud_rate",
    "category_fraud_rate",
]
ML_TARGET = "is_fraud"

# ── Faker Enrichment Rules ─────────────────────────────────────────────────
CARD_NETWORK_WEIGHTS = {
    "Visa":       0.44,
    "Mastercard": 0.31,
    "Amex":       0.12,
    "ACH":        0.09,
    "Other":      0.04,
}

# ISO 8583 decline codes: code → (reason, weight)
DECLINE_CODES = {
    "51": ("Insufficient funds",   0.38),
    "05": ("Do not honour",        0.24),
    "14": ("Invalid card number",  0.16),
    "41": ("Lost card",            0.09),
    "43": ("Stolen card",          0.05),
    "59": ("Suspected fraud",      0.08),
}

# Chargeback reasons and weights
CHARGEBACK_REASONS = {
    "Unauthorized transaction": 0.40,
    "Item not received":        0.35,
    "Item not as described":    0.15,
    "Duplicate charge":         0.10,
}

# Settlement days by card network: {network: [(days, probability), ...]}
SETTLEMENT_DAYS = {
    "Visa":       [(1, 0.60), (2, 0.40)],
    "Mastercard": [(1, 0.60), (2, 0.40)],
    "Amex":       [(2, 0.50), (3, 0.50)],
    "ACH":        [(3, 1.00)],
    "Other":      [(2, 0.50), (3, 0.50)],
}

# Processing fee rates by card network
FEE_RATES = {
    "Visa":       0.0215,
    "Mastercard": 0.0220,
    "Amex":       0.0350,
    "ACH":        0.0080,
    "Other":      0.0250,
}

# Auth latency parameters (ms): {status: (mean, std)}
AUTH_LATENCY = {
    "approved": (180, 30),
    "declined": (240, 40),
    "flagged":  (160, 20),
}

# ── Category Mappings ──────────────────────────────────────────────────────
CATEGORY_DISPLAY = {
    "grocery_pos":    "Grocery (In-store)",
    "grocery_net":    "Grocery (Online)",
    "shopping_pos":   "Shopping (In-store)",
    "shopping_net":   "Shopping (Online)",
    "food_dining":    "Food & Dining",
    "gas_transport":  "Gas & Transport",
    "entertainment":  "Entertainment",
    "travel":         "Travel",
    "health_fitness": "Health & Fitness",
    "home":           "Home",
    "kids_pets":      "Kids & Pets",
    "personal_care":  "Personal Care",
    "misc_pos":       "Misc (In-store)",
    "misc_net":       "Misc (Online)",
}

CATEGORY_ORDER = list(CATEGORY_DISPLAY.keys())
CATEGORY_ENCODED = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}

# Online categories (card-not-present)
ONLINE_CATEGORIES = {"grocery_net", "shopping_net", "misc_net"}

# High-risk categories (historically higher fraud rates)
HIGH_RISK_CATEGORIES = {"travel", "entertainment", "misc_net", "shopping_net"}

# ── Job Category Mapping ───────────────────────────────────────────────────
# Map Sparkov job strings → 10 grouped categories
JOB_CATEGORY_KEYWORDS = {
    "Technology":   ["engineer", "developer", "programmer", "analyst", "data", "software", "it ", "tech"],
    "Healthcare":   ["doctor", "nurse", "medical", "health", "physician", "therapist", "dental"],
    "Finance":      ["accountant", "banker", "financial", "broker", "trader", "economist"],
    "Education":    ["teacher", "professor", "lecturer", "educator", "instructor", "tutor"],
    "Legal":        ["lawyer", "attorney", "paralegal", "judge", "solicitor"],
    "Management":   ["manager", "director", "executive", "ceo", "officer", "administrator"],
    "Service":      ["driver", "clerk", "assistant", "worker", "operator", "technician"],
    "Sales":        ["sales", "marketing", "representative", "agent", "consultant"],
    "Creative":     ["designer", "artist", "writer", "journalist", "architect"],
    "Other":        [],  # fallback
}

# ── Age Group Mapping ──────────────────────────────────────────────────────
AGE_GROUPS = {
    "18-25": (18, 25),
    "26-35": (26, 35),
    "36-50": (36, 50),
    "51-65": (51, 65),
    "66+":   (66, 120),
}
AGE_GROUP_ENCODED = {"18-25": 0, "26-35": 1, "36-50": 2, "51-65": 3, "66+": 4}

# ── Dashboard Config ───────────────────────────────────────────────────────
DASHBOARD_TITLE   = "Payments Merchant Dashboard"
DASHBOARD_ICON    = "💳"
PRIMARY_COLOR     = "#635bff"   # Stripe-like purple
DANGER_COLOR      = "#e24b4a"
SUCCESS_COLOR     = "#1d9e75"
WARNING_COLOR     = "#ba7517"

# ── Industry Benchmarks (for comparison) ──────────────────────────────────
INDUSTRY_FRAUD_RATE    = 0.0058   # 0.58% Sparkov baseline
INDUSTRY_APPROVAL_RATE = 0.973    # 97.3% baseline
INDUSTRY_AVG_TICKET    = 74.10    # $74.10 baseline
