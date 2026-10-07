# Application metrics

The API exposes Prometheus text at `GET /metrics`. The worker exposes its own
HTTP server on `WORKER_METRICS_PORT` (default `9101`), inside the container network.
The root development and production Compose files pass this setting without
publishing the worker port. Each process has an independent registry; no
Prometheus multiprocess mode is used.

All names below have the `statuswatch_` prefix. Histograms also expose `_bucket`,
`_count` and `_sum` samples. Labelled series appear after the first matching event;
the metric families are exposed even before that event.

| Process | Metric | Labels / meaning |
| --- | --- | --- |
| API | `api_http_requests_total` | `method`, route template or `unmatched`, `status_code` |
| API | `api_http_request_duration_seconds` | `method`, `route`; time until response headers are available |
| API | `api_http_requests_in_progress` | `method`; active requests until response headers |
| Worker | `monitor_checks_total` | `status`: `UP`, `DOWN`; committed checks |
| Worker | `monitor_check_failures_total` | `error_type`: fixed checker error codes, `http_error` for unsuccessful HTTP status; unknown codes become `unexpected_error` |
| Worker | `monitor_check_duration_seconds` | `status`; committed check latency, milliseconds converted to seconds |
| Worker | `incident_transitions_total` | `event`: `opened`, `resolved`; committed transitions |
| Worker | `scheduler_cycles_total` | `result`: `success`, `error`; completed cycles, not individual check outcomes |
| Worker | `scheduler_cycle_duration_seconds` | Cycle execution time, including interrupted cycles, excluding poll/sleep |
| Worker | `notification_delivery_attempts_total` | `channel_type`: `EMAIL`, `WEBHOOK`; `outcome`: `success`, `error`, `cancelled` |
| Worker | `notification_deliveries_total` | `channel_type`, terminal `status`: `SENT`, `FAILED`; counted after commit |
| Worker | `notification_delivery_retries_total` | `channel_type`; committed return to `PENDING` following an error |
| Worker | `notification_delivery_duration_seconds` | `channel_type`; external attempt time, excluding claim and completion transactions |

The API does not instrument `/metrics`. Nonstandard HTTP methods use `OTHER`.
Labels contain no IDs, targets, credentials, payloads or exception messages.

Notification attempts describe the external operation, even if the subsequent
commit fails. Cancellation propagates and does not claim that a terminal state
was persisted. For SMTP, cancellation of the async waiter cannot stop an already
running synchronous send; `cancelled` describes interruption of that waiter.
Retries remain at 60 and 300 seconds, with at most three attempts.

Disabled channels and exhausted/expired claims count `FAILED` only after commit,
without creating external attempt or retry samples. Deleting a channel cascades
to its deliveries; deletion is not a terminal delivery transition. If the defensive
missing-channel branch ever encounters an orphan despite the foreign key, no
channel-labelled metric is fabricated because the channel type is unavailable.

These are process counters, not a durable audit ledger: restarts reset them, and
a process crash between commit and increment can lose an observation. Persisted
state counters are emitted in the persistence thread after successful commit so
cancellation of its async waiter does not skip the increment.

No open-incident gauge is maintained without database reconciliation. Prometheus
scraping, Grafana, exporters, alerts, dashboards, SLOs and additional infrastructure
are left for the separate manual DevOps stage.
