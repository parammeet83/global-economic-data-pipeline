"""Local-only check for the unauthenticated manual pipeline trigger (D-23, D-38, D-39).

A request is accepted only when all of these hold:

1. The ``Host`` header names a loopback host (``localhost``, ``127.0.0.1`` or ``[::1]``).
   A browser on another machine reaching an exposed dev server sends that server's LAN
   address instead.
2. The originating client is a loopback address:
   * without forwarding headers, the client is the TCP peer;
   * with forwarding headers, they are used **only** if the peer is listed in
     ``TRUSTED_PROXY_IPS``. The client is then the right-most ``X-Forwarded-For`` entry
     that is not itself a trusted proxy, so a value forged by the client (which proxies
     append to, never replace) cannot win;
   * forwarding headers from a peer that is not a configured proxy fail closed: the
     request's origin cannot be verified.

This is a guard for a local demo, not authentication. Anything exposed beyond this
machine needs real authentication and rate limiting first.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Collection, Mapping

LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})
FORWARDING_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")

HOST_NOT_LOCAL = "Manual pipeline runs are only accepted at a loopback address (localhost or 127.0.0.1)."
CLIENT_NOT_LOCAL = "Manual pipeline runs are only accepted from this machine."
UNTRUSTED_PROXY = (
    "This request came through a proxy that is not listed in TRUSTED_PROXY_IPS, so its origin cannot be "
    "verified. For the local Vite dev server, set TRUSTED_PROXY_IPS=127.0.0.1,::1 in backend/.env."
)


def normalize_ip(value: str) -> str | None:
    """Canonical IP string (IPv4-mapped IPv6 becomes IPv4), or None if not an IP address."""
    try:
        address = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def is_loopback(value: str | None) -> bool:
    normalized = normalize_ip(value) if value else None
    return normalized is not None and ipaddress.ip_address(normalized).is_loopback


def host_name(host_header: str) -> str:
    """Hostname part of a Host header: ``localhost:5173`` -> ``localhost``, ``[::1]:8000`` -> ``::1``."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1 : host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def resolve_client(peer: str | None, headers: Mapping[str, str], trusted_proxies: Collection[str]) -> str | None:
    """Originating client address, or None when it cannot be determined safely."""
    trusted = {ip for ip in (normalize_ip(p) for p in trusted_proxies) if ip}
    peer_ip = normalize_ip(peer) if peer else None
    if not any(name in headers for name in FORWARDING_HEADERS):
        return peer_ip
    if peer_ip is None or peer_ip not in trusted:
        return None  # forwarding headers from an unconfigured hop: fail closed
    hops = [normalize_ip(h) for h in headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if not hops or any(h is None for h in hops):
        return None  # only Forwarded/X-Real-IP, or an unparseable entry: not supported, fail closed
    for hop in reversed(hops):
        if hop not in trusted:
            return hop
    return hops[0]


def local_request_error(
    peer: str | None, headers: Mapping[str, str], trusted_proxies: Collection[str]
) -> str | None:
    """Return a user-facing reason to refuse the request, or None if it is local."""
    if host_name(headers.get("host", "")) not in LOOPBACK_HOSTNAMES:
        return HOST_NOT_LOCAL
    peer_ip = normalize_ip(peer) if peer else None
    has_forwarding = any(name in headers for name in FORWARDING_HEADERS)
    trusted = {ip for ip in (normalize_ip(p) for p in trusted_proxies) if ip}
    if has_forwarding and peer_ip is not None and peer_ip not in trusted and is_loopback(peer_ip):
        return UNTRUSTED_PROXY
    client = resolve_client(peer, headers, trusted_proxies)
    if not is_loopback(client):
        return CLIENT_NOT_LOCAL
    return None
