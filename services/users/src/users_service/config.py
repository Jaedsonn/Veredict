from functools import lru_cache

from veriditi_common.settings import ServiceSettings


class Settings(ServiceSettings):
    service_name: str = "users"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
