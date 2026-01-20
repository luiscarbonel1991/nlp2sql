#!/bin/bash
# Generate database connection URLs based on current environment variables

# Load .env file if it exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set defaults
SIMPLE_DB_USER=${SIMPLE_DB_USER:-testuser}
SIMPLE_DB_PASSWORD=${SIMPLE_DB_PASSWORD:-testpass}
SIMPLE_DB_NAME=${SIMPLE_DB_NAME:-testdb}
SIMPLE_DB_PORT=${SIMPLE_DB_PORT:-5432}

LARGE_DB_USER=${LARGE_DB_USER:-demo}
LARGE_DB_PASSWORD=${LARGE_DB_PASSWORD:-demo123}
LARGE_DB_NAME=${LARGE_DB_NAME:-enterprise}
LARGE_DB_PORT=${LARGE_DB_PORT:-5433}

echo "-- nlp2sql Database Connection URLs"
echo "=================================="
echo ""
echo "-- Simple Test Database:"
echo "postgresql://${SIMPLE_DB_USER}:${SIMPLE_DB_PASSWORD}@localhost:${SIMPLE_DB_PORT}/${SIMPLE_DB_NAME}"
echo ""
echo "-- Large Enterprise Database:"
echo "postgresql://${LARGE_DB_USER}:${LARGE_DB_PASSWORD}@localhost:${LARGE_DB_PORT}/${LARGE_DB_NAME}"
echo ""
echo "-- Export as environment variables:"
echo "export SIMPLE_DB_URL=\"postgresql://${SIMPLE_DB_USER}:${SIMPLE_DB_PASSWORD}@localhost:${SIMPLE_DB_PORT}/${SIMPLE_DB_NAME}\""
echo "export LARGE_DB_URL=\"postgresql://${LARGE_DB_USER}:${LARGE_DB_PASSWORD}@localhost:${LARGE_DB_PORT}/${LARGE_DB_NAME}\""
echo ""
echo "-- Quick test commands:"
echo "uv run nlp2sql inspect --database-url postgresql://${SIMPLE_DB_USER}:${SIMPLE_DB_PASSWORD}@localhost:${SIMPLE_DB_PORT}/${SIMPLE_DB_NAME}"
echo "uv run nlp2sql query --database-url postgresql://${SIMPLE_DB_USER}:${SIMPLE_DB_PASSWORD}@localhost:${SIMPLE_DB_PORT}/${SIMPLE_DB_NAME} --question \"Show me all active users\""