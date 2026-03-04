# MVP Auto-Summary Orchestrator
# Replaces n8n with native Python scheduler + tasks + Telegram bot
#
# Build: docker build -t mvp-orchestrator .
# Run:   docker compose up -d orchestrator

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Health check (process is alive)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Set timezone
ENV TZ=Europe/Moscow
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "app.main"]
