import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from veriditi_common.settings import BaseServiceSettings, ServiceSettings


def _settings(**overrides: object) -> ServiceSettings:
    values: dict[str, object] = {
        "service_name": "auth",
        "db_host": "mysql",
        "db_port": 3306,
        "db_user": "auth_svc",
        "db_password": "a",
        "db_migrator_user": "migrator",
        "db_migrator_password": "m",
    }
    values.update(overrides)
    return ServiceSettings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def test_runtime_and_migration_urls_use_their_own_credentials() -> None:
    settings = _settings()

    assert (
        settings.database_url == "mysql+aiomysql://auth_svc:a@mysql:3306/veriditi?charset=utf8mb4"
    )
    assert settings.migration_database_url == (
        "mysql+aiomysql://migrator:m@mysql:3306/veriditi?charset=utf8mb4"
    )


def test_db_name_defaults_to_central_and_can_point_to_logs() -> None:
    assert _settings().db_name == "veriditi"
    logs_url = _settings(db_name="veriditi_logs").database_url
    assert logs_url.endswith("/veriditi_logs?charset=utf8mb4")


def test_database_url_requires_runtime_password() -> None:
    with pytest.raises(RuntimeError, match="DB_PASSWORD"):
        _ = _settings(db_password=None).database_url


@pytest.mark.parametrize("missing", ["db_migrator_user", "db_migrator_password"])
def test_migration_url_requires_migrator_credentials(missing: str) -> None:
    with pytest.raises(RuntimeError, match="DB_MIGRATOR"):
        _ = _settings(**{missing: None}).migration_database_url


def test_passwords_are_not_leaked_in_repr() -> None:
    rendered = repr(_settings(db_password="s3nh4-runtime", db_migrator_password="s3nh4-ddl"))
    assert "s3nh4" not in rendered


def test_base_settings_work_without_database_variables() -> None:
    settings = BaseServiceSettings(_env_file=None, service_name="gateway")  # type: ignore[call-arg]

    assert settings.service_name == "gateway"
    assert settings.debug is False
    assert issubclass(ServiceSettings, BaseServiceSettings)


@pytest.mark.parametrize("password", ["p@ss", "a%41b", "x/y:z", "@%/:"])
def test_special_characters_in_password_survive_the_url(password: str) -> None:
    settings = _settings(db_password=password, db_migrator_password=password)

    for raw in (settings.database_url, settings.migration_database_url):
        url = make_url(raw)
        assert url.password == password
        assert (url.host, url.port, url.database) == ("mysql", 3306, "veriditi")


TOKEN = "test-internal-token-0123456789"


def _base(**overrides: object) -> BaseServiceSettings:
    return BaseServiceSettings(_env_file=None, service_name="svc", **overrides)  # type: ignore[call-arg, arg-type]


def test_internal_token_is_optional_but_required_on_access() -> None:
    settings = _base()

    assert settings.internal_api_token is None
    with pytest.raises(RuntimeError, match="INTERNAL_API_TOKEN"):
        _ = settings.internal_token


def test_empty_internal_token_counts_as_missing() -> None:
    assert _base(internal_api_token="").internal_api_token is None


def test_internal_token_requires_16_characters() -> None:
    with pytest.raises(ValidationError, match="16"):
        _base(internal_api_token="a" * 15)

    assert _base(internal_api_token=TOKEN).internal_token.get_secret_value() == TOKEN


def test_internal_token_is_not_leaked_in_repr() -> None:
    assert TOKEN not in repr(_base(internal_api_token=TOKEN))


def test_log_level_defaults_to_info_and_is_case_insensitive() -> None:
    assert _base().log_level == "INFO"
    assert _base(log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        _base(log_level="verbose")


def test_service_settings_without_token_stay_valid() -> None:
    assert _settings().internal_api_token is None
