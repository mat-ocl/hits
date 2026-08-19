FROM python:3.14-slim

ARG APP_VERSION=0.1.0-dev

WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Permanently hardcode the built version directly into config.py
RUN sed -i "s/CURRENT_VERSION = .*/CURRENT_VERSION = \"${APP_VERSION}\"/" app/config.py

# Run as non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.routes:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]