FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY . .

# Increase pip network timeout a bit to be robust to slow connections when building image
RUN pip install --no-cache-dir --default-timeout=120 .

EXPOSE 8000

CMD ["python", "-m", "thordata_mcp.main", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
