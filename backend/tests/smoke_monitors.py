"""Exercise a running development API with synthetic accounts; never prints JWTs.

Usage: python tests/smoke_monitors.py http://127.0.0.1:8000
Creates two uniquely named test users and removes all monitors it creates.
"""
import json
import secrets
import sys
import urllib.error
import urllib.request
import uuid


def main(base: str) -> None:
    def request(method, path, expected, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, method=method, headers=headers,
                                     data=json.dumps(payload).encode() if payload is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            assert response.status == expected, (method, path, response.status, expected)
            return json.loads(body) if body else None

    request("GET", "/health", 200)
    accounts = []
    for label in ("a", "b"):
        credentials = {"email": f"smoke-{uuid.uuid4().hex}-{label}@example.com", "password": secrets.token_urlsafe(24)}
        user = request("POST", "/auth/register", 201, {**credentials, "full_name": "Smoke Test"})
        token = request("POST", "/auth/login", 200, credentials)["access_token"]
        assert request("GET", "/auth/me", 200, token=token)["id"] == user["id"]
        accounts.append((user, token))
    (owner, token), (_, other) = accounts
    request("GET", "/monitors", 401)
    request("GET", "/monitors", 401, token="invalid")
    valid = {"name": "Smoke monitor", "url": "https://example.com/health"}
    for field, value in [("url", "ftp://example.com"), ("method", "POST"), ("interval_seconds", 1), ("timeout_seconds", 31)]:
        request("POST", "/monitors", 422, {**valid, field: value}, token)
    created = request("POST", "/monitors", 201, valid, token)
    assert created["user_id"] == owner["id"]
    assert created["created_at"].endswith(("Z", "+00:00"))
    path = "/monitors/" + created["id"]
    assert request("GET", path, 200, token=token) == created
    assert request("GET", "/monitors", 200, token=token) == [created]
    assert request("GET", "/monitors", 200, token=other) == []
    request("GET", path, 404, token=other)
    request("PATCH", path, 404, {"name": "Not allowed"}, other)
    request("DELETE", path, 404, token=other)
    updated = request("PATCH", path, 200, {"is_active": False}, token)
    assert updated["is_active"] is False and updated["name"] == created["name"]
    assert updated["updated_at"] >= created["updated_at"]
    request("DELETE", path, 204, token=token)
    request("GET", path, 404, token=token)
    print("PASS: real HTTP auth, CRUD, validation, timestamps and two-user isolation")


if __name__ == "__main__":
    main(sys.argv[1].rstrip("/"))
