import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

import httpx

from app.core.config import Settings
from app.monitoring.checker import destination


class DeliveryError(Exception):
    """Only fixed, non-sensitive error codes may be persisted."""


def send_email(settings: Settings, target: str, payload: dict[str, Any], delivery_id: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise DeliveryError('smtp_not_configured')
    monitor, incident = payload['monitor'], payload['incident']
    event = 'Incident opened' if payload['event'] == 'INCIDENT_OPENED' else 'Incident resolved'
    message = EmailMessage()
    message['Subject'] = f'StatusWatch — {event}'
    message['From'] = settings.smtp_from
    message['To'] = target
    message['Message-ID'] = f'<{delivery_id}@statuswatch.local>'
    message.set_content('\n'.join([
        'StatusWatch', event, f"Monitor: {monitor['name']}", f"URL: {monitor['url']}",
        f"Started at: {incident['started_at']}", f"Opened at: {incident['opened_at']}",
        *([f"Resolved at: {incident['resolved_at']}"] if incident['resolved_at'] else []),
    ]))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        if smtp.send_message(message):
            raise DeliveryError('smtp_recipient_refused')


async def send_webhook(client: httpx.AsyncClient, target: str, payload: dict[str, Any], delivery_id: str) -> None:
    async with asyncio.timeout(10):
        url = httpx.URL(target)
        address = await destination(url)
        pinned = url.copy_with(host=address, fragment=None)
        async with client.stream('POST', pinned, json=payload,
                                 headers={'Host': url.netloc.decode('ascii'), 'Idempotency-Key': delivery_id},
                                 extensions={'sni_hostname': url.host}, timeout=10, follow_redirects=False) as response:
            if not 200 <= response.status_code < 300:
                raise DeliveryError('webhook_http_error')
