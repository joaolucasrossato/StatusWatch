import uuid

import pytest
from sqlalchemy import select

from app.models import Monitor, User

VALID = {"name": "  Example API  ", "url": "https://example.com/health"}


@pytest.mark.parametrize("method,path", [("post", "/monitors"), ("get", "/monitors"),
    ("get", "/monitors/00000000-0000-0000-0000-000000000001"),
    ("patch", "/monitors/00000000-0000-0000-0000-000000000001"),
    ("delete", "/monitors/00000000-0000-0000-0000-000000000001")])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_auth_required(client, db, method, path, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.request(method, path, headers=headers, json=VALID)
    assert response.status_code == 401


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("interval", [30, 60, 300, 600])
def test_create(client, accounts, scheme, interval):
    user, headers = accounts[0]
    response = client.post("/monitors", headers=headers, json={**VALID, "url": f"{scheme}://example.com", "interval_seconds": interval})
    assert response.status_code == 201
    monitor = response.json()
    assert monitor["user_id"] == user["id"]
    assert monitor["name"] == "Example API"
    assert monitor["method"] == "GET"
    assert monitor["timeout_seconds"] == 10
    assert monitor["is_active"] is True
    assert monitor["created_at"] and monitor["updated_at"]


INVALID = [
    ("url", "ftp://example.com"), ("url", "file:///etc/passwd"),
    ("url", "javascript:alert(1)"), ("url", "data:text/plain,hello"),
    ("url", "https://"), ("url", "https://example.com/" + "a" * 2083),
    ("method", "POST"), ("method", "PUT"), ("method", "PATCH"), ("method", "DELETE"),
    ("interval_seconds", 31), ("timeout_seconds", 0), ("timeout_seconds", 31),
    ("timeout_seconds", 1.5), ("name", ""), ("name", "   "), ("name", "a" * 121),
    ("user_id", str(uuid.uuid4())), ("id", str(uuid.uuid4())), ("created_at", "2026-01-01"),
]


@pytest.mark.parametrize("field,value", INVALID)
def test_create_validation(client, accounts, field, value):
    response = client.post("/monitors", headers=accounts[0][1], json={**VALID, field: value})
    assert response.status_code == 422


@pytest.mark.parametrize("field,value", INVALID + [(key, None) for key in
    ("name", "url", "method", "interval_seconds", "timeout_seconds", "is_active")])
def test_patch_validation(client, accounts, field, value):
    headers = accounts[0][1]
    monitor = client.post("/monitors", headers=headers, json=VALID).json()
    response = client.patch(f"/monitors/{monitor['id']}", headers=headers, json={field: value})
    assert response.status_code == 422
    assert client.get(f"/monitors/{monitor['id']}", headers=headers).json() == monitor


def test_two_user_isolation_and_lifecycle(client, accounts):
    alice, bob = accounts[0][1], accounts[1][1]
    original = client.post("/monitors", headers=alice, json=VALID).json()
    path = f"/monitors/{original['id']}"
    assert client.get(path, headers=alice).json() == original
    assert client.get("/monitors", headers=alice).json() == [original]
    assert client.get("/monitors", headers=bob).json() == []
    for method in ("get", "patch", "delete"):
        assert client.request(method, path, headers=bob, json={"name": "Hijacked"}).status_code == 404
    changed = client.patch(path, headers=alice, json={"is_active": False}).json()
    assert changed["is_active"] is False
    for key in ("id", "user_id", "name", "url", "created_at", "interval_seconds", "timeout_seconds"):
        assert changed[key] == original[key]
    assert client.patch(path, headers=alice, json={}).status_code == 200
    assert client.patch(path, headers=alice, json={"name": "Renamed", "timeout_seconds": 30}).json()["name"] == "Renamed"
    deleted = client.delete(path, headers=alice)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(path, headers=alice).status_code == 404
    assert client.get("/monitors", headers=alice).json() == []


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_missing_and_invalid_uuid(client, accounts, method):
    for identifier, expected in [(str(uuid.uuid4()), 404), ("invalid", 422)]:
        assert client.request(method, f"/monitors/{identifier}", headers=accounts[0][1], json={}).status_code == expected


def test_relationship_and_cascade(client, accounts, db):
    user, headers = accounts[0]
    created = client.post("/monitors", headers=headers, json=VALID).json()
    owner = db.get(User, uuid.UUID(user["id"]))
    assert owner.monitors[0].id == uuid.UUID(created["id"])
    assert owner.monitors[0].user is owner
    db.expire(owner, ["monitors"])
    db.delete(owner)
    db.commit()
    assert db.scalar(select(Monitor)) is None
