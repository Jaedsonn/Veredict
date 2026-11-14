from ipaddress import ip_address, ip_network

import pytest

from gateway_service.client_ip import (
    MAX_FORWARDED_ITEMS,
    TrustedProxies,
    parse_ip,
    resolve_client_ip,
)

TRUSTED = TrustedProxies([ip_network("10.0.0.0/8"), ip_network("fd00::/8")])
PROXY = "10.0.0.5"


def test_untrusted_peer_ignores_forwarded_for() -> None:
    assert resolve_client_ip("203.0.113.7", ["198.51.100.9"], TRUSTED) == "203.0.113.7"


@pytest.mark.parametrize(
    ("xff", "expected"),
    [
        (["198.51.100.9"], "198.51.100.9"),
        (["1.1.1.1, 10.0.0.2"], "1.1.1.1"),
        (["6.6.6.6, 1.1.1.1"], "1.1.1.1"),
        (["6.6.6.6", "1.1.1.1, 10.0.0.9"], "1.1.1.1"),
        (["2.2.2.2", "6.6.6.6"], "6.6.6.6"),
        ([], PROXY),
    ],
)
def test_trusted_peer_walks_from_the_right(xff: list[str], expected: str) -> None:
    assert resolve_client_ip(PROXY, xff, TRUSTED) == expected


def test_multiple_lines_are_joined_in_order() -> None:
    assert resolve_client_ip(PROXY, ["5.5.5.5", "10.0.0.1", "10.0.0.2"], TRUSTED) == "5.5.5.5"


@pytest.mark.parametrize("bad", ["nao-ip", "", "fe80::1%eth0", "1.2.3.4:porta", "[::1"])
def test_invalid_item_stops_at_last_valid(bad: str) -> None:
    assert resolve_client_ip(PROXY, [f"6.6.6.6, {bad}, 10.0.0.3"], TRUSTED) == "10.0.0.3"


def test_all_trusted_returns_leftmost() -> None:
    assert resolve_client_ip(PROXY, ["10.1.1.1, 10.2.2.2"], TRUSTED) == "10.1.1.1"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2001:db8::1", "2001:db8::1"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("[2001:db8::1]", "2001:db8::1"),
        ("1.2.3.4:5678", "1.2.3.4"),
        ("::ffff:1.2.3.4", "1.2.3.4"),
        (" 1.2.3.4 ", "1.2.3.4"),
    ],
)
def test_parse_formats(raw: str, expected: str) -> None:
    assert str(parse_ip(raw)) == expected


@pytest.mark.parametrize(
    "raw", ["fe80::1%eth0", "[fe80::1%eth0]:80", "[::1]x", "[::1]:", "1.2.3.4:", "1.2.3.4:²", "x"]
)
def test_parse_rejects(raw: str) -> None:
    assert parse_ip(raw) is None


def test_ipv6_through_trusted_ipv6_proxy() -> None:
    assert resolve_client_ip("fd00::1", ["[2001:db8::7]:1234"], TRUSTED) == "2001:db8::7"


def test_ipv4_mapped_peer_is_trusted_as_ipv4() -> None:
    assert resolve_client_ip("::ffff:10.0.0.5", ["198.51.100.9"], TRUSTED) == "198.51.100.9"


def test_only_last_items_are_read() -> None:
    spoofed = ", ".join(["10.9.9.9"] * (MAX_FORWARDED_ITEMS + 5))
    xff = [f"7.7.7.7, {spoofed}"]

    assert resolve_client_ip(PROXY, xff, TRUSTED) == "10.9.9.9"


@pytest.mark.parametrize("peer", [None, "", "testclient"])
def test_peer_without_ip_is_none(peer: str | None) -> None:
    assert resolve_client_ip(peer, ["1.1.1.1"], TRUSTED) is None


def test_empty_trusted_never_trusts() -> None:
    assert resolve_client_ip("10.0.0.5", ["1.1.1.1"], TrustedProxies([])) == "10.0.0.5"


def test_membership_respects_ip_version() -> None:
    assert ip_address("10.0.0.1") in TRUSTED
    assert ip_address("::1") not in TRUSTED
