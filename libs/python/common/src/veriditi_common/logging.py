"""Configuração de logging estruturado em JSON (ADR-012)."""

import logging
import sys
from typing import Any

import structlog


def configure_logging(service_name: str, *, level: int = logging.INFO) -> None:
    """Configura structlog para emitir eventos estruturados em JSON (ADR-012).

    Cada entrada inclui timestamp ISO-8601 em UTC, nível, nome do serviço,
    request_id (quando presente no contexto) e campos de domínio.
    """

    def add_service_name(
        _logger: Any, _method_name: str, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        event_dict.setdefault("service", service_name)
        return event_dict

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_service_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


get_logger = structlog.get_logger
