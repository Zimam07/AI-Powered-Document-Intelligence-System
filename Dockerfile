FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY scripts scripts
COPY README.md ARCHITECTURE.md PROMPTS.md ./
ENV DATA_DIR=/app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
