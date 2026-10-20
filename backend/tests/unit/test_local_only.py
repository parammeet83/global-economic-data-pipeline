"""Local-only trigger guard as pure functions (D-39)."""

import pytest

from src.api.local_only import (
    CLIENT_NOT_LOCAL,
    HOST_NOT_LOCAL,
    UNTRUSTED_PROXY,
    host_name,
    local_request_error,
    normalize_ip,
    resolve_client,
)

VITE = ["127.0.0.1", "::1"]


@pytest.mark.parametrize(
    ("header", "expected"),
    [("localhost:5173", "localhost"), ("127.0.0.1", "127.0.0.1"), ("[::1]:8000", "::1"), ("LOCALHOST", "localhost"), ("192.168.1.5:5173", "192.168.1.5")],
)
def test_host_name(header, expected):
    assert host_name(header) == expected


def test_normalize_ip():
    assert normalize_ip("::ffff:127.0.0.1") == "127.0.0.1"
    assert normalize_ip(" [::1] ") == "::1"
    assert normalize_ip("testclient") is None


def test_without_forwarding_headers_the_peer_is_the_client():
    assert resolve_client("127.0.0.1", {}, []) == "127.0.0.1"
    assert resolve_client("203.0.113.7", {}, VITE) == "203.0.113.7"


def test_forwarded_client_is_the_rightmost_untrusted_hop():
    headers = {"x-forwarded-for": "127.0.0.1, 192.168.1.20, 127.0.0.1"}
    assert resolve_client("127.0.0.1", headers, VITE) == "192.168.1.20"


def test_forwarding_headers_are_ignored_unless_the_peer_is_trusted():
    assert resolve_client("127.0.0.1", {"x-forwarded-for": "127.0.0.1"}, []) is None
    assert resolve_client("203.0.113.7", {"x-forwarded-for": "127.0.0.1"}, VITE) is None


def test_unparseable_or_unsupported_forwarding_fails_closed():
    assert resolve_client("127.0.0.1", {"x-forwarded-for": "unknown"}, VITE) is None
    assert resolve_client("127.0.0.1", {"forwarded": "for=127.0.0.1"}, VITE) is None


@pytest.mark.parametrize(
    ("peer", "headers", "trusted", "expected"),
    [
        ("127.0.0.1", {"host": "127.0.0.1:8000"}, [], None),
        ("::1", {"host": "[::1]:8000"}, [], None),
        ("127.0.0.1", {"host": "localhost:5173", "x-forwarded-for": "127.0.0.1"}, VITE, None),
        ("127.0.0.1", {"host": "localhost:5173", "x-forwarded-for": "192.168.1.20"}, VITE, CLIENT_NOT_LOCAL),
        ("127.0.0.1", {"host": "localhost:5173", "x-forwarded-for": "127.0.0.1"}, [], UNTRUSTED_PROXY),
        ("127.0.0.1", {"host": "192.168.1.5:5173"}, [], HOST_NOT_LOCAL),
        ("203.0.113.7", {"host": "127.0.0.1:8000"}, [], CLIENT_NOT_LOCAL),
        ("203.0.113.7", {"host": "127.0.0.1:8000", "x-forwarded-for": "127.0.0.1"}, VITE, CLIENT_NOT_LOCAL),
        (None, {"host": "127.0.0.1:8000"}, [], CLIENT_NOT_LOCAL),
        ("testclient", {"host": "127.0.0.1:8000"}, [], CLIENT_NOT_LOCAL),
    ],
)
def test_local_request_error(peer, headers, trusted, expected):
    assert local_request_error(peer, headers, trusted) == expected
