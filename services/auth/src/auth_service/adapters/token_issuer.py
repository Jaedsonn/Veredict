"""Adaptador de emissão e hash de tokens de sessão com PyJWT (RS256) e CSPRNG (#9)."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt


class PyJwtTokenIssuer:
    """Emite Access Tokens JWT assinados com RS256 e Refresh Tokens opacos de 32 bytes (#9).

    Por que RS256: apenas o serviço `auth` detém a chave privada para assinar tokens;
    o API Gateway precisa apenas da chave pública para validá-los, reduzindo a
    superfície de ataque (princípio do menor privilégio — RNF01).
    """

    def __init__(
        self,
        *,
        private_key_pem: str,
        public_key_pem: str | None = None,
        issuer: str = "veriditi-auth",
        audience: str = "veriditi",
        access_ttl_seconds: int = 900,
        refresh_ttl_days: int = 7,
    ) -> None:
        self._private_key = private_key_pem
        self._public_key = public_key_pem
        self._issuer = issuer
        self._audience = audience
        self._access_ttl_seconds = access_ttl_seconds
        self._refresh_ttl_days = refresh_ttl_days

    @property
    def access_ttl_seconds(self) -> int:
        return self._access_ttl_seconds

    @property
    def refresh_ttl_days(self) -> int:
        return self._refresh_ttl_days

    def issue_access_token(
        self,
        *,
        user_id: int,
        email: str,
        now: datetime,
        session_id: uuid.UUID | None = None,
    ) -> str:
        exp = now + timedelta(seconds=self._access_ttl_seconds)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "email": email,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": str(uuid.uuid4()),
            "iss": self._issuer,
            "aud": self._audience,
        }
        if session_id is not None:
            payload["sid"] = str(session_id)
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def decode_access_token(self, token: str) -> dict[str, Any]:
        """Utilitário para inspeção/validação em testes usando a chave pública RS256."""
        if not self._public_key:
            raise RuntimeError("Chave pública JWT não configurada.")
        result: dict[str, Any] = jwt.decode(
            token,
            self._public_key,
            algorithms=["RS256"],
            issuer=self._issuer,
            audience=self._audience,
            options={"verify_iat": False, "verify_exp": False},
        )
        return result

    def generate_refresh_token(self) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        return raw_token, self.hash_refresh_token(raw_token)

    def hash_refresh_token(self, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
