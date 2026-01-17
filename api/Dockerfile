# vbase-rce API Server
FROM python:3.12-slim

# Install minimal dependencies (no Docker CLI needed - using TCP proxy)
# gosu is used for dropping privileges in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser

# Create code files directory (will be overridden by volume mount)
RUN mkdir -p /tmp/vbase-rce && chown appuser:appuser /tmp/vbase-rce

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and entrypoint
COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Expose port
EXPOSE 8000

# Use entrypoint to handle volume permissions and drop privileges
# Container starts as root (set in docker-compose), entrypoint drops to appuser
ENTRYPOINT ["/entrypoint.sh"]

# Start the API server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
