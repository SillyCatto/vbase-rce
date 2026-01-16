# Python Runner - Alpine-based lightweight container
FROM python:3.12-alpine

# Install only essential packages
RUN apk add --no-cache bash

# Create non-root user for security
RUN adduser -D -s /bin/bash runner

# Set working directory
WORKDIR /code

# Switch to non-root user
USER runner

# Default command (will be overridden)
CMD ["python3", "--version"]
