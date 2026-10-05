import pytest


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "StatusWatch", "version": "1.0.0"}


def test_health_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "healthy",
        "services": {"api": "healthy", "database": "healthy", "redis": "healthy"},
    }


@pytest.mark.parametrize("failed", [("database",), ("redis",), ("database", "redis")])
def test_health_unavailable(client, dependencies, failed):
    services = {"database": "healthy", "redis": "healthy"}
    services.update({name: "unhealthy" for name in failed})
    dependencies.check.return_value = services
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "services": {"api": "healthy", **services},
    }


def test_validation_does_not_echo_password(client, db):
    response = client.post('/auth/register', json={'email': 'test@example.com', 'full_name': 'Test', 'password': 'sensitive'})
    assert response.status_code == 422
    assert 'sensitive' not in response.text
    assert 'input' not in response.text


def test_database_unavailable_is_sanitized(client, db, monkeypatch):
    from sqlalchemy.exc import OperationalError
    def fail(*args, **kwargs):
        raise OperationalError('secret statement', {}, Exception('private details'))
    monkeypatch.setattr(db, 'scalar', fail)
    response = client.post('/auth/login', json={'email': 'test@example.com', 'password': 'password'})
    assert response.status_code == 503
    assert response.json() == {'detail': 'Service temporarily unavailable'}
