"""Adaptador de hash de senhas com Argon2id (`argon2-cffi`) (RNF01)"""

import contextlib

from argon2 import PasswordHasher as Argon2Hasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    """Implementa `PasswordHasher` usando Argon2id (RNF01 / #7 / #9)

    Inclui um hash dummy pré-computado no momento da inicialização para que
    tentativas de login com e-mails inexistentes executem a mesma operação
    criptográfica Argon2id, mitigando ataques de enumeração por tempo (#9).
    """

    def __init__(
        self,
        *,
        time_cost: int = 2,
        memory_cost: int = 19456,
        parallelism: int = 1,
    ) -> None:
        self._hasher = Argon2Hasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,
        )
        self._dummy_hash: str = self._hasher.hash("dummy-password-for-constant-time-99")

    def hash(self, plain_password: str) -> str:
        return self._hasher.hash(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        try:
            return bool(self._hasher.verify(password_hash, plain_password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, plain_password: str) -> None:
        with contextlib.suppress(VerifyMismatchError, VerificationError, InvalidHashError):
            self._hasher.verify(self._dummy_hash, plain_password)
