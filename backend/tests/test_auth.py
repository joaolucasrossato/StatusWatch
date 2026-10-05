import pytest


def test_auth_regression(client, accounts):
    user, headers = accounts[0]
    assert client.get("/auth/me", headers=headers).json() == user
    assert "password_hash" not in user
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/register", json={"email": user["email"], "full_name": "Alice", "password": "test-password-only-123"}).status_code == 409
    assert client.post("/auth/login", json={"email": user["email"], "password": "wrong"}).status_code == 401


@pytest.mark.parametrize("inactive", [True, False])
def test_inactive_or_deleted_user(client, accounts, db, inactive):
    import uuid
    from app.models import User

    user, headers = accounts[0]
    record = db.get(User, uuid.UUID(user["id"]))
    if inactive:
        record.is_active = False
    else:
        db.delete(record)
    db.commit()
    assert client.get("/monitors", headers=headers).status_code == (403 if inactive else 401)


@pytest.mark.parametrize('expiry', ['expired', 'missing'])
def test_invalid_expiry_rejected(client, accounts, expiry):
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core.config import settings
    payload = {'sub': accounts[0][0]['id'], 'type': 'access'}
    if expiry == 'expired':
        payload['exp'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401
