# Go Runner - Alpine-based lightweight container
FROM golang:1.22-alpine

# Install only essential packages
RUN apk add --no-cache bash

# Create non-root user for security
RUN adduser -D -s /bin/bash runner

# Set working directory
WORKDIR /code

# Switch to non-root user
USER runner

# Default command (will be overridden)
CMD ["go", "version"]
