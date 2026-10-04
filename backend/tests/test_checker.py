import asyncio
import socket
import ssl
from unittest.mock import AsyncMock

import httpx
import pytest

from app.monitoring.checker import check_http, create_client, destination, DestinationError


async def public_dns(host, port):
    return ["93.184.216.34", "2606:4700:4700::1111"]


def run(handler, url="https://example.com/", timeout=2, resolver=public_dns, redirects=5):
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await check_http(client, url, timeout, redirects, resolver)
    return asyncio.run(check())


@pytest.mark.parametrize("code", [200, 204, 301, 302, 399, 400, 404, 500, 599])
def test_http_status(code):
    result = run(lambda request: httpx.Response(code))
    assert result.status == ("UP" if code < 400 else "DOWN")
    assert result.http_status_code == code
    assert result.response_time_ms >= 0
    assert result.error_type is None


@pytest.mark.parametrize("url", [
    "http://localhost", "http://LOCALHOST./", "http://127.0.0.1", "http://127.50.1.2",
    "http://[::1]", "http://10.1.2.3", "http://172.16.0.1", "http://172.31.255.254",
    "http://192.168.1.1", "http://169.254.169.254", "http://[fe80::1]", "http://[fc00::1]",
    "http://0.0.0.0", "http://[::]", "http://224.0.0.1", "http://[ff02::1]",
    "http://240.1.1.1", "http://100.64.0.1", "http://192.0.2.1", "http://[2001:db8::1]",
    "http://[::ffff:127.0.0.1]", "http://[64:ff9b::7f00:1]", "http://[2002:7f00:1::]",
])
def test_blocked_literals(url):
    handler = AsyncMock()
    result = run(handler, url)
    assert result.error_type == "ssrf_blocked"
    handler.assert_not_called()


@pytest.mark.parametrize("addresses", [["10.0.0.1"], ["93.184.216.34", "::1"], ["::ffff:10.0.0.1"]])
def test_dns_all_addresses_checked(addresses):
    handler = AsyncMock()
    result = run(handler, resolver=AsyncMock(return_value=addresses))
    assert result.error_type == "ssrf_blocked"
    handler.assert_not_called()


@pytest.mark.parametrize("url", ["https://user:secret@example.com", "http://user@example.com",
                                      "file:///tmp/test", "http://[fe80::1%25eth0]", "http://"])
def test_invalid_destination(url):
    handler = AsyncMock()
    assert run(handler, url).error_type == "invalid_destination"
    handler.assert_not_called()


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_pinned_ip_host_sni_port_and_fragment(scheme):
    def handler(request):
        assert request.url.host == "93.184.216.34"
        assert request.url.port == 8443
        assert request.url.fragment == ""
        assert request.headers["host"] == "example.com:8443"
        assert request.extensions["sni_hostname"] == "example.com"
        assert request.method == "GET"
        return httpx.Response(200)
    assert run(handler, f"{scheme}://example.com:8443/a#fragment").status == "UP"


def test_redirect_to_private_blocked():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
    assert run(handler).error_type == "ssrf_blocked"
    assert len(calls) == 1


def test_redirect_resolves_each_hop_and_pins_ipv6():
    resolver = AsyncMock(side_effect=[["93.184.216.34"], ["2606:4700:4700::1111"]])
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(301, headers={"location": "/next"})
        assert request.url.host == "2606:4700:4700::1111"
        assert request.url.path == "/next"
        return httpx.Response(204)
    assert run(handler, resolver=resolver).status == "UP"
    assert resolver.await_count == 2


def test_redirect_limit():
    handler = AsyncMock(return_value=httpx.Response(302, headers={"location": "/again"}))
    assert run(handler, redirects=2).error_type == "redirect_limit"
    assert handler.await_count == 3


@pytest.mark.parametrize("exception,kind", [
    (httpx.ReadTimeout("secret"), "timeout"), (httpx.ConnectError("secret"), "connection_error"),
    (httpx.RemoteProtocolError("secret"), "network_error"),
    (socket.gaierror("secret"), "dns_error"), (ssl.SSLError("secret"), "tls_error"),
    (RuntimeError("secret"), "unexpected_error"),
])
def test_errors_sanitized(exception, kind, caplog):
    def handler(request):
        raise exception
    result = run(handler)
    assert result.status == "DOWN" and result.error_type == kind
    assert "secret" not in result.error_message and "secret" not in caplog.text
    assert result.http_status_code is None and result.response_time_ms >= 0


@pytest.mark.parametrize("cause,kind", [(ssl.SSLCertVerificationError("secret"), "tls_error"),
    (ConnectionRefusedError(), "connection_refused"), (socket.gaierror(), "dns_error")])
def test_wrapped_connect_errors(cause, kind):
    def handler(request):
        raise httpx.ConnectError("hidden") from cause
    assert run(handler).error_type == kind


def test_total_deadline_includes_dns():
    async def slow_dns(host, port):
        await asyncio.Event().wait()
    handler = AsyncMock()
    assert run(handler, timeout=0.01, resolver=slow_dns).error_type == "timeout"
    handler.assert_not_called()


def test_body_not_consumed():
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("Body must not be consumed")
            yield b""
    assert run(lambda request: httpx.Response(200, stream=Body())).status == "UP"


def test_client_does_not_forward_cookies():
    async def check():
        async with create_client(2) as client:
            request = client.build_request("GET", "https://93.184.216.34", headers={"cookie": "sensitive"})
            for hook in client.event_hooks["request"]:
                await hook(request)
            assert "cookie" not in request.headers
            assert not client.follow_redirects
    asyncio.run(check())


def test_real_resolver_failure(monkeypatch):
    async def check():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(side_effect=socket.gaierror()))
        with pytest.raises(DestinationError, match="DNS resolution failed"):
            await destination(httpx.URL("https://example.com"))
    asyncio.run(check())


def test_real_transport_pins_connection_preserves_tls_and_host(monkeypatch):
    """Exercise httpx/httpcore down to the socket boundary, without network access."""
    connections, tls_names, sent = [], [], []
    class Stream:
        async def read(self, max_bytes, timeout=None):
            return b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nSet-Cookie: secret=value; Path=/\r\n\r\n"
        async def write(self, buffer, timeout=None):
            sent.append(buffer)
        async def aclose(self):
            pass
        def get_extra_info(self, info):
            return None
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert ssl_context.check_hostname is True
            tls_names.append(server_hostname)
            return self
    async def connect(self, host, port, **kwargs):
        connections.append((host, port))
        return Stream()
    monkeypatch.setattr('httpcore._backends.auto.AutoBackend.connect_tcp', connect)
    async def check():
        async with create_client(1) as client:
            for host in ('first.example', 'second.example'):
                result = await check_http(client, 'https://' + host, 2, resolver=public_dns)
                assert result.status == 'UP'
    asyncio.run(check())
    assert connections == [('93.184.216.34', 443), ('93.184.216.34', 443)]
    assert tls_names == ['first.example', 'second.example']
    wire = b''.join(sent)
    assert b'Host: first.example' in wire and b'Host: second.example' in wire
    assert b'Cookie:' not in wire


def test_deadline_covers_redirect_chain():
    async def handler(request):
        await asyncio.sleep(0.02)
        return httpx.Response(302, headers={'location': '/next'})
    assert run(handler, timeout=0.03).error_type == 'timeout'
