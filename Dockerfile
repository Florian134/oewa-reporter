# ÖWA Reporting System - Dockerfile
# ==================================

FROM python:3.11-slim

# Labels
LABEL maintainer="Russmedia"
LABEL description="ÖWA/INFOnline Reporting System"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Vienna

# Working Directory
WORKDIR /app

# System Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application Code
COPY oewa_reporting/ ./oewa_reporting/
COPY tests/ ./tests/

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m oewa_reporting check || exit 1

# Default Command
ENTRYPOINT ["python", "-m", "oewa_reporting"]
CMD ["--help"]

