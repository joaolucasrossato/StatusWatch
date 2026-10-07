#!/bin/sh
set -eu

case "$WORKER_METRICS_PORT" in
  ''|*[!0-9]*)
    echo 'Invalid worker metrics port' >&2
    exit 1
    ;;
esac

sed "s/worker:9101/worker:$WORKER_METRICS_PORT/g" \
  /etc/prometheus/prometheus.yml \
  > /tmp/prometheus.yml

exec /bin/prometheus \
  --config.file=/tmp/prometheus.yml \
  --storage.tsdb.path=/prometheus