from ipaddress import ip_network
from typing import Any

import pytest
from pydantic import ValidationError

from gateway_service.config import Settings
from gateway_service.domain import Upstream


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_defaults() -> None:
    settings = _settings()

    assert settings.trusted_proxies == ()
    assert settings.jwt_public_key is None
    assert settings.jwt_issuer == "veriditi-auth"
    assert settings.jwt_audience == "veriditi"
    assert settings.jwt_leeway_seconds == 10
    assert settings.upstream_timeout_seconds == 5.0
    assert settings.max_body_bytes == 1_048_576
    assert settings.web_origin == "http://localhost:3000"


def test_trusted_proxies_csv_with_spaces_single_ip_and_ipv6() -> None:
    settings = _settings(trusted_proxies=" 10.0.0.0/8 , 192.168.1.10,2001:db8::/32,::1,")

    assert settings.trusted_proxies == (
        ip_network("10.0.0.0/8"),
        ip_network("192.168.1.10/32"),
        ip_network("2001:db8::/32"),
        ip_network("::1/128"),
    )


def test_trusted_proxies_host_bits_are_accepted() -> None:
    assert _settings(trusted_proxies="10.1.2.3/8").trusted_proxies == (ip_network("10.0.0.0/8"),)


def test_invalid_trusted_proxy_names_the_item() -> None:
    with pytest.raises(ValidationError, match="'10.0.0.300'"):
        _settings(trusted_proxies="10.0.0.0/8,10.0.0.300")


def test_empty_trusted_proxies_is_empty_tuple() -> None:
    assert _settings(trusted_proxies="").trusted_proxies == ()


def test_trusted_proxies_from_environment_is_not_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "172.16.0.0/12,127.0.0.1")

    settings = _settings()

    assert settings.trusted_proxies == (ip_network("172.16.0.0/12"), ip_network("127.0.0.1/32"))


def test_web_url_trailing_slash_is_dropped() -> None:
    settings = _settings(web_url="https://app.veriditi.test:8443/")

    assert settings.web_url == "https://app.veriditi.test:8443"
    assert settings.web_origin == "https://app.veriditi.test:8443"


@pytest.mark.parametrize(
    "url", ["http://web.test/app", "http://web.test?x=1", "web.test", "ftp://x"]
)
def test_web_url_rejects_path_and_non_http(url: str) -> None:
    with pytest.raises(ValidationError, match="WEB_URL"):
        _settings(web_url=url)


@pytest.mark.parametrize("url", ["auth:8000", "localhost:8001", "/auth"])
def test_auth_url_requires_scheme(url: str) -> None:
    with pytest.raises(ValidationError, match="AUTH_URL"):
        _settings(auth_url=url)


def test_upstreams_only_auth_without_trailing_slash() -> None:
    settings = _settings(auth_url="http://auth:8000/")

    assert settings.upstreams == {"auth": Upstream("auth", "http://auth:8000", "autenticação")}
    assert settings.upstream_urls == {"auth": "http://auth:8000"}


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_public_key_is_missing(value: str) -> None:
    settings = _settings(jwt_public_key=value)

    assert settings.jwt_public_key is None
    with pytest.raises(RuntimeError, match="make keys"):
        settings.require_jwt_public_key()


def test_public_key_is_returned_when_present() -> None:
    assert _settings(jwt_public_key="pem").require_jwt_public_key() == "pem"


@pytest.mark.parametrize("value", [0, -1, 60.5])
def test_upstream_timeout_bounds(value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(upstream_timeout_seconds=value)


@pytest.mark.parametrize("value", [-1, 61])
def test_leeway_bounds(value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(jwt_leeway_seconds=value)


@pytest.mark.parametrize("value", [1023, 104_857_601])
def test_max_body_bounds(value: int) -> None:
    with pytest.raises(ValidationError):
        _settings(max_body_bytes=value)
