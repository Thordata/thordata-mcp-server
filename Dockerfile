FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY . .

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "thordata_mcp.main", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
