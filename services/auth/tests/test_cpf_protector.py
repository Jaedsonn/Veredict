"""Cifra AES-GCM e índice HMAC do CPF (#60, ADR-024)"""

import base64
import hashlib
import hmac
import os

import pytest

from auth_service.adapters.cpf_protector import AesGcmCpfProtector, CpfDecryptionError
from auth_service.config import Settings
from auth_service.domain.cpf import Cpf
from auth_service.main import create_app
from auth_service.ports import CpfProtector
from veriditi_common.db import Database

CPF = Cpf.parse("529.982.247-25")
ENC_KEY = bytes(range(32))
HMAC_KEY = bytes(range(32, 64))


@pytest.fixture
def protector() -> AesGcmCpfProtector:
    return AesGcmCpfProtector(encryption_key=ENC_KEY, hmac_key=HMAC_KEY)


def test_implements_the_port(protector: AesGcmCpfProtector) -> None:
    assert isinstance(protector, CpfProtector)


def test_round_trip(protector: AesGcmCpfProtector) -> None:
    assert protector.decrypt(protector.encrypt(CPF)) == CPF


def test_blob_has_version_nonce_cipher_and_tag_without_plaintext(
    protector: AesGcmCpfProtector,
) -> None:
    blob = protector.encrypt(CPF)

    assert len(blob) == 1 + 12 + 11 + 16
    assert blob[0] == 1
    assert CPF.digits.encode() not in blob


def test_random_nonce_gives_different_blobs(protector: AesGcmCpfProtector) -> None:
    first, second = protector.encrypt(CPF), protector.encrypt(CPF)

    assert first != second
    assert first[1:13] != second[1:13]


@pytest.mark.parametrize("position", [0, 1, 13, -1])
def test_tampered_blob_fails(protector: AesGcmCpfProtector, position: int) -> None:
    blob = bytearray(protector.encrypt(CPF))
    blob[position] ^= 0x01

    with pytest.raises(CpfDecryptionError):
        protector.decrypt(bytes(blob))


@pytest.mark.parametrize("blob", [b"", b"\x01", b"\x01" + b"\x00" * 20])
def test_truncated_blob_fails(protector: AesGcmCpfProtector, blob: bytes) -> None:
    with pytest.raises(CpfDecryptionError):
        protector.decrypt(blob)


def test_wrong_key_fails(protector: AesGcmCpfProtector) -> None:
    other = AesGcmCpfProtector(encryption_key=os.urandom(32), hmac_key=HMAC_KEY)

    with pytest.raises(CpfDecryptionError):
        other.decrypt(protector.encrypt(CPF))


def test_decryption_error_does_not_carry_data(protector: AesGcmCpfProtector) -> None:
    other = AesGcmCpfProtector(encryption_key=os.urandom(32), hmac_key=HMAC_KEY)
    blob = protector.encrypt(CPF)

    with pytest.raises(CpfDecryptionError) as exc:
        other.decrypt(blob)

    assert blob.hex() not in str(exc.value)
    assert exc.value.__cause__ is None


def test_blind_index_is_deterministic_hmac_sha256(protector: AesGcmCpfProtector) -> None:
    expected = hmac.new(HMAC_KEY, CPF.digits.encode(), hashlib.sha256).hexdigest()

    assert protector.blind_index(CPF) == expected
    assert protector.blind_index(Cpf.parse("52998224725")) == expected
    assert protector.blind_index(Cpf.parse("111.444.777-35")) != expected


def test_blind_index_depends_on_the_key() -> None:
    a = AesGcmCpfProtector(encryption_key=ENC_KEY, hmac_key=HMAC_KEY)
    b = AesGcmCpfProtector(encryption_key=ENC_KEY, hmac_key=os.urandom(32))

    assert a.blind_index(CPF) != b.blind_index(CPF)


@pytest.mark.parametrize(
    ("enc", "mac", "message"),
    [
        (b"\x00" * 16, HMAC_KEY, "32 bytes"),
        (ENC_KEY, b"\x00" * 31, "32 bytes"),
        (ENC_KEY, ENC_KEY, "diferentes"),
    ],
)
def test_constructor_rejects_bad_keys(enc: bytes, mac: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AesGcmCpfProtector(encryption_key=enc, hmac_key=mac)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"cpf_encryption_key": None}, "CPF_ENCRYPTION_KEY não definido"),
        ({"cpf_hmac_key": None}, "CPF_HMAC_KEY não definido"),
        ({"cpf_encryption_key": "não é base64!"}, "CPF_ENCRYPTION_KEY precisa ser base64"),
        ({"cpf_hmac_key": _b64(b"\x01" * 16)}, "CPF_HMAC_KEY precisa ser base64 de 32 bytes"),
        ({"cpf_hmac_key": _b64(ENC_KEY)}, "precisam ser diferentes"),
    ],
)
def test_create_app_fails_fast_on_cpf_keys(
    settings: Settings, db: Database, update: dict[str, str | None], message: str
) -> None:
    values = {"cpf_encryption_key": _b64(ENC_KEY), "cpf_hmac_key": _b64(HMAC_KEY), **update}
    broken = Settings.model_validate({**settings.model_dump(), **values})

    with pytest.raises(RuntimeError, match=message):
        create_app(settings=broken, db=db)


def test_empty_cpf_key_counts_as_missing(settings: Settings) -> None:
    broken = Settings.model_validate({**settings.model_dump(), "cpf_hmac_key": "  "})

    with pytest.raises(RuntimeError, match="CPF_HMAC_KEY não definido"):
        broken.resolved_cpf_keys()


async def test_app_exposes_the_protector_built_from_settings(
    settings: Settings, db: Database
) -> None:
    app = create_app(settings=settings, db=db)

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.cpf_protector, AesGcmCpfProtector)
