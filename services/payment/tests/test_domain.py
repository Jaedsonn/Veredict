import uuid

import pytest

from payment_service.adapters.qr import SegnoQrRenderer
from payment_service.adapters.sandbox_provider import SandboxPixProvider, build_br_code, crc16_ccitt
from payment_service.domain import (
    Billing,
    PixChargeRequest,
    cep_digits,
    cpf_digits,
    mask_cpf,
    phone_digits,
)


@pytest.mark.parametrize("raw", ["529.982.247-25", "52998224725", " 111.444.777-35 "])
def test_cpf_valid(raw: str) -> None:
    digits = cpf_digits(raw)
    assert digits is not None and len(digits) == 11


@pytest.mark.parametrize(
    "raw", ["529.982.247-24", "111.111.111-11", "5299822472", "529-982-247.25", "abc", ""]
)
def test_cpf_invalid(raw: str) -> None:
    assert cpf_digits(raw) is None


def test_mask_cpf_matches_auth_format() -> None:
    assert mask_cpf("52998224725") == "***.982.247-**"


@pytest.mark.parametrize(("raw", "expected"), [("40110-100", "40110100"), ("40110100", "40110100")])
def test_cep_valid(raw: str, expected: str) -> None:
    assert cep_digits(raw) == expected


@pytest.mark.parametrize("raw", ["4011-0100", "4011010", "401101000", "abcde-fgh"])
def test_cep_invalid(raw: str) -> None:
    assert cep_digits(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(71) 99876-5432", "71998765432"),
        ("71 3333-4444", "7133334444"),
        ("+55 71 99876-5432", "71998765432"),
    ],
)
def test_phone_valid(raw: str, expected: str) -> None:
    assert phone_digits(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "998765432", "(01) 99876-5432", "71 99876-543x", "123456789012"]
)
def test_phone_invalid(raw: str) -> None:
    assert phone_digits(raw) is None


def test_crc16_ccitt_known_vector() -> None:
    # Valor de referência do CRC-16/CCITT-FALSE
    assert crc16_ccitt("123456789") == "29B1"


def test_br_code_layout_and_crc() -> None:
    code = build_br_code(
        pix_key="pagamentos@veriditi.app",
        amount_cents=2500,
        merchant_name="Veriditi Sandbox",
        merchant_city="São Paulo",
        txid="ABC123",
    )
    assert code.startswith("000201")
    assert "0014br.gov.bcb.pix0123pagamentos@veriditi.app" in code
    assert "540525.00" in code
    assert "5916VERIDITI SANDBOX" in code
    assert "6009SAO PAULO" in code
    assert "62100506ABC123" in code
    assert code[-8:-4] == "6304"
    assert crc16_ccitt(code[:-4]) == code[-4:]


def test_br_code_rejects_oversized_field() -> None:
    with pytest.raises(ValueError):
        build_br_code(
            pix_key="x" * 100, amount_cents=1, merchant_name="a", merchant_city="b", txid="c"
        )


async def test_sandbox_provider_charge_is_tied_to_the_order() -> None:
    order_id = uuid.UUID("0c3b9b6e-6c43-4a49-9d3f-1d0f1b2e3c4d")
    provider = SandboxPixProvider(pix_key="k@v.app", merchant_name="V", merchant_city="S")
    billing = Billing(
        name="Ana", email="a@x.com", phone="71998765432", cpf="52998224725", cep="40110100",
        street="Rua", number="1", complement=None, district="Centro", city="Salvador", state="BA",
    )  # fmt: skip
    charge = await provider.create_pix_charge(
        PixChargeRequest(order_id=order_id, amount_cents=8000, description="x", payer=billing)
    )
    assert charge.provider_payment_id == f"sandbox-{order_id.hex}"
    assert order_id.hex[:25].upper() in charge.copy_paste
    assert "540580.00" in charge.copy_paste
    assert "52998224725" not in repr(billing)


def test_qr_renderer_outputs_svg() -> None:
    svg = SegnoQrRenderer().svg("000201010212")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "<script" not in svg
