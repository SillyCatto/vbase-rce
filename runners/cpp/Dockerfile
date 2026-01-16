# C++ Runner - Alpine-based lightweight container
FROM alpine:3.19

# Install G++ and essential build tools
RUN apk add --no-cache g++ musl-dev bash libstdc++

# Create non-root user for security
RUN adduser -D -s /bin/bash runner

# Set working directory
WORKDIR /code

# Switch to non-root user
USER runner

# Default command (will be overridden)
CMD ["g++", "--version"]
