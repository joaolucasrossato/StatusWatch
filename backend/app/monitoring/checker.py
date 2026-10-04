import asyncio
import ipaddress
import logging
import socket
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)
Resolver = Callable[[str, int], Awaitable[list[str]]]
ERRORS = {
    "timeout": "Check timed out",
    "dns_error": "DNS resolution failed",
    "connection_refused": "Connection refused",
    "connection_error": "Connection failed",
    "tls_error": "TLS verification or handshake failed",
    "network_error": "HTTP protocol or network error",
    "invalid_destination": "Invalid destination",
    "ssrf_blocked": "Blocked destination",
    "redirect_limit": "Redirect limit exceeded",
    "unexpected_error": "Unexpected check failure",
}


@dataclass(frozen=True)
class CheckResult:
    status: Literal["UP", "DOWN"]
    http_status_code: int | None = None
    response_time_ms: int | None = None
    error_type: str | None = None
    error_message: str | None = None


class DestinationError(Exception):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(ERRORS[kind])


async def resolve(host: str, port: int) -> list[str]:
    try:
        records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DestinationError("dns_error") from exc
    return list(dict.fromkeys(record[4][0] for record in records))


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Reject transition mechanisms and zone identifiers conservatively.
        if address.scope_id or address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if address in ipaddress.ip_network("64:ff9b::/96") or address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return address.is_global and not any((address.is_multicast, address.is_reserved,
        address.is_unspecified, address.is_loopback, address.is_link_local, address.is_private))


async def destination(url: httpx.URL, resolver: Resolver = resolve) -> str:
    if (url.scheme not in ("http", "https") or not url.host or url.userinfo
            or b"@" in url.netloc or "%" in url.host or "\\" in url.host):
        raise DestinationError("invalid_destination")
    if url.host.rstrip(".").lower() == "localhost":
        raise DestinationError("ssrf_blocked")
    try:
        ipaddress.ip_address(url.host)
        addresses = [url.host]
    except ValueError:
        addresses = await resolver(url.host, url.port or (443 if url.scheme == "https" else 80))
    if not addresses:
        raise DestinationError("dns_error")
    if not all(public_address(address) for address in addresses):
        raise DestinationError("ssrf_blocked")
    return addresses[0]


async def strip_cookies(request: httpx.Request) -> None:
    request.headers.pop("cookie", None)


def create_client(concurrency: int) -> httpx.AsyncClient:
    # Never reuse an IP-keyed connection across original hosts (TLS/Host isolation).
    return httpx.AsyncClient(
        trust_env=False, follow_redirects=False, event_hooks={"request": [strip_cookies]},
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=0),
    )


def connection_error(exc: BaseException) -> str:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return "tls_error"
        if isinstance(current, socket.gaierror):
            return "dns_error"
        if isinstance(current, ConnectionRefusedError):
            return "connection_refused"
        current = current.__cause__ or current.__context__
    return "connection_error"


async def check_http(client: httpx.AsyncClient, url: str, timeout_seconds: float,
                     max_redirects: int = 5, resolver: Resolver = resolve) -> CheckResult:
    started = time.monotonic()
    def elapsed() -> int:
        return max(0, round((time.monotonic() - started) * 1000))

    try:
        # One deadline covers DNS, connections and every redirect, not just socket reads.
        async with asyncio.timeout(timeout_seconds):
            target = httpx.URL(url)
            for hop in range(max_redirects + 1):
                address = await destination(target, resolver)
                pinned = target.copy_with(host=address, fragment=None)
                async with client.stream(
                    "GET", pinned, headers={"Host": target.netloc.decode("ascii")},
                    extensions={"sni_hostname": target.host}, timeout=timeout_seconds,
                    follow_redirects=False,
                ) as response:
                    code = response.status_code
                    if code in (301, 302, 303, 307, 308) and "location" in response.headers:
                        if hop == max_redirects:
                            raise DestinationError("redirect_limit")
                        target = target.join(response.headers["location"])
                        continue
                    return CheckResult("UP" if 200 <= code <= 399 else "DOWN", code, elapsed())
    except (TimeoutError, httpx.TimeoutException):
        kind = "timeout"
    except DestinationError as exc:
        kind = exc.kind
    except (httpx.InvalidURL, ValueError):
        kind = "invalid_destination"
    except httpx.ConnectError as exc:
        kind = connection_error(exc)
    except ssl.SSLError:
        kind = "tls_error"
    except socket.gaierror:
        kind = "dns_error"
    except (httpx.HTTPError, OSError):
        kind = "network_error"
    except Exception as exc:
        # Exception text may include credentials, URLs or response data.
        logger.error("Unexpected checker failure class=%s", type(exc).__name__)
        kind = "unexpected_error"
    return CheckResult("DOWN", response_time_ms=elapsed(), error_type=kind, error_message=ERRORS[kind])
