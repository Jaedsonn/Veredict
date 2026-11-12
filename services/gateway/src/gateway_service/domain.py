from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Upstream:
    name: str
    base_url: str
    # Entra nas mensagens 502/503/504: "Serviço de {label} indisponível."
    label: str
