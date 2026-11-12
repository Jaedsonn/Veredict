from typing import Any

import pytest
from pydantic import JsonValue

from notification_service.catalog import EmailVerificationData, WelcomeData, build_registry
from notification_service.domain import InvalidTemplateDataError, UnknownTemplateError
from notification_service.registry import TemplateRegistry, TemplateSpec
from veriditi_common.notifications import NotificationTemplate

VALID: dict[str, JsonValue] = {"name": "João", "code": "042137", "expires_in_minutes": 15}


def _errors(template: str, data: dict[str, JsonValue]) -> list[dict[str, Any]]:
    with pytest.raises(InvalidTemplateDataError) as exc:
        build_registry().parse(template, data)
    return exc.value.errors


def test_names_are_sorted_and_cover_the_producer_catalog() -> None:
    names = build_registry().names

    assert names == ("email_verification", "welcome")
    assert set(names) >= {template.value for template in NotificationTemplate}


def test_unknown_template_lists_valid_names() -> None:
    with pytest.raises(UnknownTemplateError) as exc:
        build_registry().parse("password_reset", {})

    assert exc.value.template == "password_reset"
    assert exc.value.valid == ("email_verification", "welcome")


def test_duplicate_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="welcome"):
        TemplateRegistry(
            [TemplateSpec("welcome", WelcomeData), TemplateSpec("welcome", WelcomeData)]
        )


def test_valid_email_verification_data() -> None:
    data = build_registry().parse("email_verification", VALID)

    assert data == EmailVerificationData(name="João", code="042137", expires_in_minutes=15)


@pytest.mark.parametrize("field", ["name", "code", "expires_in_minutes"])
def test_each_missing_field_is_reported(field: str) -> None:
    data = {key: value for key, value in VALID.items() if key != field}

    assert _errors("email_verification", data) == [
        {"type": "missing", "loc": (field,), "msg": "Field required"}
    ]


def test_extra_field_is_forbidden() -> None:
    [error] = _errors("email_verification", {**VALID, "link": "http://evil"})

    assert (error["type"], error["loc"]) == ("extra_forbidden", ("link",))


@pytest.mark.parametrize("code", ["12345", "1234567", "12a456", "123456\n", "١٢٣٤٥٦"])
def test_code_needs_six_ascii_digits(code: str) -> None:
    [error] = _errors("email_verification", {**VALID, "code": code})

    assert (error["type"], error["loc"]) == ("string_pattern_mismatch", ("code",))


def test_code_as_int_is_rejected() -> None:
    [error] = _errors("email_verification", {**VALID, "code": 123456})

    assert (error["type"], error["loc"]) == ("string_type", ("code",))


@pytest.mark.parametrize("value", [0, 1441, True, "15", 15.0])
def test_expires_in_minutes_is_strict_int_in_range(value: JsonValue) -> None:
    [error] = _errors("email_verification", {**VALID, "expires_in_minutes": value})

    assert error["loc"] == ("expires_in_minutes",)


@pytest.mark.parametrize(
    "name",
    ["", "   ", "a" * 121, "Ana\r\nBcc: x@evil.com", "Ana\x00", "Ana\x7f", "Ana\tSilva"],
    ids=["empty", "blank", "121-chars", "crlf", "nul", "del", "tab"],
)
def test_invalid_names_are_rejected(name: str) -> None:
    [error] = _errors("email_verification", {**VALID, "name": name})

    assert error["loc"] == ("name",)


def test_name_is_stripped_and_120_chars_fit() -> None:
    registry = build_registry()

    assert registry.parse("welcome", {"name": " Ana "}) == WelcomeData(name="Ana")
    assert registry.parse("welcome", {"name": "a" * 120}) == WelcomeData(name="a" * 120)


def test_welcome_requires_name_and_forbids_extra() -> None:
    assert [e["type"] for e in _errors("welcome", {})] == ["missing"]
    assert [e["type"] for e in _errors("welcome", {"name": "Ana", "code": "1"})] == [
        "extra_forbidden"
    ]


def test_errors_never_carry_input_or_context() -> None:
    errors = _errors("email_verification", {"name": "x" * 200, "code": "999999x", "y": "z"})

    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert "999999x" not in repr(errors)
