from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app.models import MonitorCheck


def create_monitor(client, headers, name="History Monitor"):
    response = client.post(
        "/monitors",
        headers=headers,
        json={
            "name": name,
            "url": "https://example.com",
            "interval_seconds": 30,
            "timeout_seconds": 10,
        },
    )
    assert response.status_code == 201
    return response.json()


def add_check(
    db,
    monitor_id,
    *,
    status="UP",
    response_time_ms=100,
    http_status_code=200,
    checked_at=None,
):
    check = MonitorCheck(
        monitor_id=uuid.UUID(monitor_id),
        status=status,
        http_status_code=http_status_code,
        response_time_ms=response_time_ms,
        checked_at=checked_at or datetime.now(timezone.utc),
    )
    db.add(check)
    db.commit()
    return check


@pytest.mark.parametrize("endpoint", ["checks", "stats"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_history_and_stats_require_authentication(client, db, endpoint, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    response = client.get(
        f"/monitors/{uuid.uuid4()}/{endpoint}",
        headers=headers,
    )

    assert response.status_code == 401


@pytest.mark.parametrize("endpoint", ["checks", "stats"])
def test_missing_monitor_returns_404(client, accounts, endpoint):
    headers = accounts[0][1]

    response = client.get(
        f"/monitors/{uuid.uuid4()}/{endpoint}",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("endpoint", ["checks", "stats"])
def test_other_user_monitor_returns_404(client, accounts, endpoint):
    alice_headers = accounts[0][1]
    bob_headers = accounts[1][1]

    monitor = create_monitor(client, alice_headers)

    response = client.get(
        f"/monitors/{monitor['id']}/{endpoint}",
        headers=bob_headers,
    )

    assert response.status_code == 404


def test_empty_history(client, accounts):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    response = client.get(
        f"/monitors/{monitor['id']}/checks",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    data = response.json()

    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


def test_history_is_newest_first(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)
    now = datetime.now(timezone.utc)

    add_check(
        db,
        monitor["id"],
        response_time_ms=100,
        checked_at=now - timedelta(minutes=2),
    )
    add_check(
        db,
        monitor["id"],
        response_time_ms=200,
        checked_at=now - timedelta(minutes=1),
    )
    add_check(
        db,
        monitor["id"],
        response_time_ms=300,
        checked_at=now,
    )

    response = client.get(
        f"/monitors/{monitor['id']}/checks",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 3
    assert [item["response_time_ms"] for item in data["items"]] == [
        300,
        200,
        100,
    ]


def test_history_pagination(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)
    now = datetime.now(timezone.utc)

    for index in range(4):
        add_check(
            db,
            monitor["id"],
            response_time_ms=(index + 1) * 100,
            checked_at=now + timedelta(seconds=index),
        )

    first = client.get(
        f"/monitors/{monitor['id']}/checks?limit=2&offset=0",
        headers=headers,
    )
    second = client.get(
        f"/monitors/{monitor['id']}/checks?limit=2&offset=2",
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_data = first.json()
    second_data = second.json()

    assert first_data["total"] == 4
    assert first_data["limit"] == 2
    assert first_data["offset"] == 0
    assert [item["response_time_ms"] for item in first_data["items"]] == [
        400,
        300,
    ]

    assert second_data["total"] == 4
    assert second_data["limit"] == 2
    assert second_data["offset"] == 2
    assert [item["response_time_ms"] for item in second_data["items"]] == [
        200,
        100,
    ]


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
    ],
)
def test_history_parameter_validation(client, accounts, query):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    response = client.get(
        f"/monitors/{monitor['id']}/checks?{query}",
        headers=headers,
    )

    assert response.status_code == 422


def test_stats_without_checks(client, accounts):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    response = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours=24",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"

    data = response.json()

    assert data["monitor_id"] == monitor["id"]
    assert data["window_hours"] == 24
    assert data["total_checks"] == 0
    assert data["successful_checks"] == 0
    assert data["failed_checks"] == 0
    assert data["uptime_percentage"] is None
    assert data["average_response_time_ms"] is None
    assert data["minimum_response_time_ms"] is None
    assert data["maximum_response_time_ms"] is None


@pytest.mark.parametrize(
    ("status", "expected_uptime"),
    [
        ("UP", 100.0),
        ("DOWN", 0.0),
    ],
)
def test_stats_all_same_status(
    client,
    accounts,
    db,
    status,
    expected_uptime,
):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    for response_time in (100, 200, 300):
        add_check(
            db,
            monitor["id"],
            status=status,
            response_time_ms=response_time,
            http_status_code=200 if status == "UP" else 500,
        )

    data = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours=24",
        headers=headers,
    ).json()

    assert data["total_checks"] == 3
    assert data["successful_checks"] == (3 if status == "UP" else 0)
    assert data["failed_checks"] == (3 if status == "DOWN" else 0)
    assert data["uptime_percentage"] == expected_uptime
    assert data["average_response_time_ms"] == 200.0
    assert data["minimum_response_time_ms"] == 100
    assert data["maximum_response_time_ms"] == 300


def test_stats_mixed_results(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    add_check(db, monitor["id"], status="UP", response_time_ms=100)
    add_check(db, monitor["id"], status="UP", response_time_ms=200)
    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=300,
        http_status_code=500,
    )

    data = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours=24",
        headers=headers,
    ).json()

    assert data["total_checks"] == 3
    assert data["successful_checks"] == 2
    assert data["failed_checks"] == 1
    assert data["uptime_percentage"] == pytest.approx(66.67, abs=0.01)
    assert data["average_response_time_ms"] == 200.0
    assert data["minimum_response_time_ms"] == 100
    assert data["maximum_response_time_ms"] == 300


def test_stats_ignore_checks_outside_window(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)
    now = datetime.now(timezone.utc)

    add_check(
        db,
        monitor["id"],
        status="UP",
        response_time_ms=100,
        checked_at=now - timedelta(hours=1),
    )
    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=200,
        http_status_code=500,
        checked_at=now - timedelta(hours=2),
    )
    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=1000,
        http_status_code=500,
        checked_at=now - timedelta(hours=25),
    )

    data = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours=24",
        headers=headers,
    ).json()

    assert data["total_checks"] == 2
    assert data["successful_checks"] == 1
    assert data["failed_checks"] == 1
    assert data["uptime_percentage"] == 50.0
    assert data["average_response_time_ms"] == 150.0
    assert data["minimum_response_time_ms"] == 100
    assert data["maximum_response_time_ms"] == 200


def test_stats_ignore_null_response_times(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=None,
        http_status_code=None,
    )
    add_check(
        db,
        monitor["id"],
        status="UP",
        response_time_ms=120,
        http_status_code=200,
    )

    data = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours=24",
        headers=headers,
    ).json()

    assert data["total_checks"] == 2
    assert data["successful_checks"] == 1
    assert data["failed_checks"] == 1
    assert data["uptime_percentage"] == 50.0

    # SQL aggregate functions ignore NULL response times.
    assert data["average_response_time_ms"] == 120.0
    assert data["minimum_response_time_ms"] == 120
    assert data["maximum_response_time_ms"] == 120


@pytest.mark.parametrize("window_hours", [0, 169])
def test_stats_window_validation(client, accounts, window_hours):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    response = client.get(
        f"/monitors/{monitor['id']}/stats?window_hours={window_hours}",
        headers=headers,
    )

    assert response.status_code == 422
