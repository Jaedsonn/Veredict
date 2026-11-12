import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any

import aiosmtplib
from aiosmtplib import SMTPException, SMTPRecipientsRefused, SMTPResponseException
from pydantic import SecretStr

from notification_service.domain import EmailDeliveryError, OutgoingEmail
from notification_service.ports import Clock, MessageIdFactory
from veriditi_common.db_types import utcnow


def message_id_factory(domain: str) -> MessageIdFactory:
    """Message-ID no domínio do remetente, gerado uma vez por notificação"""

    def make() -> str:
        return make_msgid(domain=domain)

    return make


def build_message(email: OutgoingEmail, *, sender: str, date: datetime) -> EmailMessage:
    """multipart/alternative com o texto primeiro: o cliente mostra a última parte que entende"""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email.to
    message["Subject"] = email.subject
    message["Message-ID"] = email.message_id
    message["Date"] = format_datetime(date)
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    return message


def _is_permanent(code: int) -> bool:
    return 500 <= code < 600


def _delivery_error(exc: SMTPException | OSError) -> EmailDeliveryError:
    """Só tipo e código: a mensagem do servidor (550 ... <endereço>) traz o destinatário"""
    reason = type(exc).__name__
    if isinstance(exc, SMTPRecipientsRefused):
        codes = [refused.code for refused in exc.recipients]
        permanent = bool(codes) and all(_is_permanent(code) for code in codes)
        return EmailDeliveryError(
            reason, permanent=permanent, smtp_code=codes[0] if codes else None
        )
    if isinstance(exc, SMTPResponseException):
        return EmailDeliveryError(reason, permanent=_is_permanent(exc.code), smtp_code=exc.code)
    return EmailDeliveryError(reason)


class SmtpEmailSender:
    """Uma conexão por envio: o volume da Sprint 1 não justifica um pool SMTP"""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender_name: str,
        sender_address: str,
        username: str | None,
        password: SecretStr | None,
        start_tls: bool,
        timeout: float,
        transport: Callable[..., Awaitable[Any]] = aiosmtplib.send,
        clock: Clock = utcnow,
    ) -> None:
        self._host = host
        self._port = port
        # formataddr põe aspas no nome: "Veriditi, Inc" sem elas viraria 2 mailboxes
        self._from_header = formataddr((sender_name, sender_address))
        self._sender_address = sender_address
        self._username = username
        self._password = password
        self._start_tls = start_tls
        self._timeout = timeout
        self._transport = transport
        self._clock = clock

    async def send(self, email: OutgoingEmail) -> None:
        message = build_message(email, sender=self._from_header, date=self._clock())
        password = self._password.get_secret_value() if self._username and self._password else None
        try:
            # O timeout do aiosmtplib vale por comando; este limita a tentativa inteira
            async with asyncio.timeout(self._timeout):
                await self._transport(
                    message,
                    # Envelope explícito: não depende de o aiosmtplib reler o From e o To
                    sender=self._sender_address,
                    recipients=[email.to],
                    hostname=self._host,
                    port=self._port,
                    username=self._username,
                    password=password,
                    # Explícito: None faria o aiosmtplib tentar o STARTTLS sozinho
                    start_tls=self._start_tls,
                    timeout=self._timeout,
                )
        # TimeoutError é OSError: o estouro do total cai como transitório
        except (SMTPException, OSError) as exc:
            error = _delivery_error(exc)
        else:
            return
        # Fora do except: nem __cause__ nem __context__ levam a exceção com o endereço
        raise error
