from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, JsonValue, ValidationError

from notification_service.domain import InvalidTemplateDataError, UnknownTemplateError


@dataclass(frozen=True, slots=True)
class TemplateSpec:
    """Um e-mail: a pasta templates/<name>/ e o schema do data que ela consome"""

    name: str
    data_model: type[BaseModel]


class TemplateRegistry:
    """Catálogo genérico: um e-mail novo é um TemplateSpec a mais, sem mudar o caso de uso"""

    def __init__(self, specs: Iterable[TemplateSpec]) -> None:
        self._specs: dict[str, TemplateSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"Template registrado duas vezes: {spec.name}")
            self._specs[spec.name] = spec

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def parse(self, template: str, data: Mapping[str, JsonValue]) -> BaseModel:
        """Valida o data contra o schema do template; o loader só vê nomes registrados"""
        spec = self._specs.get(template)
        if spec is None:
            raise UnknownTemplateError(template, self.names)
        try:
            return spec.data_model.model_validate(data)
        except ValidationError as exc:
            raise InvalidTemplateDataError(_safe_errors(exc)) from None


def _safe_errors(exc: ValidationError) -> list[dict[str, Any]]:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return [{"type": error["type"], "loc": error["loc"], "msg": error["msg"]} for error in errors]
