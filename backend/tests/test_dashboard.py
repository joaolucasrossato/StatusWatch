from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app.models import MonitorCheck


def create_monitor(client, headers, name="Dashboard Monitor", is_active=True):
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

    monitor = response.json()

    if not is_active:
        response = client.patch(
            f"/monitors/{monitor['id']}",
            headers=headers,
            json={"is_active": False},
        )
        assert response.status_code == 200
        monitor = response.json()

    return monitor


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


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_dashboard_requires_authentication(client, db, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    response = client.get("/dashboard/summary", headers=headers)

    assert response.status_code == 401


def test_empty_dashboard(client, accounts):
    headers = accounts[0][1]

    response = client.get("/dashboard/summary", headers=headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "total_monitors": 0,
        "active_monitors": 0,
        "paused_monitors": 0,
        "up_monitors": 0,
        "down_monitors": 0,
        "pending_monitors": 0,
        "checks_last_24h": 0,
        "average_response_time_ms_24h": None,
    }


def test_active_monitor_without_checks_is_pending(client, accounts):
    headers = accounts[0][1]
    create_monitor(client, headers)

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["total_monitors"] == 1
    assert data["active_monitors"] == 1
    assert data["paused_monitors"] == 0
    assert data["up_monitors"] == 0
    assert data["down_monitors"] == 0
    assert data["pending_monitors"] == 1
    assert data["checks_last_24h"] == 0
    assert data["average_response_time_ms_24h"] is None


def test_latest_up_check_marks_monitor_up(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    add_check(db, monitor["id"], status="UP", response_time_ms=120)

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["active_monitors"] == 1
    assert data["up_monitors"] == 1
    assert data["down_monitors"] == 0
    assert data["pending_monitors"] == 0
    assert data["checks_last_24h"] == 1
    assert data["average_response_time_ms_24h"] == 120.0


def test_latest_down_check_marks_monitor_down(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=250,
        http_status_code=500,
    )

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["up_monitors"] == 0
    assert data["down_monitors"] == 1
    assert data["pending_monitors"] == 0


def test_latest_check_wins(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)
    now = datetime.now(timezone.utc)

    add_check(
        db,
        monitor["id"],
        status="DOWN",
        response_time_ms=300,
        http_status_code=500,
        checked_at=now - timedelta(minutes=2),
    )
    add_check(
        db,
        monitor["id"],
        status="UP",
        response_time_ms=100,
        http_status_code=200,
        checked_at=now,
    )

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["up_monitors"] == 1
    assert data["down_monitors"] == 0
    assert data["pending_monitors"] == 0


def test_paused_monitor_is_not_counted_as_operational(client, accounts, db):
    headers = accounts[0][1]
    monitor = create_monitor(client, headers)

    add_check(db, monitor["id"], status="UP", response_time_ms=90)

    response = client.patch(
        f"/monitors/{monitor['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["total_monitors"] == 1
    assert data["active_monitors"] == 0
    assert data["paused_monitors"] == 1
    assert data["up_monitors"] == 0
    assert data["down_monitors"] == 0
    assert data["pending_monitors"] == 0

    # Historical metrics remain available even while the monitor is paused.
    assert data["checks_last_24h"] == 1
    assert data["average_response_time_ms_24h"] == 90.0


def test_dashboard_multiple_monitor_states(client, accounts, db):
    headers = accounts[0][1]

    up = create_monitor(client, headers, "UP Monitor")
    down = create_monitor(client, headers, "DOWN Monitor")
    create_monitor(client, headers, "Pending Monitor")
    paused = create_monitor(client, headers, "Paused Monitor")

    add_check(db, up["id"], status="UP", response_time_ms=100)
    add_check(
        db,
        down["id"],
        status="DOWN",
        response_time_ms=200,
        http_status_code=500,
    )
    add_check(db, paused["id"], status="UP", response_time_ms=300)

    response = client.patch(
        f"/monitors/{paused['id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["total_monitors"] == 4
    assert data["active_monitors"] == 3
    assert data["paused_monitors"] == 1
    assert data["up_monitors"] == 1
    assert data["down_monitors"] == 1
    assert data["pending_monitors"] == 1

    assert (
        data["up_monitors"]
        + data["down_monitors"]
        + data["pending_monitors"]
        == data["active_monitors"]
    )


def test_dashboard_isolated_by_user(client, accounts, db):
    alice_headers = accounts[0][1]
    bob_headers = accounts[1][1]

    alice_monitor = create_monitor(client, alice_headers, "Alice")
    bob_monitor = create_monitor(client, bob_headers, "Bob")

    add_check(db, alice_monitor["id"], status="UP", response_time_ms=100)
    add_check(
        db,
        bob_monitor["id"],
        status="DOWN",
        response_time_ms=900,
        http_status_code=500,
    )

    alice = client.get("/dashboard/summary", headers=alice_headers).json()
    bob = client.get("/dashboard/summary", headers=bob_headers).json()

    assert alice["total_monitors"] == 1
    assert alice["up_monitors"] == 1
    assert alice["down_monitors"] == 0
    assert alice["checks_last_24h"] == 1
    assert alice["average_response_time_ms_24h"] == 100.0

    assert bob["total_monitors"] == 1
    assert bob["up_monitors"] == 0
    assert bob["down_monitors"] == 1
    assert bob["checks_last_24h"] == 1
    assert bob["average_response_time_ms_24h"] == 900.0


def test_dashboard_24h_metrics_ignore_old_checks(client, accounts, db):
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
        status="UP",
        response_time_ms=200,
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

    data = client.get("/dashboard/summary", headers=headers).json()

    assert data["checks_last_24h"] == 2
    assert data["average_response_time_ms_24h"] == 150.0
