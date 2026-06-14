FROM python:3.12-slim

WORKDIR /app

# gcc/g++ needed by grpcio (pulled in by google-adk) on some platforms
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install deps first so Docker caches this layer separately from source code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Render injects $PORT at runtime; fall back to 8501 locally
CMD ["sh", "-c", "streamlit run dashboard/app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false"]
