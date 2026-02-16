#!/bin/sh
set -e

echo "Starting deployment script..."
echo "Current PORT environment variable is: '$PORT'"

# Set default port if PORT is empty
SERVER_PORT=${PORT:-8000}
echo "Starting uvicorn on port: $SERVER_PORT"

# Use exec to replace the shell with the uvicorn process
exec uvicorn src.web.app:app --host 0.0.0.0 --port "$SERVER_PORT"
