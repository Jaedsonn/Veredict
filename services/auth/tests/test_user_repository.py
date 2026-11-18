"""SqlAlchemyUserRepository no SQLite: tipo, CPF, OAB e o mapeamento de duplicidade (#60)"""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from auth_service.adapters.repositories import SqlAlchemyUserRepository
from auth_service.domain.errors import (
    CpfAlreadyRegisteredError,
    EmailAlreadyRegisteredError,
    OabAlreadyRegisteredError,
)
from auth_service.domain.oab import Oab
from auth_service.models import OabKind, OabUf, UserType
from veriditi_common.db import Database

NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)
OAB = Oab(number="12345", uf=OabUf.BA, kind=OabKind.PRINCIPAL)


@pytest.fixture
async def repo(db: Database) -> AsyncIterator[SqlAlchemyUserRepository]:
    async with db.session_factory() as session:
        yield SqlAlchemyUserRepository(session)


async def _create(
    repo: SqlAlchemyUserRepository,
    email: str,
    cpf_hmac: str,
    *,
    user_type: UserType = UserType.COMMON,
    oab: Oab | None = None,
) -> object:
    return await repo.create(
        email=email,
        name="Nome",
        password_hash="$argon2id$stub",
        user_type=user_type,
        cpf_enc=b"\x01" + b"\x00" * 39,
        cpf_hmac=cpf_hmac,
        oab=oab,
        now=NOW,
    )


def _hmac(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


async def test_create_round_trips_type_cpf_and_oab(repo: SqlAlchemyUserRepository) -> None:
    created = await _create(repo, "adv@example.com", _hmac("a"), user_type=UserType.LAWYER, oab=OAB)

    loaded = await repo.get_by_email("adv@example.com")

    assert created == loaded
    assert loaded is not None
    assert loaded.user_type is UserType.LAWYER
    assert loaded.oab == OAB
    assert loaded.cpf_enc == b"\x01" + b"\x00" * 39
    assert "cpf_enc" not in repr(loaded)


async def test_common_user_has_no_oab(repo: SqlAlchemyUserRepository) -> None:
    created = await _create(repo, "c@example.com", _hmac("c"))

    assert created.oab is None  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("second", "error"),
    [
        ({"email": "a@example.com", "cpf_hmac": _hmac("2")}, EmailAlreadyRegisteredError),
        ({"email": "b@example.com", "cpf_hmac": _hmac("1")}, CpfAlreadyRegisteredError),
        ({"email": "b@example.com", "cpf_hmac": _hmac("2")}, OabAlreadyRegisteredError),
    ],
)
async def test_duplicates_map_to_one_domain_error_per_field(
    repo: SqlAlchemyUserRepository, second: dict[str, str], error: type[Exception]
) -> None:
    lawyer = UserType.LAWYER
    await _create(repo, "a@example.com", _hmac("1"), user_type=lawyer, oab=OAB)

    with pytest.raises(error) as exc:
        await _create(repo, second["email"], second["cpf_hmac"], user_type=lawyer, oab=OAB)

    # Sem a cadeia: a mensagem do driver repete o valor duplicado
    assert exc.value.__cause__ is None
    assert second["cpf_hmac"] not in str(exc.value)


async def test_unmapped_integrity_error_is_not_disguised(repo: SqlAlchemyUserRepository) -> None:
    # Advogado sem OAB viola o CHECK, não um UNIQUE: não vira 409
    with pytest.raises(IntegrityError):
        await _create(repo, "x@example.com", _hmac("x"), user_type=UserType.LAWYER)
