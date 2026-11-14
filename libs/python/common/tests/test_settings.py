import pytest
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
