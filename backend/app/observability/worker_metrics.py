from prometheus_client import Counter, Histogram


MONITOR_CHECKS = Counter(
    "statuswatch_monitor_checks_total",
    "Total number of persisted monitor checks.",
    labelnames=("status",),
)

MONITOR_CHECK_FAILURES = Counter(
    "statuswatch_monitor_check_failures_total",
    "Total number of persisted failed monitor checks.",
    labelnames=("error_type",),
)

MONITOR_CHECK_DURATION = Histogram(
    "statuswatch_monitor_check_duration_seconds",
    "Duration of persisted HTTP monitor checks.",
    labelnames=("status",),
    buckets=(
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
    ),
)

INCIDENT_TRANSITIONS = Counter(
    "statuswatch_incident_transitions_total",
    "Total number of committed incident lifecycle transitions.",
    labelnames=("event",),
)

SCHEDULER_CYCLES = Counter(
    "statuswatch_scheduler_cycles_total",
    "Total number of monitoring scheduler cycles.",
    labelnames=("result",),
)

SCHEDULER_CYCLE_DURATION = Histogram(
    "statuswatch_scheduler_cycle_duration_seconds",
    "Duration of monitoring scheduler cycles.",
    buckets=(
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

NOTIFICATION_DELIVERY_ATTEMPTS = Counter(
    "statuswatch_notification_delivery_attempts_total",
    "Total number of notification delivery attempts.",
    labelnames=("channel_type", "outcome"),
)

NOTIFICATION_DELIVERIES = Counter(
    "statuswatch_notification_deliveries_total",
    "Total number of notification deliveries reaching a terminal state.",
    labelnames=("channel_type", "status"),
)

NOTIFICATION_DELIVERY_RETRIES = Counter(
    "statuswatch_notification_delivery_retries_total",
    "Total number of notification deliveries scheduled for retry.",
    labelnames=("channel_type",),
)

NOTIFICATION_DELIVERY_DURATION = Histogram(
    "statuswatch_notification_delivery_duration_seconds",
    "Duration of notification delivery attempts.",
    labelnames=("channel_type",),
    buckets=(
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)
