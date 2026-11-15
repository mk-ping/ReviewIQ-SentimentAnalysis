
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TESSERACT_CMD=/usr/bin/tesseract
# tesseract is only for scanned-PDF OCR; the app works without it
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt
COPY . .
EXPOSE 8010
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8010"]
