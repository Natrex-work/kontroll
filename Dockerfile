FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    DEBIAN_FRONTEND=noninteractive \
    PORT=10000 \
    KV_APP_VERSION_LABEL=v98 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends -o Dpkg::Use-Pty=0 \
        ca-certificates \
        tesseract-ocr \
        tesseract-ocr-nor \
        tesseract-ocr-eng \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --prefer-binary -r requirements.txt

COPY . ./

EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
