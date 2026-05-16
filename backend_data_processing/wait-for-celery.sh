#!/bin/bash
set -e

echo "[flower] Waiting for Celery worker to be ready..."

# Retry until Celery responds to `inspect ping`
MAX_RETRIES=20
RETRY_DELAY=5
COUNT=0

while ! celery -A dataprocessing inspect ping &>/dev/null; do
  COUNT=$((COUNT+1))
  echo "[flower] Celery not ready yet (attempt: $COUNT/$MAX_RETRIES)"
  if [ "$COUNT" -ge "$MAX_RETRIES" ]; then
    echo "[flower] Celery failed to respond after $MAX_RETRIES attempts. Exiting."
    exit 1
  fi
  sleep $RETRY_DELAY
done

echo "[flower] Celery is ready! Starting Flower UI..."
exec celery -A dataprocessing flower \
  --broker=redis://dataprocessing_redis:6379/0 \
  --basic_auth="${FLOWER_USER}:${FLOWER_PASSWORD}" \
  --enable_health_check
