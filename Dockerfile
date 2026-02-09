FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Install Playwright dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
RUN pip install --no-cache-dir --default-timeout=120 . && \
    playwright install chromium && \
    playwright install-deps chromium

# Copy application code
COPY . .

EXPOSE 8000

CMD ["python", "-m", "thordata_mcp.main", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
