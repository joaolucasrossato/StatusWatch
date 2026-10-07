import os

# Isolated test configuration; never load developer credentials.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["REDIS_URL"] = "redis://localhost/15"
os.environ["JWT_SECRET"] = "statuswatch-test-only-secret-not-for-deployment"

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_dependencies


@pytest.fixture
def dependencies():
    dependency = Mock()
    dependency.check.return_value = {"database": "healthy", "redis": "healthy"}
    return dependency


@pytest.fixture
def client(dependencies):
    app.dependency_overrides[get_dependencies] = lambda: dependencies
    # No lifespan: unit tests do not create external connections or need secrets.
    with_override = TestClient(app)
    try:
        yield with_override
    finally:
        with_override.close()
        app.dependency_overrides.clear()


@pytest.fixture
def db(client):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.db.base import Base
    from app.db.session import get_db

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        def override_db():
            yield session
        app.dependency_overrides[get_db] = override_db
        yield session
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture
def accounts(client, db):
    result = []
    for name in ("alice", "bob"):
        credentials = {"email": f"{name}@example.com", "password": "test-password-only-123"}
        response = client.post("/auth/register", json={**credentials, "full_name": name.title()})
        assert response.status_code == 201
        user = response.json()
        token = client.post("/auth/login", json=credentials)
        assert token.status_code == 200
        headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
        result.append((user, headers))
    return result


@pytest.fixture
def metric_value():
    from prometheus_client import REGISTRY

    def value(name, **labels):
        return REGISTRY.get_sample_value('statuswatch_' + name, labels) or 0

    return value


@pytest.fixture
def fail_commit():
    from sqlalchemy import event

    def install(sessions):
        def fail(session):
            # Exercise rollback even after all pending writes were flushed.
            session.flush()
            raise RuntimeError('commit failed')
        event.listen(sessions, 'before_commit', fail)

    return install
