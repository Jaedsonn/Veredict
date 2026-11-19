"""Configurações do serviço de Pagamento"""

from functools import lru_cache
from typing import Literal

from pydantic import Field

from veriditi_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "payment"
    db_user: str = "payment_svc"

    # Porta do `make dev`; no compose é http://monitoring:8000
    monitoring_url: str = "http://localhost:8003"

    # Sem credenciais de provedor na Sprint 1, só o sandbox existe (o real entra no #23)
    payment_provider: Literal["sandbox"] = "sandbox"
    # Validade da cobrança PIX (#22)
    order_ttl_minutes: int = Field(default=30, ge=1, le=1440)

    # Dados do recebedor no BR Code do sandbox
    pix_key: str = Field(default="pagamentos@veriditi.app", min_length=1, max_length=77)
    pix_merchant_name: str = Field(default="VERIDITI SANDBOX", min_length=1, max_length=25)
    pix_merchant_city: str = Field(default="SALVADOR", min_length=1, max_length=15)

    @property
    def sandbox(self) -> bool:
        return self.payment_provider == "sandbox"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
