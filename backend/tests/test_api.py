import pytest


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "StatusWatch", "version": "0.4.0"}


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
