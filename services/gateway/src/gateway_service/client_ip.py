"""IP real do cliente: o X-Forwarded-For só vale quando vem de um proxy confiável"""

from collections.abc import Iterable, Sequence
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from typing import Final

IPAddress = IPv4Address | IPv6Address

# Teto de itens lidos da direita: um XFF gigante não vira laço longo
MAX_FORWARDED_ITEMS: Final = 20


class TrustedProxies:
    def __init__(self, networks: Iterable[IPv4Network | IPv6Network]) -> None:
        self._networks = tuple(networks)

    def __contains__(self, ip: IPAddress) -> bool:
        return any(ip.version == net.version and ip in net for net in self._networks)


def _port_ok(port: str) -> bool:
    return port.isascii() and port.isdigit()


def parse_ip(raw: str) -> IPAddress | None:
    """IPv4, IPv6, [v6]:porta e v4:porta; IPv4-mapeado vira IPv4 e scope id é recusado"""
    item = raw.strip()
    if item.startswith("["):
        host, sep, rest = item[1:].partition("]")
        if not sep or (rest and not (rest.startswith(":") and _port_ok(rest[1:]))):
            return None
    elif item.count(":") == 1:
        host, _, port = item.partition(":")
        if not _port_ok(port):
            return None
    else:
        host = item
    if "%" in host:
        return None
    try:
        ip = ip_address(host)
    except ValueError:
        return None
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def resolve_client_ip(
    peer: str | None, forwarded_for: Sequence[str], trusted: TrustedProxies
) -> str | None:
    """Da direita para a esquerda enquanto o salto é confiável; item inválido para no último"""
    real = parse_ip(peer) if peer else None
    if real is None:
        return None
    items = [part for line in forwarded_for for part in line.split(",")][-MAX_FORWARDED_ITEMS:]
    for raw in reversed(items):
        if real not in trusted:
            break
        candidate = parse_ip(raw)
        if candidate is None:
            break
        real = candidate
    return str(real)
