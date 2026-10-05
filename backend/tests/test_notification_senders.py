import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.monitoring.checker import DestinationError
from app.notifications.senders import DeliveryError, send_email, send_webhook

PAYLOAD = {'event': 'INCIDENT_RESOLVED', 'monitor': {'name': 'API', 'url': 'https://example.com'},
           'incident': {'started_at': 'start', 'opened_at': 'open', 'resolved_at': 'resolved'}}


def test_email_content_and_tls():
    with patch('app.notifications.senders.smtplib.SMTP') as smtp:
        smtp.return_value.__enter__.return_value.send_message.return_value = {}
        send_email(Settings(smtp_host='smtp.example.com', smtp_from='status@example.com'), 'alerts@example.com', PAYLOAD, 'delivery-id')
        connection = smtp.return_value.__enter__.return_value
        connection.starttls.assert_called_once()
        message = connection.send_message.call_args.args[0]
        assert 'Incident resolved' in message['Subject']
        for value in ('StatusWatch', 'API', 'https://example.com', 'start', 'open', 'resolved'):
            assert value in message.get_content()
        assert message['Message-ID'] == '<delivery-id@statuswatch.local>'


def test_smtp_not_configured():
    with pytest.raises(DeliveryError, match='smtp_not_configured'):
        send_email(Settings(smtp_host='', smtp_from=''), 'alerts@example.com', PAYLOAD, 'id')


def test_webhook_pinned_post_and_no_redirects(monkeypatch):
    monkeypatch.setattr('app.notifications.senders.destination', AsyncMock(return_value='93.184.216.34'))
    seen = []
    def transport(request):
        seen.append(request)
        return httpx.Response(204)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            await send_webhook(client, 'https://example.com/hook', PAYLOAD, 'delivery-id')
    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0].method == 'POST' and seen[0].url.host == '93.184.216.34'
    assert seen[0].headers['host'] == 'example.com'
    assert seen[0].extensions['sni_hostname'] == 'example.com'
    assert seen[0].headers['idempotency-key'] == 'delivery-id'
    assert 'authorization' not in seen[0].headers


@pytest.mark.parametrize('code', [301, 302, 307, 308, 400, 429, 500])
def test_webhook_non_success_and_redirect_rejected(monkeypatch, code):
    monkeypatch.setattr('app.notifications.senders.destination', AsyncMock(return_value='93.184.216.34'))
    seen = []
    def transport(request):
        seen.append(request)
        return httpx.Response(code, headers={'location': 'http://127.0.0.1'})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            with pytest.raises(DeliveryError, match='webhook_http_error'):
                await send_webhook(client, 'https://example.com', PAYLOAD, 'id')
    asyncio.run(run())
    assert len(seen) == 1


@pytest.mark.parametrize('target', ['http://localhost', 'http://127.0.0.1', 'http://[::1]', 'http://10.1.1.1', 'http://169.254.169.254'])
def test_worker_revalidates_private_targets(target):
    client = MagicMock()
    with pytest.raises(DestinationError): asyncio.run(send_webhook(client, target, PAYLOAD, 'id'))
    client.stream.assert_not_called()


def test_worker_revalidates_dns_rebinding(monkeypatch):
    from app.monitoring.checker import destination
    async def rebound(url): return await destination(url, AsyncMock(return_value=['10.0.0.1']))
    monkeypatch.setattr('app.notifications.senders.destination', rebound)
    client = MagicMock()
    with pytest.raises(DestinationError): asyncio.run(send_webhook(client, 'https://example.com', PAYLOAD, 'id'))
    client.stream.assert_not_called()
