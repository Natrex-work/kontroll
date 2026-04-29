FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000 \
    KV_APP_VERSION=1.8.0 \
    KV_APP_VERSION_LABEL=1.8.0 \
    KV_ZONE_CHECK_MAX_LIVE_LAYERS=6 \
    KV_ZONE_POINT_QUERY_TIMEOUT=1.8 \
    KV_ZONE_CHECK_TOTAL_TIMEOUT=3.0 \
    KV_ZONE_STATUS_CACHE_SECONDS=300 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tesseract-ocr tesseract-ocr-nor tesseract-ocr-eng \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
