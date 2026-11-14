import pytest
from pydantic import ValidationError

from notification_service.config import Settings

SECRET = "s3nh4-smtp-super-secreta"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"db_user": "test"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_smtp_defaults_point_to_local_mailpit() -> None:
    settings = _settings()

    assert str(settings.smtp_from) == "Veriditi <no-reply@veriditi.app>"
    assert settings.smtp_from_domain == "veriditi.app"
    assert (settings.smtp_host, settings.smtp_port) == ("localhost", 1025)
    assert settings.smtp_starttls is False
    assert settings.smtp_use_tls is False
    assert settings.smtp_timeout_seconds == 10.0
    assert (settings.smtp_user, settings.smtp_password) == (None, None)
    assert settings.web_url == "http://localhost:3000"


def test_values_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in {
        "SMTP_HOST": "smtp.exemplo.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "apikey",
        "SMTP_PASSWORD": SECRET,
        "SMTP_FROM": "Equipe <contato@exemplo.com>",
        "SMTP_STARTTLS": "true",
        "WEB_URL": "https://veriditi.app/",
    }.items():
        monkeypatch.setenv(key, value)

    settings = _settings()

    assert (settings.smtp_host, settings.smtp_port) == ("smtp.exemplo.com", 587)
    assert settings.smtp_user == "apikey"
    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == SECRET
    assert str(settings.smtp_from) == "Equipe <contato@exemplo.com>"
    assert settings.smtp_from_domain == "exemplo.com"
    assert settings.smtp_starttls is True
    assert settings.web_url == "https://veriditi.app"


def test_empty_smtp_credentials_are_missing() -> None:
    settings = _settings(smtp_user="", smtp_password="")

    assert (settings.smtp_user, settings.smtp_password) == (None, None)


def test_user_without_password_is_rejected() -> None:
    with pytest.raises(ValidationError, match="SMTP_USER exige SMTP_PASSWORD"):
        _settings(smtp_user="apikey")


@pytest.mark.parametrize(
    "value",
    ["Veriditi <no-reply@veriditi.app>\r\nBcc: x@evil.com", "Veriditi", ""],
    ids=["crlf", "no-address", "empty"],
)
def test_invalid_smtp_from_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        _settings(smtp_from=value)


@pytest.mark.parametrize("value", ["ftp://x", "localhost:3000", "/entrar", "http://"])
def test_web_url_must_be_absolute_http(value: str) -> None:
    with pytest.raises(ValidationError, match="WEB_URL"):
        _settings(web_url=value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("http://x/", "http://x"), ("https://veriditi.app//", "https://veriditi.app")],
)
def test_web_url_loses_trailing_slash(value: str, expected: str) -> None:
    assert _settings(web_url=value).web_url == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("smtp_port", 0),
        ("smtp_port", 65536),
        ("smtp_timeout_seconds", 0),
        ("smtp_timeout_seconds", 61),
    ],
)
def test_out_of_range_numbers_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_password_never_shows_in_repr_or_dump() -> None:
    settings = _settings(smtp_user="apikey", smtp_password=SECRET)

    assert SECRET not in repr(settings)
    assert SECRET not in settings.model_dump_json()


def test_implicit_tls_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    monkeypatch.setenv("SMTP_PORT", "465")

    settings = _settings()

    assert (settings.smtp_use_tls, settings.smtp_starttls, settings.smtp_port) == (True, False, 465)


def test_implicit_tls_and_starttls_are_exclusive() -> None:
    with pytest.raises(ValidationError, match="excludentes"):
        _settings(smtp_use_tls=True, smtp_starttls=True)


@pytest.mark.parametrize("host", ["smtp.exemplo.com", "10.0.0.5"])
def test_credentials_over_plaintext_to_remote_host_are_rejected(host: str) -> None:
    with pytest.raises(ValidationError, match="SMTP_USE_TLS ou SMTP_STARTTLS"):
        _settings(smtp_host=host, smtp_user="apikey", smtp_password=SECRET)


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "::1", "mailpit"])
def test_credentials_over_plaintext_are_allowed_on_local_smtp(host: str) -> None:
    settings = _settings(smtp_host=host, smtp_user="apikey", smtp_password=SECRET)

    assert settings.smtp_user == "apikey"


@pytest.mark.parametrize("tls", [{"smtp_use_tls": True}, {"smtp_starttls": True}])
def test_credentials_with_tls_are_allowed_on_remote_host(tls: dict[str, bool]) -> None:
    settings = _settings(
        smtp_host="smtp.exemplo.com", smtp_user="apikey", smtp_password=SECRET, **tls
    )

    assert settings.smtp_user == "apikey"


def test_remote_host_without_credentials_needs_no_tls() -> None:
    assert _settings(smtp_host="smtp.exemplo.com").smtp_starttls is False
