import io
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pymysql.err
import pytest
import sqlalchemy as sa
from pydantic import BaseModel, ValidationError
from sqlalchemy import exc as sa_exc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from structlog.contextvars import bound_contextvars

from veriditi_common.logging import (
    REDACTED,
    configure_logging,
    get_logger,
    is_sensitive_key,
    mask_email,
    redact,
    redact_sensitive,
)

JsonLogs = Callable[[], list[dict[str, Any]]]


def test_line_is_json_with_standard_keys(json_logs: JsonLogs) -> None:
    get_logger("app.test").info("x", a=1)

    [line] = json_logs()
    assert line["event"] == "x"
    assert line["a"] == 1
    assert line["level"] == "info"
    assert line["service"] == "svc-test"
    assert line["logger"] == "app.test"
    assert line["timestamp"].endswith("Z")
    assert datetime.fromisoformat(line["timestamp"]).tzinfo is not None


def test_get_logger_without_name_uses_caller_module(json_logs: JsonLogs) -> None:
    get_logger().info("x")

    assert json_logs()[0]["logger"] == __name__


def test_request_id_from_contextvars(json_logs: JsonLogs) -> None:
    with bound_contextvars(request_id="3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"):
        get_logger("t").info("x")

    assert json_logs()[0]["request_id"] == "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55"


def test_stdlib_loggers_are_rendered_as_json(json_logs: JsonLogs) -> None:
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 7)

    [line] = json_logs()
    assert line["event"] == "Started server process [7]"
    assert line["service"] == "svc-test"
    assert line["logger"] == "uvicorn.error"
    assert line["level"] == "info"


def test_uvicorn_access_and_httpx_info_are_silenced(json_logs: JsonLogs) -> None:
    logging.getLogger("uvicorn.access").info("GET / 200")
    logging.getLogger("httpx").info("HTTP Request: GET http://x")
    logging.getLogger("httpcore").info("connect")
    logging.getLogger("aiosqlite").debug("executing INSERT ('segredo@sql.test',)")

    assert json_logs() == []


def test_configure_twice_emits_one_line_per_log(reset_logging: None) -> None:
    stream = io.StringIO()
    configure_logging("svc", stream=stream)
    configure_logging("svc", stream=stream)

    get_logger("t").info("x")

    assert len(stream.getvalue().splitlines()) == 1


def test_level_is_respected(reset_logging: None) -> None:
    stream = io.StringIO()
    configure_logging("svc", level="WARNING", stream=stream)

    get_logger("t").info("descartado")
    logging.getLogger("uvicorn.error").info("descartado")
    get_logger("t").warning("mantido")

    assert [json.loads(raw)["event"] for raw in stream.getvalue().splitlines()] == ["mantido"]


def test_sensitive_keys_are_redacted(json_logs: JsonLogs) -> None:
    get_logger("t").info(
        "x",
        password="p",
        **{"X-Internal-Token": "tok"},
        Authorization="Bearer abc",
        metadata={"token": "t", "inner": [{"refresh_token": "r"}], "ok": 1},
        status_code=401,
    )

    [line] = json_logs()
    assert line["password"] == REDACTED
    assert line["X-Internal-Token"] == REDACTED
    assert line["Authorization"] == REDACTED
    assert line["metadata"] == {"token": REDACTED, "inner": [{"refresh_token": REDACTED}], "ok": 1}
    assert line["status_code"] == 401


def test_redact_sensitive_compares_case_and_separator_insensitively() -> None:
    event = {"event": "x", "SET_COOKIE": "a", "x_internal_token": "b", "Code": "c", "n": 1}

    assert redact_sensitive(None, "info", event) == {
        "event": "x",
        "SET_COOKIE": REDACTED,
        "x_internal_token": REDACTED,
        "Code": REDACTED,
        "n": 1,
    }


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "current_password",
        "password_hash",
        "passwd",
        "db_password",
        "client_secret",
        "token",
        "refresh_token",
        "X-Internal-Token",
        "internal_api_token",
        "Authorization",
        "Set-Cookie",
        "jwt_private_key",
        "api_key",
        "X-Api-Key",
        "otp",
        "otp_secret",
        "code",
        "verification_code",
        b"authorization",
        # Falsos negativos da 2ª revisão
        "apikey",
        "apiKey",
        "privateKey",
        "private-key",
        "passphrase",
        "pwd",
        "pass",
        "senha",
        "codigo",
        "code_hash",
        "verification_code_hash",
        "verificationCode",
        "otpCode",
        "totp",
        "pin",
        "credentials",
        "credential",
        "jwt",
        "bearer",
        "database_url",
        "databaseUrl",
        "dsn",
        "signature",
        "session_key",
        "x-amz-security-token",
        "proxy-authorization",
        "access_key",
        "secret_key",
        "hmac_key",
        "signing_key",
        "encryption_key",
        "pepper",
        "x-csrf-token",
        "mfa_code",
        # Falsos negativos da revisão do #5: plural, acento, separadores e semente de TOTP
        "codes",
        "recovery_codes",
        "recoveryCodes",
        "backup_codes",
        "verification_codes",
        "código",
        "CÓDIGO",
        "códigos",
        "códigoVerificação",
        "codigos_recuperacao",
        "auth_codigo",
        "señha",
        "auth.code",
        "otp code",
        "pass word",
        "otpauth",
        "otpauth_uri",
        "otpAuthUrl",
        "seed",
        "totp_seed",
        "ｐａｓｓｗｏｒｄ",
        # 2ª revisão do #5: 2FA, passcode, novos prefixos e separadores : e /
        "2FA_code",
        "2FACode",
        "user2faCode",
        "2_fa_code",
        "passcode",
        "userPasscode",
        "activation_code",
        "verify_code",
        "confirm_code",
        "two_factor_code",
        "twoFactorCode",
        "tfa_code",
        "magic_code",
        "auth:code",
        "auth/code",
    ],
)
def test_sensitive_key_variants(key: str | bytes) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key",
    [
        "status_code",
        "error_code",
        "idempotency_key",
        "template",
        "to_masked",
        "request_id",
        42,
        # Metadados e códigos que não são segredo (falsos positivos da 2ª revisão)
        "token_type",
        "tokens_used",
        "max_tokens",
        "token_id",
        "token_family_id",
        "refresh_token_id",
        "token_expires_at",
        "token_count",
        "code_expired",
        "http_status_code",
        "response_status_code",
        "zip_code",
        "country_code",
        "exit_code",
        "smtp_code",
        "mysql_error_code",
        "db_error_code",
        "reason_code",
        "sqlstate_code",
        "cookie_name",
        "password_changed_at",
        "password_reset_requested",
        "secret_rotation",
        "authorization_header_present",
        "code_length",
        "code_attempts",
        "attempts_remaining",
        "has_password",
        "otp_attempts",
        "status_codes",
        "error_codes",
        "zip_codes",
        "country.code",
        "http status code",
        "códigos_count",
        "seed_count",
        # Códigos de diagnóstico: o prefixo de segredo só vale logo antes de code(s)
        "email_error_code",
        "sms_status_code",
        "sms_provider_error_code",
        "email_bounce_code",
        "login_failure_code",
        "access_denied_code",
        "email_template_code",
        "login_response_code",
        "email_error_codes",
        "sms_delivery_status_codes",
        "codigo_ibge",
        "código_postal",
        "codigos_erro",
        "activation_error_code",
        "verify_status_code",
        "magic_link_status_code",
        "two_factor_error_code",
        "2fa_enabled",
        "api/status_code",
    ],
)
def test_non_sensitive_keys(key: object) -> None:
    assert not is_sensitive_key(key)


@pytest.mark.parametrize(
    "key",
    ["auth_code", "reset_code", "mfa_code", "otp_code", "one_time_code", "pin_code", "code_hash"],
)
def test_secret_codes_by_prefix(key: str) -> None:
    assert is_sensitive_key(key)


def test_pairs_outside_headers_are_left_alone(json_logs: JsonLogs) -> None:
    get_logger("t").info(
        "x",
        fields=["password", "email"],
        loc=("code", "too_short"),
        request_headers=[("Authorization", "Bearer abc")],
    )

    [line] = json_logs()
    assert line["fields"] == ["password", "email"]
    assert line["loc"] == ["code", "too_short"]
    assert line["request_headers"] == [["Authorization", REDACTED]]


def test_header_pairs_are_redacted_by_name(json_logs: JsonLogs) -> None:
    get_logger("t").info(
        "x",
        raw_headers=[(b"authorization", b"Bearer abc"), (b"x-internal-token", b"tok-interno")],
        headers=[["Cookie", "sid=1"], ["Accept", "application/json"]],
        error_code="invalid_credentials",
        code="123456",
    )

    [line] = json_logs()
    output = json.dumps(line)
    for secret in ("Bearer abc", "tok-interno", "sid=1", "123456"):
        assert secret not in output
    assert line["raw_headers"] == [
        ["b'authorization'", REDACTED],
        ["b'x-internal-token'", REDACTED],
    ]
    assert line["headers"] == [["Cookie", REDACTED], ["Accept", "application/json"]]
    assert line["error_code"] == "invalid_credentials"
    assert line["code"] == REDACTED


def test_exception_does_not_leak_locals(json_logs: JsonLogs) -> None:
    def boom() -> None:
        secret = "s3cr3t"
        raise ValueError("falhou " + str(len(secret)))

    try:
        boom()
    except ValueError:
        get_logger("t").exception("deu_ruim")

    output = json.dumps(json_logs())
    assert "s3cr3t" not in output
    assert json_logs()[0]["exception"][0]["exc_type"] == "ValueError"


@pytest.mark.parametrize(
    ("email", "masked"),
    [
        ("joao@x.com", "j***@x.com"),
        ("a@x.com", "a***@x.com"),
        ("semarroba", "***"),
        ("", "***"),
    ],
)
def test_mask_email(email: str, masked: str) -> None:
    assert mask_email(email) == masked


def test_validation_error_message_is_redacted_by_the_formatter(json_logs: JsonLogs) -> None:
    # Modelo sem hide_input_in_errors: só o formatter de exceção impede o vazamento
    exc = _validation_error("hunter2")
    assert "hunter2" in str(exc)

    _log_exception(exc)

    assert "hunter2" not in json.dumps(json_logs())
    [stack] = json_logs()[0]["exception"]
    assert stack["exc_type"] == "ValidationError"
    assert stack["exc_value"] == REDACTED
    assert stack["frames"]


async def test_sql_error_is_redacted_by_the_formatter(json_logs: JsonLogs) -> None:
    # Engine sem hide_parameters: só o formatter de exceção impede o vazamento
    metadata = sa.MetaData()
    table = sa.Table("t", metadata, sa.Column("email", sa.String(50), unique=True))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
            await conn.execute(table.insert().values(email="segredo@sql.test"))
        with pytest.raises(IntegrityError) as caught:
            async with engine.begin() as conn:
                await conn.execute(table.insert().values(email="segredo@sql.test"))
    finally:
        await engine.dispose()
    assert "segredo@sql.test" in str(caught.value)

    _log_exception(caught.value)

    output = json.dumps([e for e in json_logs() if e["event"] == "falhou"])
    assert "IntegrityError" in output
    assert "segredo@sql.test" not in output


class _Strict(BaseModel):
    n: int


def _validation_error(secret: str) -> ValidationError:
    try:
        _Strict(n=secret)  # type: ignore[arg-type]
    except ValidationError as exc:
        return exc
    raise AssertionError("deveria falhar")


def _log_exception(exc: BaseException) -> None:
    try:
        raise exc
    except BaseException:
        get_logger("t").exception("falhou")


def test_common_exception_keeps_its_message(json_logs: JsonLogs) -> None:
    _log_exception(ValueError("x"))

    [stack] = json_logs()[0]["exception"]
    assert stack["exc_value"] == "x"


def test_db_error_is_redacted_and_keeps_errno(json_logs: JsonLogs) -> None:
    driver_error = pymysql.err.IntegrityError(
        1062, "Duplicate entry 'x@y' for key 'uq_users_email'"
    )
    try:
        try:
            raise driver_error
        except pymysql.err.IntegrityError as orig:
            raise sa_exc.IntegrityError("INSERT INTO users ...", None, orig) from orig
    except sa_exc.IntegrityError:
        get_logger("t").exception("falhou")

    [line] = json_logs()
    assert "x@y" not in json.dumps(line)
    outer, cause = line["exception"]
    assert (outer["exc_type"], outer["exc_value"], outer["db_errno"]) == (
        "IntegrityError",
        REDACTED,
        1062,
    )
    assert cause["exc_value"] == REDACTED
    assert cause["is_cause"] is True


def test_redaction_follows_the_cause_chain(json_logs: JsonLogs) -> None:
    try:
        try:
            raise _validation_error("hunter2")
        except ValidationError as inner:
            raise RuntimeError("cadastro falhou") from inner
    except RuntimeError:
        get_logger("t").exception("falhou")

    [line] = json_logs()
    assert "hunter2" not in json.dumps(line)
    outer, cause = line["exception"]
    assert outer["exc_value"] == "cadastro falhou"
    assert (cause["exc_type"], cause["exc_value"]) == ("ValidationError", REDACTED)


def test_redaction_inside_exception_groups(json_logs: JsonLogs) -> None:
    _log_exception(
        ExceptionGroup(
            "lote", [ValueError("visivel"), ExceptionGroup("sub", [_validation_error("hunter2")])]
        )
    )

    output = json.dumps(json_logs())
    assert "hunter2" not in output
    assert "visivel" in output


def test_header_pair_with_list_value_is_redacted(json_logs: JsonLogs) -> None:
    get_logger("t").info("x", headers=[("authorization", ["Bearer zz"])])

    [line] = json_logs()
    assert line["headers"] == [["authorization", REDACTED]]


def test_redact_covers_the_names_from_the_audit_issue() -> None:
    data = {"password": "p", "token": "t", "code": "c", "secret": "s", "email_masked": "a***"}

    assert redact(data) == {
        "password": REDACTED,
        "token": REDACTED,
        "code": REDACTED,
        "secret": REDACTED,
        "email_masked": "a***",
    }


def test_redact_is_recursive_and_keeps_metadata_about_secrets() -> None:
    data = {
        "nested": {"apiKey": "k", "status_code": 401},
        "items": [{"verification_code": "123456"}, {"token_type": "bearer"}],
        "headers": [["Authorization", "Bearer x"], ["Accept", "*/*"]],
    }

    assert redact(data) == {
        "nested": {"apiKey": REDACTED, "status_code": 401},
        "items": [{"verification_code": REDACTED}, {"token_type": "bearer"}],
        "headers": [["Authorization", REDACTED], ["Accept", "*/*"]],
    }


def test_redact_does_not_mutate_the_original() -> None:
    data = {"nested": {"password": "p"}, "items": [{"secret": "s"}]}

    redact(data)

    assert data == {"nested": {"password": "p"}, "items": [{"secret": "s"}]}
