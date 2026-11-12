import asyncio
import ssl
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Any, Protocol

from aiosmtplib import (
    SMTP,
    SMTPConnectError,
    SMTPException,
    SMTPNotSupported,
    SMTPRecipientsRefused,
    SMTPResponseException,
)
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
    # Antes do OSError genérico: servidor sem STARTTLS/SMTPUTF8 ou certificado inválido não mudam
    if isinstance(exc, SMTPNotSupported | ssl.SSLCertVerificationError) or _cert_rejected(exc):
        return EmailDeliveryError(reason, permanent=True)
    # SMTPException puro só sai de erro de configuração: STARTTLS ou AUTH ausentes no servidor
    if type(exc) is SMTPException:
        return EmailDeliveryError(reason, permanent=True)
    return EmailDeliveryError(reason)


def _cert_rejected(exc: BaseException) -> bool:
    """O use_tls embrulha a falha do handshake em SMTPConnectError"""
    if not isinstance(exc, SMTPConnectError):
        return False
    causes = (exc.__cause__, exc.__context__)
    return any(isinstance(cause, ssl.SSLCertVerificationError) for cause in causes)


class SmtpClient(Protocol):
    """O pedaço do aiosmtplib.SMTP que o envio usa; os testes trocam por um falso"""

    async def connect(self) -> Any: ...

    async def login(self, username: str, password: str, /) -> Any: ...

    async def send_message(
        self, message: EmailMessage, /, *, sender: str, recipients: Sequence[str]
    ) -> Any: ...

    async def quit(self) -> Any: ...

    def close(self) -> None: ...


SmtpClientFactory = Callable[..., SmtpClient]


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
        use_tls: bool,
        timeout: float,
        client_factory: SmtpClientFactory = SMTP,
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
        self._use_tls = use_tls
        self._timeout = timeout
        self._client_factory = client_factory
        self._clock = clock

    async def send(self, email: OutgoingEmail) -> None:
        message = build_message(email, sender=self._from_header, date=self._clock())
        # Explícito: start_tls=None faria o aiosmtplib tentar o STARTTLS sozinho
        client = self._client_factory(
            hostname=self._host,
            port=self._port,
            use_tls=self._use_tls,
            start_tls=self._start_tls,
            timeout=self._timeout,
        )
        try:
            # O timeout do aiosmtplib vale por comando; este limita a tentativa inteira
            async with asyncio.timeout(self._timeout):
                await client.connect()
                if self._username is not None and self._password is not None:
                    await client.login(self._username, self._password.get_secret_value())
                # Envelope explícito: não depende de o aiosmtplib reler o From e o To
                await client.send_message(
                    message, sender=self._sender_address, recipients=[email.to]
                )
        # TimeoutError é OSError: o estouro do total cai como transitório
        except (SMTPException, OSError) as exc:
            # close e não QUIT: um servidor travado seguraria a tentativa por mais um timeout
            client.close()
            error = _delivery_error(exc)
        except BaseException:
            client.close()
            raise
        else:
            # Fora do timeout total: o QUIT não pode transformar entrega em falha e reenvio
            await self._quit_quietly(client)
            return
        # Fora do except: nem __cause__ nem __context__ levam a exceção com o endereço
        raise error

    async def _quit_quietly(self, client: SmtpClient) -> None:
        """Depois do DATA aceito o e-mail já foi: QUIT lento ou recusado não vira falha"""
        try:
            with suppress(Exception):
                async with asyncio.timeout(self._timeout):
                    await client.quit()
        finally:
            client.close()
