import io
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from structlog.contextvars import bound_contextvars

from veriditi_common.logging import (
    REDACTED,
    SENSITIVE_KEYS,
    configure_logging,
    get_logger,
    mask_email,
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
    assert {"password", "code", "x-internal-token"} <= SENSITIVE_KEYS


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
