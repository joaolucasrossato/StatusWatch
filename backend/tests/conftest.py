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
