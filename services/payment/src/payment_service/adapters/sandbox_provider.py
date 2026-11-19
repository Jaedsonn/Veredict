"""Provedor PIX sandbox: cobrança local no formato BR Code, sem dinheiro de verdade

Implementa a mesma porta do provedor real (#23). O código copia-e-cola segue o padrão
EMV do BR Code do Banco Central, para a tela e o QR Code ficarem idênticos aos reais.
"""

import unicodedata
from typing import Final

from payment_service.domain import PixCharge, PixChargeRequest

_GUI: Final = "br.gov.bcb.pix"


def _field(tag: str, value: str) -> str:
    if len(value) > 99:
        raise ValueError(f"Campo {tag} do BR Code passa de 99 caracteres")
    return f"{tag}{len(value):02d}{value}"


def _ascii_upper(value: str, limit: int) -> str:
    """O BR Code aceita só ASCII; nome e cidade vão sem acento e em maiúsculas"""
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return plain.upper()[:limit]


def crc16_ccitt(payload: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, valor inicial 0xFFFF), como pede o BR Code"""
    crc = 0xFFFF
    for byte in payload.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def build_br_code(
    *, pix_key: str, amount_cents: int, merchant_name: str, merchant_city: str, txid: str
) -> str:
    account = _field("00", _GUI) + _field("01", pix_key)
    payload = (
        _field("00", "01")
        + _field("26", account)
        + _field("52", "0000")
        + _field("53", "986")
        + _field("54", f"{amount_cents // 100}.{amount_cents % 100:02d}")
        + _field("58", "BR")
        + _field("59", _ascii_upper(merchant_name, 25))
        + _field("60", _ascii_upper(merchant_city, 15))
        + _field("62", _field("05", txid[:25]))
        + "6304"
    )
    return payload + crc16_ccitt(payload)


class SandboxPixProvider:
    name = "sandbox"

    def __init__(self, *, pix_key: str, merchant_name: str, merchant_city: str) -> None:
        self._pix_key = pix_key
        self._merchant_name = merchant_name
        self._merchant_city = merchant_city

    async def create_pix_charge(self, request: PixChargeRequest) -> PixCharge:
        # txid alfanumérico de até 25 caracteres, derivado do pedido
        txid = request.order_id.hex[:25].upper()
        copy_paste = build_br_code(
            pix_key=self._pix_key,
            amount_cents=request.amount_cents,
            merchant_name=self._merchant_name,
            merchant_city=self._merchant_city,
            txid=txid,
        )
        return PixCharge(
            provider_payment_id=f"sandbox-{request.order_id.hex}", copy_paste=copy_paste
        )
