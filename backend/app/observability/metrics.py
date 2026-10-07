from prometheus_client import Counter, Gauge, Histogram


API_HTTP_REQUESTS = Counter(
    "statuswatch_api_http_requests_total",
    "Total number of HTTP requests handled by the StatusWatch API.",
    labelnames=("method", "route", "status_code"),
)

API_HTTP_REQUEST_DURATION = Histogram(
    "statuswatch_api_http_request_duration_seconds",
    "Duration of HTTP requests handled by the StatusWatch API.",
    labelnames=("method", "route"),
    buckets=(
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
    ),
)

API_HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "statuswatch_api_http_requests_in_progress",
    "Number of HTTP requests currently being handled by the StatusWatch API.",
    labelnames=("method",),
)
