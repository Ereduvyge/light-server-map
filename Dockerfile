FROM python:3.13-slim

ARG APP_ENV=production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=${APP_ENV}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home appuser

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/data && chown appuser:appuser /app/data

ENV DATABASE_URL=sqlite+aiosqlite:////app/data/monitor.db
VOLUME ["/app/data"]
USER appuser
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:3001/healthz', timeout=2)"

# Use one worker: the APScheduler instance lives in this process.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3001", "--workers", "1"]
