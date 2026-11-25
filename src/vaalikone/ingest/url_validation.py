"""SSRF protection for URL-fetching connectors.

Validates that a URL is a public http(s) URL before fetching it:
blocks private/loopback/link-local/reserved IPs (including DNS names
that resolve to them) and non-http(s) schemes.
"""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch (SSRF risk)."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str, resolve_dns: bool = True) -> str:
    """Validate that ``url`` is a public http(s) URL. Returns the normalized URL.

    Raises UnsafeURLError for anything that could reach internal services.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Scheme {parsed.scheme!r} not allowed (only http/https)")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no hostname")

    hostname = parsed.hostname.lower()
    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".localhost"):
        raise UnsafeURLError("localhost is not allowed")

    # Literal IP?
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None  # not a literal IP, resolve DNS below
    if ip is not None:
        if _is_blocked_ip(ip):
            raise UnsafeURLError(f"IP {ip} is not public")
        return url

    if resolve_dns:
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as e:
            raise UnsafeURLError(f"Cannot resolve hostname {hostname!r}: {e}") from e
        if not infos:
            raise UnsafeURLError(f"Cannot resolve hostname {hostname!r}")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if _is_blocked_ip(ip):
                raise UnsafeURLError(f"Hostname {hostname!r} resolves to non-public IP {ip}")

    return url
