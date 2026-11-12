import asyncio
import email
import email.policy
import re
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any

import pytest
from aiosmtplib import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPNotSupported,
    SMTPRecipientRefused,
    SMTPRecipientsRefused,
    SMTPResponseException,
    SMTPServerDisconnected,
    SMTPTimeoutError,
)
from pydantic import SecretStr

from notification_service.adapters.memory_sender import FailingEmailSender
from notification_service.adapters.smtp_sender import (
    SmtpEmailSender,
    build_message,
    message_id_factory,
)
from notification_service.domain import EmailDeliveryError, OutgoingEmail

TO = "joao@exemplo.com"
SENDER = "Veriditi <no-reply@veriditi.app>"
SECRET = "s3nh4-smtp-super-secreta"
NOW = datetime(2026, 11, 12, 15, 0, 0, 123456, tzinfo=UTC)
EMAIL = OutgoingEmail(
    to=TO,
    subject="Seu código de verificação Veriditi",
    text="Olá, João! Código 042137\n",
    html="<p>Olá, João! Código <b>042137</b></p>\n",
    message_id="<fixed-1@veriditi.app>",
)


class FakeTransport:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[EmailMessage, dict[str, Any]]] = []

    async def __call__(self, message: EmailMessage, **kwargs: Any) -> None:
        self.calls.append((message, kwargs))
        if self.error is not None:
            raise self.error


def _sender(transport: FakeTransport, **overrides: Any) -> SmtpEmailSender:
    values: dict[str, Any] = {
        "host": "mailpit",
        "port": 1025,
        "sender_name": "Veriditi",
        "sender_address": "no-reply@veriditi.app",
        "username": None,
        "password": None,
        "start_tls": False,
        "use_tls": False,
        "timeout": 10.0,
        "transport": transport,
        "clock": lambda: NOW,
    }
    values.update(overrides)
    return SmtpEmailSender(**values)


def test_message_is_multipart_alternative_with_text_then_html() -> None:
    message = build_message(EMAIL, sender=SENDER, date=NOW)

    assert message.get_content_type() == "multipart/alternative"
    text, html = message.iter_parts()
    assert text["Content-Type"] == 'text/plain; charset="utf-8"'
    assert html.get_content_type() == "text/html"
    assert text.get_content() == EMAIL.text
    assert html.get_content() == EMAIL.html


def test_headers_survive_the_wire_format() -> None:
    raw = bytes(build_message(EMAIL, sender=SENDER, date=NOW))
    parsed = email.message_from_bytes(raw, policy=email.policy.default)

    assert parsed["From"] == SENDER
    assert parsed["To"] == TO
    assert parsed["Message-ID"] == "<fixed-1@veriditi.app>"
    assert parsed["Date"] == "Thu, 12 Nov 2026 15:00:00 +0000"
    # Acentuado: vai codificado em RFC 2047 e volta igual
    assert b"=?utf-8?q?c=C3=B3digo_de_verifica=C3=A7=C3=A3o?=" in raw
    assert parsed["Subject"] == EMAIL.subject


def test_message_ids_are_unique_in_sender_domain() -> None:
    make = message_id_factory("veriditi.app")
    ids = {make() for _ in range(100)}

    assert len(ids) == 100
    assert all(re.fullmatch(r"<[^<>@\s]+@veriditi\.app>", mid) for mid in ids)


@pytest.mark.parametrize(("start_tls", "use_tls"), [(False, False), (True, False), (False, True)])
async def test_transport_gets_explicit_connection_settings(start_tls: bool, use_tls: bool) -> None:
    transport = FakeTransport()

    await _sender(transport, start_tls=start_tls, use_tls=use_tls).send(EMAIL)

    [(message, kwargs)] = transport.calls
    assert kwargs == {
        "sender": "no-reply@veriditi.app",
        "recipients": [TO],
        "hostname": "mailpit",
        "port": 1025,
        "username": None,
        "password": None,
        "start_tls": start_tls,
        "use_tls": use_tls,
        "timeout": 10.0,
    }
    assert message["Message-ID"] == EMAIL.message_id
    assert message["Date"] == "Thu, 12 Nov 2026 15:00:00 +0000"
    assert message["From"] == SENDER


async def test_password_is_revealed_only_in_the_transport_call() -> None:
    transport = FakeTransport()
    sender = _sender(transport, username="apikey", password=SecretStr(SECRET))

    await sender.send(EMAIL)

    [(_message, kwargs)] = transport.calls
    assert (kwargs["username"], kwargs["password"]) == ("apikey", SECRET)
    assert SECRET not in repr(vars(sender))


def _refused(*codes: int) -> SMTPRecipientsRefused:
    return SMTPRecipientsRefused(
        [SMTPRecipientRefused(code, f"{code} <{TO}> nope", TO) for code in codes]
    )


@pytest.mark.parametrize(
    ("error", "reason", "permanent", "smtp_code"),
    [
        (SMTPConnectError(f"conexão recusada para {TO}"), "SMTPConnectError", False, None),
        (SMTPServerDisconnected("caiu"), "SMTPServerDisconnected", False, None),
        (SMTPTimeoutError("lento"), "SMTPTimeoutError", False, None),
        (OSError("rede"), "OSError", False, None),
        (TimeoutError(), "TimeoutError", False, None),
        (SMTPResponseException(451, "tente depois"), "SMTPResponseException", False, 451),
        (SMTPResponseException(550, f"<{TO}> não existe"), "SMTPResponseException", True, 550),
        (SMTPAuthenticationError(535, "credencial"), "SMTPAuthenticationError", True, 535),
        (_refused(550), "SMTPRecipientsRefused", True, 550),
        (_refused(450), "SMTPRecipientsRefused", False, 450),
        (_refused(550, 450), "SMTPRecipientsRefused", False, 550),
        (SMTPNotSupported("STARTTLS ausente"), "SMTPNotSupported", True, None),
        (SMTPNotSupported("SMTPUTF8 ausente"), "SMTPNotSupported", True, None),
        (
            ssl.SSLCertVerificationError(1, "certificate verify failed"),
            "SSLCertVerificationError",
            True,
            None,
        ),
        (ssl.SSLError(1, "handshake interrompido"), "SSLError", False, None),
    ],
    ids=[
        "connect",
        "disconnected",
        "timeout-smtp",
        "oserror",
        "timeout",
        "451",
        "550",
        "auth-535",
        "recipients-550",
        "recipients-450",
        "recipients-mixed",
        "starttls-not-supported",
        "smtputf8-not-supported",
        "cert-verification",
        "other-ssl-error",
    ],
)
async def test_errors_are_classified_without_the_address(
    error: Exception, reason: str, permanent: bool, smtp_code: int | None
) -> None:
    with pytest.raises(EmailDeliveryError) as exc:
        await _sender(FakeTransport(error)).send(EMAIL)

    assert (exc.value.reason, exc.value.permanent, exc.value.smtp_code) == (
        reason,
        permanent,
        smtp_code,
    )
    assert TO not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


async def test_unexpected_errors_are_not_masked() -> None:
    with pytest.raises(RuntimeError, match="bug"):
        await _sender(FakeTransport(RuntimeError("bug"))).send(EMAIL)


async def test_failing_sender_fails_n_times_then_delivers() -> None:
    sender = FailingEmailSender(fail_times=2)

    for _ in range(2):
        with pytest.raises(EmailDeliveryError):
            await sender.send(EMAIL)
    await sender.send(EMAIL)

    assert sender.calls == [EMAIL, EMAIL, EMAIL]
    assert sender.sent == [EMAIL]


def test_outgoing_email_repr_hides_address_and_bodies() -> None:
    shown = repr(EMAIL)

    assert TO not in shown
    assert "042137" not in shown
    assert EMAIL.message_id in shown


class SlowTransport(FakeTransport):
    """Cada comando cabe no timeout do aiosmtplib, mas a soma não"""

    async def __call__(self, message: EmailMessage, **kwargs: Any) -> None:
        self.calls.append((message, kwargs))
        await asyncio.sleep(1)


async def test_whole_attempt_is_bounded_by_the_timeout() -> None:
    transport = SlowTransport()

    with pytest.raises(EmailDeliveryError) as exc:
        await _sender(transport, timeout=0.05).send(EMAIL)

    assert (exc.value.reason, exc.value.permanent, exc.value.smtp_code) == (
        "TimeoutError",
        False,
        None,
    )
    assert exc.value.__context__ is None
    [(_message, kwargs)] = transport.calls
    assert kwargs["timeout"] == 0.05
