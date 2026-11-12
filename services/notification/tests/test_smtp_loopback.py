import asyncio
import email
import email.policy
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

import pytest

from notification_service.adapters.smtp_sender import SmtpEmailSender
from notification_service.domain import EmailDeliveryError, OutgoingEmail

TO = "joao@exemplo.com"
EMAIL = OutgoingEmail(
    to=TO,
    subject="Seu código de verificação Veriditi",
    text="Olá, João! Código 042137\n.linha com ponto\n",
    html="<p>Olá, João! Código <b>042137</b></p>\n",
    message_id="<fixed-1@veriditi.app>",
)


@dataclass
class SmtpStub:
    """Servidor SMTP mínimo em loopback, com os defeitos que cada teste liga"""

    answer_quit: bool = True
    stall_after_ehlo: bool = False
    envelopes: list[tuple[str, list[str]]] = field(default_factory=list)
    messages: list[bytes] = field(default_factory=list)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"220 stub ESMTP\r\n")
        await writer.drain()
        sender, recipients, data, in_data = "", [], [], False
        while line := await reader.readline():
            if in_data:
                if line == b".\r\n":
                    in_data = False
                    self.envelopes.append((sender, recipients))
                    self.messages.append(b"".join(data))
                    writer.write(b"250 queued\r\n")
                else:
                    data.append(line[1:] if line.startswith(b"..") else line)
            else:
                command = line.decode().strip()
                verb = command[:4].upper()
                if verb == "EHLO":
                    writer.write(b"250-stub\r\n250 8BITMIME\r\n")
                elif self.stall_after_ehlo:
                    continue
                elif verb == "MAIL":
                    # Só o endereço: o aiosmtplib acrescenta BODY=8BITMIME
                    sender, recipients, data = command[10:].split()[0], [], []
                    writer.write(b"250 ok\r\n")
                elif verb == "RCPT":
                    recipients.append(command[8:].split()[0])
                    writer.write(b"250 ok\r\n")
                elif verb == "DATA":
                    in_data = True
                    writer.write(b"354 go\r\n")
                elif verb == "QUIT":
                    if not self.answer_quit:
                        continue
                    writer.write(b"221 bye\r\n")
                else:
                    writer.write(b"250 ok\r\n")
            await writer.drain()
        writer.close()


Serve = Callable[[SmtpStub], Awaitable[int]]


@pytest.fixture
async def serve() -> AsyncIterator[Serve]:
    servers: list[asyncio.Server] = []

    async def start(stub: SmtpStub) -> int:
        server = await asyncio.start_server(stub.handle, "127.0.0.1", 0)
        servers.append(server)
        port: int = server.sockets[0].getsockname()[1]
        return port

    yield start
    for server in servers:
        server.close()
        await server.wait_closed()


def _sender(port: int, timeout: float) -> SmtpEmailSender:
    return SmtpEmailSender(
        host="127.0.0.1",
        port=port,
        sender_name="Veriditi, Inc",
        sender_address="no-reply@veriditi.app",
        username=None,
        password=None,
        start_tls=False,
        use_tls=False,
        timeout=timeout,
    )


async def test_delivers_once_with_envelope_and_multipart(serve: Serve) -> None:
    stub = SmtpStub()

    await _sender(await serve(stub), timeout=2.0).send(EMAIL)

    assert stub.envelopes == [("<no-reply@veriditi.app>", [f"<{TO}>"])]
    [raw] = stub.messages
    # CRLF é o formato de fio; o conteúdo comparado usa \n como o template
    parsed = email.message_from_bytes(raw.replace(b"\r\n", b"\n"), policy=email.policy.default)
    assert parsed["From"] == '"Veriditi, Inc" <no-reply@veriditi.app>'
    assert parsed["To"] == TO
    assert parsed["Message-ID"] == EMAIL.message_id
    assert parsed.get_content_type() == "multipart/alternative"
    text, html = parsed.iter_parts()
    assert text.get_content() == EMAIL.text
    assert html.get_content() == EMAIL.html


async def test_server_ignoring_quit_still_counts_as_one_delivery(serve: Serve) -> None:
    stub = SmtpStub(answer_quit=False)

    # Antes, o QUIT preso estourava o timeout depois do DATA: falha falsa e reenvio
    await _sender(await serve(stub), timeout=0.3).send(EMAIL)

    assert len(stub.messages) == 1


async def test_stalled_server_fails_within_one_timeout(serve: Serve) -> None:
    stub = SmtpStub(stall_after_ehlo=True)
    sender = _sender(await serve(stub), timeout=0.5)

    started = time.perf_counter()
    with pytest.raises(EmailDeliveryError) as exc:
        await sender.send(EMAIL)
    elapsed = time.perf_counter() - started

    assert exc.value.permanent is False
    # Antes levava 2 timeouts: o QUIT do __aexit__ esperava mais um inteiro
    assert 0.45 <= elapsed < 0.8
    assert stub.messages == []
