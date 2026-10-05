import uuid
from unittest.mock import AsyncMock

import pytest

from app.models import NotificationChannel
from app.monitoring.checker import DestinationError
from test_incidents import create_monitor


@pytest.fixture
def channel_monitor(client, accounts):
    return create_monitor(client, accounts[0][1])


def create(client, accounts, monitor, **changes):
    return client.post('/notification-channels', headers=accounts[0][1], json={
        'monitor_id': monitor['id'], 'type': 'EMAIL', 'target': 'alerts@example.com', **changes,
    })


def test_channel_crud_and_masking(client, accounts, db, channel_monitor, monkeypatch):
    monkeypatch.setattr('app.services.notification_channels.destination', AsyncMock(return_value='93.184.216.34'))
    email = create(client, accounts, channel_monitor)
    assert email.status_code == 201
    assert email.headers['cache-control'] == 'no-store'
    webhook = create(client, accounts, channel_monitor, type='WEBHOOK', target='https://example.com/private-path?key=test-only')
    assert webhook.status_code == 201
    assert webhook.json()['target'] == 'https://example.com/…'
    assert webhook.json()['target_redacted'] is True
    assert 'private-path' not in webhook.text and 'test-only' not in webhook.text
    path = '/notification-channels/' + webhook.json()['id']
    updated = client.patch(path, headers=accounts[0][1], json={'is_active': False, 'notify_on_open': False})
    assert updated.status_code == 200 and not updated.json()['is_active']
    db.expire_all()
    assert db.get(NotificationChannel, uuid.UUID(webhook.json()['id'])).target.endswith('key=test-only')
    assert len(client.get('/notification-channels', headers=accounts[0][1]).json()) == 2
    assert len(client.get(f"/monitors/{channel_monitor['id']}/notification-channels", headers=accounts[0][1]).json()) == 2
    assert client.patch('/notification-channels/' + email.json()['id'], headers=accounts[0][1], json={'target': 'new@example.com'}).json()['target'] == 'new@example.com'
    assert client.delete(path, headers=accounts[0][1]).status_code == 204
    assert client.delete(path, headers=accounts[0][1]).status_code == 404


def test_channel_ownership(client, accounts, db, channel_monitor):
    channel = create(client, accounts, channel_monitor).json()
    path = '/notification-channels/' + channel['id']
    assert client.patch(path, headers=accounts[1][1], json={'is_active': False}).status_code == 404
    assert client.delete(path, headers=accounts[1][1]).status_code == 404
    assert client.get('/notification-channels', headers=accounts[1][1]).json() == []
    assert client.get(f"/monitors/{channel_monitor['id']}/notification-channels", headers=accounts[1][1]).status_code == 404
    foreign = create_monitor(client, accounts[1][1])
    assert create(client, accounts, foreign).status_code == 404
    assert create(client, accounts, channel_monitor, user_id=accounts[1][0]['id']).status_code == 422


@pytest.mark.parametrize('target', ['localhost', '127.0.0.1', '[::1]', '10.0.0.1', '192.168.1.1', '169.254.169.254', '[fe80::1]'])
def test_webhook_blocks_private_addresses(client, accounts, channel_monitor, target):
    assert create(client, accounts, channel_monitor, type='WEBHOOK', target=f'http://{target}/').status_code == 422


@pytest.mark.parametrize('changes', [
    {'target': 'not-email'}, {'type': 'SMS'}, {'type': 'WEBHOOK', 'target': 'file:///tmp/file'},
    {'type': 'WEBHOOK', 'target': 'https://user:password@example.com'},
    {'type': 'WEBHOOK', 'target': 'https://example.com/#fragment'}, {'target': ''},
])
def test_invalid_channels(client, accounts, channel_monitor, changes):
    assert create(client, accounts, channel_monitor, **changes).status_code == 422


def test_dns_private_and_patch_validation(client, accounts, channel_monitor, monkeypatch):
    monkeypatch.setattr('app.services.notification_channels.destination', AsyncMock(side_effect=DestinationError('ssrf_blocked')))
    assert create(client, accounts, channel_monitor, type='WEBHOOK', target='https://internal.example.com').status_code == 422
    channel = create(client, accounts, channel_monitor).json()
    for update in ({'target': 'bad'}, {'is_active': None}, {'monitor_id': str(uuid.uuid4())}, {'type': 'WEBHOOK'}):
        assert client.patch('/notification-channels/' + channel['id'], headers=accounts[0][1], json=update).status_code == 422


@pytest.mark.parametrize('method,path', [('get', '/notification-channels'), ('post', '/notification-channels'),
    ('patch', '/notification-channels/' + str(uuid.uuid4())), ('delete', '/notification-channels/' + str(uuid.uuid4())),
    ('get', '/notification-deliveries'), ('get', '/incidents/' + str(uuid.uuid4()) + '/notification-deliveries'),
    ('get', '/monitors/' + str(uuid.uuid4()) + '/notification-channels')])
def test_auth_required(client, db, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_validation_does_not_echo_target(client, accounts, channel_monitor):
    marker = 'test-only-sensitive-marker'
    response = create(client, accounts, channel_monitor, target=marker * 100)
    assert response.status_code == 422
    assert marker not in response.text


def test_dns_validation_releases_transaction(client, accounts, db, channel_monitor, monkeypatch):
    async def validate(kind, target):
        assert not db.in_transaction()
        return target
    monkeypatch.setattr('app.services.notification_channels.validate_target', validate)
    response = create(client, accounts, channel_monitor, type='WEBHOOK', target='https://example.com/?token=private')
    assert response.status_code == 201
    assert client.patch('/notification-channels/' + response.json()['id'], headers=accounts[0][1],
                        json={'target': 'https://example.com/?key=replacement'}).status_code == 200
