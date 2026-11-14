import importlib.util
import os
import stat
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from dotenv import dotenv_values

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "jwt_keys.py"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("jwt_keys_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp_path: Path, content: str = "A=1\nJWT_PRIVATE_KEY=\nJWT_PUBLIC_KEY=\n") -> Path:
    path = tmp_path / ".env"
    path.write_text(content)
    return path


def _keys(path: Path) -> dict[str, str]:
    values = dotenv_values(path)
    return {k: v for k, v in values.items() if k.startswith("JWT_") and v is not None}


def test_generates_pair_in_env_without_keys(script: ModuleType, tmp_path: Path) -> None:
    env = _env(tmp_path, "A=1\nB='x y'\n")

    assert script.main(["--env-file", str(env)]) == 0

    lines = env.read_text().splitlines()
    assert lines[:2] == ["A=1", "B='x y'"]
    assert lines[2].startswith("JWT_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----\\n")
    assert lines[3].startswith("JWT_PUBLIC_KEY='-----BEGIN PUBLIC KEY-----\\n")
    assert len(lines) == 4


def test_pair_is_coherent_and_dotenv_keeps_literal_newlines(
    script: ModuleType, tmp_path: Path
) -> None:
    env = _env(tmp_path)

    script.main(["--env-file", str(env)])

    keys = _keys(env)
    assert "\\n" in keys["JWT_PUBLIC_KEY"]
    assert "\n" not in keys["JWT_PUBLIC_KEY"]
    private = serialization.load_pem_private_key(
        keys["JWT_PRIVATE_KEY"].replace("\\n", "\n").encode(), password=None
    )
    public = serialization.load_pem_public_key(keys["JWT_PUBLIC_KEY"].replace("\\n", "\n").encode())
    assert isinstance(private, rsa.RSAPrivateKey)
    assert isinstance(public, rsa.RSAPublicKey)
    assert private.key_size == 2048
    signature = private.sign(b"msg", padding.PKCS1v15(), hashes.SHA256())
    public.verify(signature, b"msg", padding.PKCS1v15(), hashes.SHA256())


def test_second_run_is_idempotent(
    script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path)
    script.main(["--env-file", str(env)])
    before = env.read_bytes()

    assert script.main(["--env-file", str(env)]) == 0

    assert env.read_bytes() == before
    assert "já existem" in capsys.readouterr().out


def test_force_replaces_pair(script: ModuleType, tmp_path: Path) -> None:
    env = _env(tmp_path)
    script.main(["--env-file", str(env)])
    before = _keys(env)

    assert script.main(["--env-file", str(env), "--force"]) == 0

    after = _keys(env)
    assert after["JWT_PRIVATE_KEY"] != before["JWT_PRIVATE_KEY"]
    assert after["JWT_PUBLIC_KEY"] != before["JWT_PUBLIC_KEY"]


def test_only_one_key_filled_fails(script: ModuleType, tmp_path: Path) -> None:
    env = _env(tmp_path, "JWT_PRIVATE_KEY='abc'\nJWT_PUBLIC_KEY=\n")
    before = env.read_bytes()

    assert script.main(["--env-file", str(env)]) == 1

    assert env.read_bytes() == before


def test_duplicate_lines_become_one(script: ModuleType, tmp_path: Path) -> None:
    env = _env(
        tmp_path, "JWT_PUBLIC_KEY=\nA=1\nJWT_PUBLIC_KEY=\nJWT_PRIVATE_KEY=\nJWT_PRIVATE_KEY=\n"
    )

    script.main(["--env-file", str(env)])

    lines = env.read_text().splitlines()
    assert sum(line.startswith("JWT_PUBLIC_KEY=") for line in lines) == 1
    assert sum(line.startswith("JWT_PRIVATE_KEY=") for line in lines) == 1
    assert lines[0].startswith("JWT_PUBLIC_KEY='")
    assert lines[1] == "A=1"


def test_other_lines_preserved_byte_for_byte(script: ModuleType, tmp_path: Path) -> None:
    others = b'# coment\xc3\xa1rio\r\nA=1\r\n\r\nSMTP_FROM="Veriditi <x@y>"\r\nSEM_FIM=2'
    env = tmp_path / ".env"
    env.write_bytes(others.replace(b"A=1\r\n", b"A=1\r\nJWT_PRIVATE_KEY=\r\n"))

    script.main(["--env-file", str(env)])

    data = env.read_bytes()
    kept = b"".join(line for line in data.splitlines(keepends=True) if not line.startswith(b"JWT_"))
    assert kept == others + b"\n"


def test_never_prints_the_key(
    script: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path)

    script.main(["--env-file", str(env)])

    out = capsys.readouterr()
    assert "BEGIN" not in out.out + out.err
    assert "Par RS256 gravado" in out.out


def test_keeps_file_mode(script: ModuleType, tmp_path: Path) -> None:
    env = _env(tmp_path)
    os.chmod(env, 0o600)

    script.main(["--env-file", str(env)])

    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == [".env"]


def test_missing_env_file_fails(script: ModuleType, tmp_path: Path) -> None:
    assert script.main(["--env-file", str(tmp_path / "nao-existe")]) == 1
