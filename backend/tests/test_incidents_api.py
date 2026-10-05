import uuid
from datetime import datetime, timedelta, timezone

from app.models import Incident, Monitor


def create_monitor(client, headers, name="API Monitor"):
    response = client.post(
        "/monitors",
        headers=headers,
        json={
            "name": name,
            "url": "https://example.com",
            "method": "GET",
            "interval_seconds": 60,
            "timeout_seconds": 10,
        },
    )

    assert response.status_code == 201

    return response.json()


def add_incident(
    db,
    monitor_id,
    *,
    status="OPEN",
    started_at=None,
):
    started_at = started_at or datetime.now(timezone.utc)
    opened_at = started_at + timedelta(seconds=2)

    incident = Incident(
        monitor_id=uuid.UUID(monitor_id),
        status=status,
        started_at=started_at,
        opened_at=opened_at,
        resolved_at=(
            opened_at + timedelta(seconds=10)
            if status == "RESOLVED"
            else None
        ),
    )

    db.add(incident)
    db.commit()
    db.refresh(incident)

    return incident


def test_incidents_requires_authentication(client):
    response = client.get("/incidents")

    assert response.status_code == 401


def test_list_incidents_returns_only_owned_incidents(
    client,
    accounts,
    db,
):
    alice_monitor = create_monitor(
        client,
        accounts[0][1],
        name="Alice Monitor",
    )
    bob_monitor = create_monitor(
        client,
        accounts[1][1],
        name="Bob Monitor",
    )

    alice_incident = add_incident(
        db,
        alice_monitor["id"],
    )
    add_incident(
        db,
        bob_monitor["id"],
    )

    response = client.get(
        "/incidents",
        headers=accounts[0][1],
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    body = response.json()

    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 1

    assert body["items"][0]["id"] == str(alice_incident.id)
    assert body["items"][0]["monitor_id"] == alice_monitor["id"]
    assert body["items"][0]["status"] == "OPEN"


def test_get_incident_details(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )
    incident = add_incident(
        db,
        monitor["id"],
    )

    response = client.get(
        f"/incidents/{incident.id}",
        headers=accounts[0][1],
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    body = response.json()

    assert body["id"] == str(incident.id)
    assert body["monitor_id"] == monitor["id"]
    assert body["status"] == "OPEN"
    assert body["resolved_at"] is None


def test_incident_of_another_user_returns_404(
    client,
    accounts,
    db,
):
    bob_monitor = create_monitor(
        client,
        accounts[1][1],
        name="Bob Monitor",
    )
    incident = add_incident(
        db,
        bob_monitor["id"],
    )

    response = client.get(
        f"/incidents/{incident.id}",
        headers=accounts[0][1],
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Incident not found",
    }


def test_unknown_incident_returns_404(
    client,
    accounts,
):
    response = client.get(
        f"/incidents/{uuid.uuid4()}",
        headers=accounts[0][1],
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Incident not found",
    }


def test_list_monitor_incidents(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )
    incident = add_incident(
        db,
        monitor["id"],
    )

    response = client.get(
        f"/monitors/{monitor['id']}/incidents",
        headers=accounts[0][1],
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    body = response.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(incident.id)


def test_foreign_monitor_incidents_returns_404(
    client,
    accounts,
):
    monitor = create_monitor(
        client,
        accounts[1][1],
        name="Bob Monitor",
    )

    response = client.get(
        f"/monitors/{monitor['id']}/incidents",
        headers=accounts[0][1],
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Monitor not found",
    }


def test_unknown_monitor_incidents_returns_404(
    client,
    accounts,
):
    response = client.get(
        f"/monitors/{uuid.uuid4()}/incidents",
        headers=accounts[0][1],
    )

    assert response.status_code == 404


def test_incident_status_filters(
    client,
    accounts,
    db,
):
    open_monitor = create_monitor(
        client,
        accounts[0][1],
        name="Open Monitor",
    )
    resolved_monitor = create_monitor(
        client,
        accounts[0][1],
        name="Resolved Monitor",
    )

    open_incident = add_incident(
        db,
        open_monitor["id"],
        status="OPEN",
    )
    resolved_incident = add_incident(
        db,
        resolved_monitor["id"],
        status="RESOLVED",
    )

    response = client.get(
        "/incidents?status=OPEN",
        headers=accounts[0][1],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == str(open_incident.id)

    response = client.get(
        "/incidents?status=RESOLVED",
        headers=accounts[0][1],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == str(resolved_incident.id)


def test_monitor_incident_status_filter(
    client,
    accounts,
    db,
):
    monitor = create_monitor(
        client,
        accounts[0][1],
    )

    resolved_incident = add_incident(
        db,
        monitor["id"],
        status="RESOLVED",
    )

    add_incident(
        db,
        monitor["id"],
        status="OPEN",
    )

    response = client.get(
        f"/monitors/{monitor['id']}/incidents?status=RESOLVED",
        headers=accounts[0][1],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(resolved_incident.id)
    assert body["items"][0]["status"] == "RESOLVED"


def test_invalid_incident_status_returns_422(
    client,
    accounts,
):
    response = client.get(
        "/incidents?status=DOWN",
        headers=accounts[0][1],
    )

    assert response.status_code == 422


def test_incident_pagination_validation(
    client,
    accounts,
):
    headers = accounts[0][1]

    assert client.get(
        "/incidents?limit=0",
        headers=headers,
    ).status_code == 422

    assert client.get(
        "/incidents?limit=101",
        headers=headers,
    ).status_code == 422

    assert client.get(
        "/incidents?offset=-1",
        headers=headers,
    ).status_code == 422


def test_incident_pagination_and_ordering(
    client,
    accounts,
    db,
):
    first_monitor = create_monitor(
        client,
        accounts[0][1],
        name="First",
    )
    second_monitor = create_monitor(
        client,
        accounts[0][1],
        name="Second",
    )
    third_monitor = create_monitor(
        client,
        accounts[0][1],
        name="Third",
    )

    now = datetime.now(timezone.utc)

    oldest = add_incident(
        db,
        first_monitor["id"],
        started_at=now - timedelta(minutes=30),
    )
    middle = add_incident(
        db,
        second_monitor["id"],
        started_at=now - timedelta(minutes=20),
    )
    newest = add_incident(
        db,
        third_monitor["id"],
        started_at=now - timedelta(minutes=10),
    )

    response = client.get(
        "/incidents?limit=2&offset=0",
        headers=accounts[0][1],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0

    assert [
        item["id"]
        for item in body["items"]
    ] == [
        str(newest.id),
        str(middle.id),
    ]

    response = client.get(
        "/incidents?limit=2&offset=2",
        headers=accounts[0][1],
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(oldest.id)
