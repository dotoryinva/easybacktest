FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/strategies.db \
    ENABLE_SCHEDULER=true

WORKDIR /app

# Dependencies first so the layer caches across code changes.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY app ./app
COPY scripts ./scripts

# The Fly volume mounts here; the OHLCV Parquet cache and SQLite both live on it.
VOLUME ["/data"]
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
