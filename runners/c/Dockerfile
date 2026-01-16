# C Runner - Alpine-based lightweight container
FROM alpine:3.19

# Install GCC and essential build tools
RUN apk add --no-cache gcc musl-dev bash

# Create non-root user for security
RUN adduser -D -s /bin/bash runner

# Set working directory
WORKDIR /code

# Switch to non-root user
USER runner

# Default command (will be overridden)
CMD ["gcc", "--version"]
