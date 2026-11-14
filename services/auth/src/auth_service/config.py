from functools import lru_cache

from veriditi_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "auth"
    # Portas do make dev; o compose fixa http://monitoring:8000 e http://notification:8000
    monitoring_url: str = "http://localhost:8003"
    notification_url: str = "http://localhost:8002"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
