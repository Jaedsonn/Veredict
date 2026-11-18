"""Value objects Cpf e Oab (#60): os vetores de CPF são os mesmos do vitest da web"""

import json
from pathlib import Path
from typing import Any

import pytest

from auth_service.domain.cpf import Cpf
from auth_service.domain.errors import InvalidCpfError, InvalidOabError
from auth_service.domain.oab import (
    OAB_NOT_ALLOWED_MESSAGE,
    OAB_REQUIRED_MESSAGE,
    Oab,
    check_oab_matches_type,
)
from auth_service.models import OabKind, OabUf, UserType

# Um arquivo só para Python e TypeScript, para as duas validações não divergirem
VECTORS_FILE = Path(__file__).resolve().parents[3] / "apps/web/src/lib/validation/cpf-vectors.json"
VECTORS: dict[str, Any] = json.loads(VECTORS_FILE.read_text())


@pytest.mark.parametrize("vector", VECTORS["valid"], ids=lambda v: v["input"])
def test_valid_cpf_is_normalized_and_masked(vector: dict[str, str]) -> None:
    cpf = Cpf.parse(vector["input"])

    assert cpf.digits == vector["digits"]
    assert cpf.masked == vector["masked"]


@pytest.mark.parametrize("raw", VECTORS["invalid"])
def test_invalid_cpf_is_rejected_without_echoing_the_value(raw: str) -> None:
    with pytest.raises(InvalidCpfError) as exc:
        Cpf.parse(raw)

    assert exc.value.message == "CPF inválido."
    assert exc.value.field == "cpf"
    if raw.strip():
        assert raw.strip() not in str(exc.value)


@pytest.mark.parametrize("raw", [None, 52998224725, ["52998224725"]])
def test_non_string_cpf_is_rejected(raw: object) -> None:
    with pytest.raises(InvalidCpfError):
        Cpf.parse(raw)


@pytest.mark.parametrize("digit", "0123456789")
def test_repeated_digits_are_rejected(digit: str) -> None:
    with pytest.raises(InvalidCpfError):
        Cpf.parse(digit * 11)


def test_repr_and_str_never_show_the_full_cpf() -> None:
    cpf = Cpf.parse("529.982.247-25")

    assert "52998224725" not in repr(cpf)
    assert "529" not in str(cpf)
    assert str(cpf) == "***.982.247-**"


def test_cpf_constructor_also_validates() -> None:
    with pytest.raises(InvalidCpfError):
        Cpf("52998224724")


@pytest.mark.parametrize(
    ("number", "uf", "kind", "expected"),
    [
        ("123456", "BA", "principal", Oab("123456", OabUf.BA, OabKind.PRINCIPAL)),
        (" 1 ", "sp", "suplementar", Oab("1", OabUf.SP, OabKind.SUPLEMENTAR)),
        ("001234", "DF", "TRANSITORIA", Oab("1234", OabUf.DF, OabKind.TRANSITORIA)),
    ],
)
def test_oab_is_normalized(number: str, uf: str, kind: str, expected: Oab) -> None:
    assert Oab.parse(number=number, uf=uf, kind=kind) == expected


@pytest.mark.parametrize("number", ["", "0", "000", "1234567", "12a45", "12.345", None, 123])
def test_oab_number_must_have_1_to_6_digits(number: object) -> None:
    with pytest.raises(InvalidOabError) as exc:
        Oab.parse(number=number, uf="BA", kind="principal")

    assert exc.value.field == "oab.number"


@pytest.mark.parametrize("uf", ["", "XX", "Bahia", None])
def test_oab_uf_must_be_one_of_27(uf: object) -> None:
    with pytest.raises(InvalidOabError) as exc:
        Oab.parse(number="123", uf=uf, kind="principal")

    assert exc.value.field == "oab.uf"


@pytest.mark.parametrize("kind", ["", "estagiario", None])
def test_oab_kind_must_be_known(kind: object) -> None:
    with pytest.raises(InvalidOabError) as exc:
        Oab.parse(number="123", uf="BA", kind=kind)

    assert exc.value.field == "oab.kind"


def test_there_are_27_seccionais() -> None:
    assert len(OabUf) == 27


def test_lawyer_requires_oab_and_common_rejects_it() -> None:
    oab = Oab("123", OabUf.BA, OabKind.PRINCIPAL)
    check_oab_matches_type(UserType.LAWYER, oab)
    check_oab_matches_type(UserType.COMMON, None)

    with pytest.raises(InvalidOabError) as missing:
        check_oab_matches_type(UserType.LAWYER, None)
    with pytest.raises(InvalidOabError) as extra:
        check_oab_matches_type(UserType.COMMON, oab)

    assert (missing.value.field, missing.value.message) == ("oab", OAB_REQUIRED_MESSAGE)
    assert (extra.value.field, extra.value.message) == ("oab", OAB_NOT_ALLOWED_MESSAGE)
