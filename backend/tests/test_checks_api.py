from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select

from app.models import Monitor, MonitorCheck, User


def test_latest_ownership_pending_ordering_cascade(client, accounts, db):
    owner, other = accounts[0][1], accounts[1][1]
    created = client.post("/monitors", headers=owner, json={"name": "Check", "url": "https://example.com"}).json()
    identifier = uuid.UUID(created['id'])
    path = f"/monitors/{identifier}/checks/latest"
    response = client.get(path, headers=owner)
    assert response.status_code == 200 and response.json() is None
    assert response.headers['cache-control'] == 'no-store'
    assert client.get(path, headers=other).status_code == 404
    assert client.get(f"/monitors/{uuid.uuid4()}/checks/latest", headers=owner).status_code == 404
    now = datetime.now(timezone.utc)
    old = MonitorCheck(monitor_id=identifier, status="DOWN", checked_at=now - timedelta(seconds=60))
    latest = MonitorCheck(monitor_id=identifier, status="UP", http_status_code=200, response_time_ms=142, checked_at=now)
    db.add_all([latest, old]); db.commit()
    response = client.get(path, headers=owner)
    assert response.json()['status'] == 'UP'
    assert response.json()['response_time_ms'] == 142
    assert 'monitor_id' not in response.json()
    assert client.get(path, headers=other).status_code == 404
    assert client.get('/monitors', headers=owner).json()[0]['latest_check'] == response.json()
    monitor = db.get(Monitor, identifier)
    assert latest in monitor.checks and latest.monitor is monitor
    db.expire(monitor, ['checks'])
    db.delete(db.get(User, uuid.UUID(accounts[0][0]['id']))); db.commit()
    assert db.scalar(select(MonitorCheck)) is None


@pytest.mark.parametrize('token', [None, 'invalid'])
def test_latest_auth(client, db, token):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    assert client.get(f'/monitors/{uuid.uuid4()}/checks/latest', headers=headers).status_code == 401


@pytest.mark.parametrize('url', ['https://user@example.com', 'https://user:secret@example.com'])
def test_userinfo_rejected_on_create_and_update(client, accounts, url):
    headers = accounts[0][1]
    assert client.post('/monitors', headers=headers, json={'name': 'Test', 'url': url}).status_code == 422
    monitor = client.post('/monitors', headers=headers, json={'name': 'Test', 'url': 'https://example.com'}).json()
    assert client.patch('/monitors/' + monitor['id'], headers=headers, json={'url': url}).status_code == 422
