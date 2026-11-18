"""Dados válidos para os testes do auth: CPFs gerados, corpo do cadastro e colunas de users"""

import hashlib
from typing import Any

from auth_service.models import OabKind, OabUf, UserType


def make_cpf(seed: int, *, masked: bool = True) -> str:
    """CPF válido e distinto por seed (1 a 10⁸), com os dígitos verificadores calculados"""
    base = f"{seed:09d}"
    if len(set(base)) == 1:
        base = f"{seed + 1:09d}"
    digits = base
    for _ in range(2):
        weights = range(len(digits) + 1, 1, -1)
        total = sum(int(d) * w for d, w in zip(digits, weights, strict=True))
        digits += str(total * 10 % 11 % 10)
    if not masked:
        return digits
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def user_columns(
    email: str,
    *,
    name: str = "Usuária",
    user_type: UserType = UserType.COMMON,
    cpf_seed: int | None = None,
    oab: tuple[str, OabUf, OabKind] | None = None,
) -> dict[str, Any]:
    """Colunas obrigatórias de `User` para inserir direto pelo ORM, sem passar pela cifra"""
    seed = cpf_seed if cpf_seed is not None else int(hashlib.sha256(email.encode()).hexdigest(), 16)
    number, uf, kind = oab if oab else (None, None, None)
    return {
        "email": email,
        "name": name,
        "password_hash": "$argon2id$stub",
        "user_type": user_type,
        # 40 bytes como a cifra real; o conteúdo não importa sem o protector
        "cpf_enc": b"\x01" + hashlib.sha256(f"enc:{seed}".encode()).digest() + b"\x00" * 7,
        "cpf_hmac": hashlib.sha256(str(seed).encode()).hexdigest(),
        "oab_number": number,
        "oab_uf": uf,
        "oab_kind": kind,
    }


def cpf_for_email(email: str) -> str:
    """CPF válido e estável por e-mail, para cada conta dos testes ter o seu"""
    return make_cpf(int(hashlib.sha256(email.encode()).hexdigest(), 16) % 999_999_998 + 1)


def common_identity(email: str) -> dict[str, str]:
    """Campos que o cadastro passou a exigir (#60), para os testes que não tratam deles"""
    return {"user_type": "common", "cpf": cpf_for_email(email)}
