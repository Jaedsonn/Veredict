"""Gera no .env o par RS256 de dev (auth assina, gateway valida) e as chaves do CPF (ADR-024)"""

import argparse
import base64
import os
import re
import secrets
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

PRIVATE: Final = "JWT_PRIVATE_KEY"
PUBLIC: Final = "JWT_PUBLIC_KEY"
CPF_ENCRYPTION: Final = "CPF_ENCRYPTION_KEY"
CPF_HMAC: Final = "CPF_HMAC_KEY"
CPF_KEYS: Final = (CPF_ENCRYPTION, CPF_HMAC)
_MANAGED: Final = (PRIVATE, PUBLIC, *CPF_KEYS)
_LINE: Final = re.compile(rb"(" + b"|".join(n.encode() for n in _MANAGED) + rb")=(.*?)\r?\n?")


def _one_line(pem: bytes) -> str:
    """Aspas simples e \\n literal: o compose e o python-dotenv não processam escape nelas"""
    return "'" + pem.decode().strip().replace("\n", "\\n") + "'"


def generate_pair() -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return {PRIVATE: _one_line(private), PUBLIC: _one_line(public)}


def generate_cpf_key() -> str:
    """32 bytes aleatórios em base64, o formato que o auth exige (ADR-024)"""
    return base64.b64encode(secrets.token_bytes(32)).decode()


def _unquote(value: bytes) -> bytes:
    if len(value) >= 2 and value[:1] == value[-1:] and value[:1] in (b"'", b'"'):
        return value[1:-1]
    return value


def _filled(lines: list[bytes]) -> set[str]:
    """Última ocorrência vence, como no compose e no env_get do Makefile"""
    values: dict[str, bytes] = {}
    for line in lines:
        if match := _LINE.fullmatch(line):
            values[match.group(1).decode()] = _unquote(match.group(2).strip())
    return {name for name, value in values.items() if value}


def _rewrite(lines: list[bytes], values: dict[str, str]) -> bytes:
    """Troca a 1ª ocorrência de cada chave nova, remove as duplicadas e acrescenta as que faltam

    Chaves fora de `values` ficam como estão
    """
    out: list[bytes] = []
    written: set[str] = set()
    for line in lines:
        match = _LINE.fullmatch(line)
        name = match.group(1).decode() if match else None
        if name is None or name not in values:
            out.append(line)
            continue
        if name not in written:
            ending = b"\r\n" if line.endswith(b"\r\n") else b"\n"
            out.append(f"{name}={values[name]}".encode() + ending)
            written.add(name)
    if out and not out[-1].endswith(b"\n"):
        out[-1] += b"\n"
    missing = [name for name in _MANAGED if name in values and name not in written]
    out.extend(f"{name}={values[name]}\n".encode() for name in missing)
    return b"".join(out)


def _atomic_write(path: Path, data: bytes) -> None:
    """tmp no mesmo diretório + os.replace, mantendo o modo do arquivo original"""
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera o par RS256 e as chaves do CPF no .env")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--force", action="store_true", help="troca o par RS256; as chaves do CPF nunca mudam"
    )
    args = parser.parse_args(argv)
    env_file: Path = args.env_file

    if not env_file.is_file():
        print(f"{env_file} não existe: copie o .env.example ou rode make install", file=sys.stderr)
        return 1
    lines = env_file.read_bytes().splitlines(keepends=True)
    filled = _filled(lines)
    jwt_filled = filled & {PRIVATE, PUBLIC}
    if not args.force and jwt_filled and jwt_filled != {PRIVATE, PUBLIC}:
        print(f"Par incompleto em {env_file}; use force=1 para gerar outro", file=sys.stderr)
        return 1

    values: dict[str, str] = {}
    if args.force or not jwt_filled:
        values.update(generate_pair())
    # force=1 não troca as chaves do CPF: a de cifra perderia os CPFs gravados e a do HMAC
    # quebraria o UNIQUE (ADR-024); a troca é uma migração de dados (#62)
    values.update({name: generate_cpf_key() for name in CPF_KEYS if name not in filled})
    if not values:
        print(f"As chaves já existem em {env_file}; use force=1 para trocar o par RS256")
        return 0

    _atomic_write(env_file, _rewrite(lines, values))
    # Nunca imprime as chaves
    if PRIVATE in values:
        print(f"Par RS256 gravado em {env_file} ({PRIVATE} e {PUBLIC}); reinicie auth e gateway")
    if cpf := [name for name in CPF_KEYS if name in values]:
        print(f"Chaves do CPF gravadas em {env_file} ({' e '.join(cpf)}); reinicie o auth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
