"""Logs JSON de structlog, uvicorn e libs de terceiros no mesmo formato (ADR-012)"""

import logging
import sys
from collections.abc import Mapping
from typing import Any, Final, TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

# Basta a chave conter uma destas partes (minúsculas, "-" igual a "_")
SENSITIVE_KEY_PARTS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "cookie",
        "private_key",
        "api_key",
    }
)
# code e *_code são sensíveis; o código de erro de negócio vai em error_code
_NOT_SENSITIVE: Final = frozenset({"status_code", "error_code"})
REDACTED: Final = "[redacted]"

_HANDLER_NAME: Final = "veriditi"
# O ExceptionRenderer e o ProcessorFormatter precisam desses valores intactos
_UNTOUCHED_KEYS: Final = frozenset({"exc_info", "stack_info", "_record", "_from_structlog"})


def is_sensitive_key(key: object) -> bool:
    """Por parte do nome, para pegar db_password, jwt_private_key, verification_code e afins"""
    if isinstance(key, bytes):
        key = key.decode("latin-1")
    if not isinstance(key, str):
        return False
    normalized = key.lower().replace("-", "_")
    if normalized in _NOT_SENSITIVE:
        return False
    if normalized == "code" or normalized.endswith("_code"):
        return True
    if "otp" in normalized.split("_"):
        return True
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _is_sensitive_pair(value: list[Any] | tuple[Any, ...]) -> bool:
    """Par (nome, valor) como os headers crus do ASGI e do httpx"""
    return (
        len(value) == 2
        and all(isinstance(item, str | bytes) for item in value)
        and is_sensitive_key(value[0])
    )


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive_key(k) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        sensitive = _is_sensitive_pair(value)
        items = [value[0], REDACTED] if sensitive else [_redact(v) for v in value]
        return tuple(items) if isinstance(value, tuple) else items
    return value


def redact_sensitive(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Troca por [redacted] o valor de chaves sensíveis, inclusive aninhadas"""
    for key, value in event_dict.items():
        if key in _UNTOUCHED_KEYS:
            continue
        event_dict[key] = REDACTED if is_sensitive_key(key) else _redact(value)
    return event_dict


def _hide_exception_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if k in ("exc_value", "exc_notes") else _hide_exception_values(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_hide_exception_values(v) for v in value]
    return value


def hide_exception_messages(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Mantém tipo e frames, mas a mensagem pode trazer input do Pydantic ou parâmetros SQL"""
    if "exception" in event_dict:
        event_dict["exception"] = _hide_exception_values(event_dict["exception"])
    return event_dict


def _add_service(service_name: str) -> Processor:
    """Processor fixo: contextvars do create_app não chegam às tasks do uvicorn"""

    def add_service(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        event_dict["service"] = service_name
        return event_dict

    return add_service


def configure_logging(
    service_name: str, *, level: str | int = "INFO", stream: TextIO | None = None
) -> None:
    """Idempotente: troca só o handler veriditi do root e mantém os do pytest"""
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_service(service_name),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        redact_sensitive,
        structlog.processors.StackInfoRenderer(),
    ]
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(ignore_frame_names=[__name__]),
        wrapper_class=structlog.stdlib.BoundLogger,
        # capture_logs não enxerga loggers em cache
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # show_locals=True (padrão) vazaria variáveis locais, como headers com o token
            structlog.processors.ExceptionRenderer(
                structlog.tracebacks.ExceptionDictTransformer(show_locals=False)
            ),
            hide_exception_messages,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.name = _HANDLER_NAME
    handler.setFormatter(formatter)
    # Também no handler: o uvicorn fixa o nível dos próprios loggers
    handler.setLevel(level)

    root = logging.getLogger()
    for old in [h for h in root.handlers if h.name == _HANDLER_NAME]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # O log de acesso é o request_finished do RequestContextMiddleware
    access = logging.getLogger("uvicorn.access")
    access.handlers = [logging.NullHandler()]
    access.propagate = False
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    # Sem nome, o LoggerFactory usa o módulo de quem chamou; get_logger(None) daria "root"
    return structlog.stdlib.get_logger(name) if name else structlog.stdlib.get_logger()


def mask_email(email: str) -> str:
    """Deixa só a 1ª letra para o log identificar o destinatário sem expô-lo"""
    local, sep, domain = email.rpartition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"
