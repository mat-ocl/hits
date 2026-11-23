FROM python:3-slim

ARG APP_VERSION=0.1.0-dev

# Non-root user created first so COPY --chown does not need a second copy of every file
RUN useradd -m appuser

WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser app ./app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# No --proxy-headers: the app reads X-Forwarded-For itself, only when TRUST_PROXY_HEADERS=true
CMD ["uvicorn", "app.routes:app", "--host", "0.0.0.0", "--port", "8000"]