from functools import lru_cache

from veriditi_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "gateway"
    auth_url: str = "http://localhost:8001"
    health_timeout_s: float = 2.0

    @property
    def upstreams(self) -> dict[str, str]:
        """Serviços que o /health/ready agrega; notification e monitoring são internos"""
        return {"auth": self.auth_url}


@lru_cache
def get_settings() -> Settings:
    return Settings()
