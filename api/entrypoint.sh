#!/bin/bash
set -e

# Ensure code files directory exists and is writable by appuser
CODE_FILES_PATH="${CODE_FILES_PATH:-/tmp/vbase-rce}"
APP_USER="${APP_USER:-appuser}"

# Fix permissions on the volume mount (runs as root initially)
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$CODE_FILES_PATH"
    chown -R "$APP_USER:$APP_USER" "$CODE_FILES_PATH"
    chmod 755 "$CODE_FILES_PATH"

    # Drop privileges and re-exec as appuser
    exec gosu "$APP_USER" "$0" "$@"
fi

# Now running as appuser, execute the main command
exec "$@"
