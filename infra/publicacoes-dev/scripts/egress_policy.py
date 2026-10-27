#!/usr/bin/env python3
"""Contrato mínimo de validação de destino para conectores HTTP de DEV."""

from __future__ import annotations

import argparse
import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit


class EgressDenied(ValueError):
    """Destino não atende ao contrato de egress."""


@dataclass(frozen=True)
class ValidatedDestination:
    """Destino já validado para uma única tentativa de conexão."""

    hostname: str
    port: int
    addresses: tuple[str, ...]


Resolver = Callable[[str, int], Iterable[str]]


def system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve todos os endereços retornados pelo sistema."""

    answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(sorted({answer[4][0] for answer in answers}))


def validate_destination(
    url: str,
    *,
    allowed_hosts: set[str],
    resolver: Resolver = system_resolver,
) -> ValidatedDestination:
    """Valida URL, allowlist e todos os IPs antes de uma conexão.

    A função deve ser chamada novamente para cada redirecionamento. O cliente
    HTTP consumidor deve conectar apenas a um dos endereços retornados e manter
    o hostname original para TLS/SNI, evitando uma segunda resolução implícita.
    """

    if len(url) > 2048:
        raise EgressDenied("url_too_long")
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise EgressDenied("https_required")
    if not parsed.hostname:
        raise EgressDenied("hostname_required")
    if parsed.username is not None or parsed.password is not None:
        raise EgressDenied("userinfo_forbidden")
    if parsed.fragment:
        raise EgressDenied("fragment_forbidden")

    hostname = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    normalized_allowlist = {
        host.rstrip(".").lower().encode("idna").decode("ascii")
        for host in allowed_hosts
    }
    if hostname not in normalized_allowlist:
        raise EgressDenied("host_not_allowed")

    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise EgressDenied("invalid_port") from exc
    if port != 443:
        raise EgressDenied("port_not_allowed")

    try:
        addresses = tuple(resolver(hostname, port))
    except OSError as exc:
        raise EgressDenied("dns_failure") from exc
    if not addresses:
        raise EgressDenied("dns_empty")

    normalized_addresses: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise EgressDenied("invalid_dns_answer") from exc
        if not address.is_global:
            raise EgressDenied("non_global_address")
        normalized_addresses.append(address.compressed)

    return ValidatedDestination(
        hostname=hostname,
        port=port,
        addresses=tuple(sorted(set(normalized_addresses))),
    )


def _run_self_test() -> None:
    allowed = {"api.example.test"}

    def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946")

    destination = validate_destination(
        "https://api.example.test/resource",
        allowed_hosts=allowed,
        resolver=public_resolver,
    )
    assert destination.port == 443
    assert len(destination.addresses) == 2

    denied_cases = (
        ("http://api.example.test", public_resolver),
        ("https://user:secret@api.example.test", public_resolver),
        ("https://unlisted.example.test", public_resolver),
        ("https://api.example.test:8443", public_resolver),
        ("https://api.example.test/#secret", public_resolver),
        ("https://api.example.test", lambda _host, _port: ("127.0.0.1",)),
        ("https://api.example.test", lambda _host, _port: ("169.254.169.254",)),
        ("https://api.example.test", lambda _host, _port: ("10.0.0.1",)),
        ("https://api.example.test", lambda _host, _port: ("::1",)),
    )
    for url, resolver in denied_cases:
        try:
            validate_destination(url, allowed_hosts=allowed, resolver=resolver)
        except EgressDenied:
            continue
        raise AssertionError(f"destino deveria ser negado: {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("use --self-test; consumidores devem importar validate_destination")
    _run_self_test()
    print("Contrato de egress/SSRF aprovado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
