import asyncio
import email
import email.policy
import ipaddress
import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

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
    starttls: ssl.SSLContext | None = None
    envelopes: list[tuple[str, list[str]]] = field(default_factory=list)
    messages: list[bytes] = field(default_factory=list)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # O cliente aborta a conexão nos testes de falha: não é erro do servidor
        with suppress(ConnectionError, ssl.SSLError):
            await self._dialog(reader, writer)
        writer.close()

    async def _dialog(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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
                    extension = b"STARTTLS" if self.starttls else b"8BITMIME"
                    writer.write(b"250-stub\r\n250 " + extension + b"\r\n")
                elif verb == "STAR" and self.starttls:
                    writer.write(b"220 ready\r\n")
                    await writer.drain()
                    await writer.start_tls(self.starttls)
                    continue
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


Serve = Callable[..., Awaitable[int]]


@pytest.fixture(scope="module")
def server_tls(tmp_path_factory: pytest.TempPathFactory) -> ssl.SSLContext:
    """Certificado autoassinado para localhost: nenhum cliente com a CA do sistema confia nele"""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    directory: Path = tmp_path_factory.mktemp("tls")
    cert_file, key_file = directory / "cert.pem", directory / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_file, key_file)
    return context


@pytest.fixture
async def serve() -> AsyncIterator[Serve]:
    servers: list[asyncio.Server] = []

    async def start(stub: SmtpStub, *, tls: ssl.SSLContext | None = None) -> int:
        server = await asyncio.start_server(stub.handle, "127.0.0.1", 0, ssl=tls)
        servers.append(server)
        port: int = server.sockets[0].getsockname()[1]
        return port

    yield start
    for server in servers:
        server.close()
        await server.wait_closed()


def _sender(
    port: int, timeout: float, *, start_tls: bool = False, use_tls: bool = False
) -> SmtpEmailSender:
    return SmtpEmailSender(
        host="127.0.0.1",
        port=port,
        sender_name="Veriditi, Inc",
        sender_address="no-reply@veriditi.app",
        username=None,
        password=None,
        start_tls=start_tls,
        use_tls=use_tls,
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


async def _failure(sender: SmtpEmailSender, outgoing: OutgoingEmail = EMAIL) -> EmailDeliveryError:
    with pytest.raises(EmailDeliveryError) as exc:
        await sender.send(outgoing)
    return exc.value


async def test_starttls_against_server_without_it_is_permanent(serve: Serve) -> None:
    stub = SmtpStub()

    error = await _failure(_sender(await serve(stub), timeout=2.0, start_tls=True))

    # aiosmtplib levanta SMTPException puro: reenviar não faz o servidor ganhar STARTTLS
    assert (error.reason, error.permanent) == ("SMTPException", True)
    assert stub.messages == []


async def test_implicit_tls_with_untrusted_certificate_is_permanent(
    serve: Serve, server_tls: ssl.SSLContext
) -> None:
    stub = SmtpStub()

    error = await _failure(_sender(await serve(stub, tls=server_tls), timeout=2.0, use_tls=True))

    # O handshake falha no connect: SMTPConnectError com o SSLCertVerificationError na causa
    assert (error.reason, error.permanent) == ("SMTPConnectError", True)
    assert stub.messages == []


async def test_starttls_with_untrusted_certificate_is_permanent(
    serve: Serve, server_tls: ssl.SSLContext
) -> None:
    stub = SmtpStub(starttls=server_tls)

    error = await _failure(_sender(await serve(stub), timeout=2.0, start_tls=True))

    assert (error.reason, error.permanent) == ("SSLCertVerificationError", True)
    assert stub.messages == []


async def test_idn_domain_goes_as_punycode_in_envelope_and_header(serve: Serve) -> None:
    stub = SmtpStub()

    # Sem SMTPUTF8 no servidor: antes virava SMTPNotSupported e o To saía quebrado
    await _sender(await serve(stub), timeout=2.0).send(replace(EMAIL, to="ana@exemplo.café"))

    assert stub.envelopes == [("<no-reply@veriditi.app>", ["<ana@exemplo.xn--caf-dma>"])]
    [raw] = stub.messages
    assert b"\nTo: ana@exemplo.xn--caf-dma\r\n" in raw


async def test_non_ascii_local_part_needs_smtputf8(serve: Serve) -> None:
    stub = SmtpStub()
    sender = _sender(await serve(stub), timeout=2.0)

    error = await _failure(sender, replace(EMAIL, to="joão@exemplo.café"))

    # Sem forma ASCII possível: só um servidor com SMTPUTF8 entregaria
    assert (error.reason, error.permanent) == ("SMTPNotSupported", True)
    assert stub.messages == []
