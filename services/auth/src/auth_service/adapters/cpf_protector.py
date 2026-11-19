"""Cifra AES-256-GCM e índice HMAC-SHA256 do CPF (ADR-024)"""

import hashlib
import hmac
import os
from typing import Final

__all__ = ["KEY_BYTES", "AesGcmCpfProtector", "CpfDecryptionError"]

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from auth_service.domain.cpf import Cpf
from auth_service.domain.errors import CpfDecryptionError, InvalidCpfError

KEY_BYTES: Final = 32
_VERSION: Final = b"\x01"
_NONCE_BYTES: Final = 12
# Amarra a cifra à coluna e à versão; o id do usuário ainda não existe no INSERT
_AAD: Final = b"veriditi:users.cpf_enc:v1"


class AesGcmCpfProtector:
    """`versão || nonce || cifra || tag` em `cpf_enc` e HMAC hex em `cpf_hmac`"""

    def __init__(self, *, encryption_key: bytes, hmac_key: bytes) -> None:
        if len(encryption_key) != KEY_BYTES or len(hmac_key) != KEY_BYTES:
            raise ValueError(f"As chaves do CPF precisam ter {KEY_BYTES} bytes")
        # Uma chave só faria o vazamento de uma função comprometer a outra
        if hmac.compare_digest(encryption_key, hmac_key):
            raise ValueError("As chaves de cifra e de HMAC do CPF precisam ser diferentes")
        self._aead = AESGCM(encryption_key)
        self._hmac_key = hmac_key

    def encrypt(self, cpf: Cpf) -> bytes:
        nonce = os.urandom(_NONCE_BYTES)
        return _VERSION + nonce + self._aead.encrypt(nonce, cpf.digits.encode(), _AAD)

    def decrypt(self, blob: bytes) -> Cpf:
        version, nonce, sealed = blob[:1], blob[1 : 1 + _NONCE_BYTES], blob[1 + _NONCE_BYTES :]
        if version != _VERSION or len(nonce) != _NONCE_BYTES:
            raise CpfDecryptionError()
        try:
            return Cpf(self._aead.decrypt(nonce, sealed, _AAD).decode())
        except (InvalidTag, InvalidCpfError, UnicodeDecodeError):
            raise CpfDecryptionError() from None

    def blind_index(self, cpf: Cpf) -> str:
        return hmac.new(self._hmac_key, cpf.digits.encode(), hashlib.sha256).hexdigest()
