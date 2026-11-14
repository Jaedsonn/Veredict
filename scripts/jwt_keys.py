"""Gera o par RS256 de dev no .env: o auth assina com a privada e o gateway valida com a pública"""

import argparse
import os
import re
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
_LINE: Final = re.compile(rb"(JWT_PRIVATE_KEY|JWT_PUBLIC_KEY)=(.*?)\r?\n?")


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


def _rewrite(lines: list[bytes], pair: dict[str, str]) -> bytes:
    """Troca a 1ª ocorrência de cada chave, remove as duplicadas e acrescenta as que faltam"""
    out: list[bytes] = []
    written: set[str] = set()
    for line in lines:
        match = _LINE.fullmatch(line)
        if match is None:
            out.append(line)
            continue
        name = match.group(1).decode()
        if name not in written:
            ending = b"\r\n" if line.endswith(b"\r\n") else b"\n"
            out.append(f"{name}={pair[name]}".encode() + ending)
            written.add(name)
    if out and not out[-1].endswith(b"\n"):
        out[-1] += b"\n"
    missing = [name for name in (PRIVATE, PUBLIC) if name not in written]
    out.extend(f"{name}={pair[name]}\n".encode() for name in missing)
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
    parser = argparse.ArgumentParser(description="Gera o par RS256 de dev no .env")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--force", action="store_true", help="troca um par já existente")
    args = parser.parse_args(argv)
    env_file: Path = args.env_file

    if not env_file.is_file():
        print(f"{env_file} não existe: copie o .env.example ou rode make install", file=sys.stderr)
        return 1
    lines = env_file.read_bytes().splitlines(keepends=True)
    filled = _filled(lines)
    if not args.force and filled == {PRIVATE, PUBLIC}:
        print(f"{PRIVATE} e {PUBLIC} já existem em {env_file}; use force=1 para trocar o par")
        return 0
    if not args.force and filled:
        print(f"Par incompleto em {env_file}; use force=1 para gerar outro", file=sys.stderr)
        return 1

    _atomic_write(env_file, _rewrite(lines, generate_pair()))
    # Nunca imprime a chave
    print(f"Par RS256 gravado em {env_file} ({PRIVATE} e {PUBLIC}); reinicie auth e gateway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
