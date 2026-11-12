"""Logs JSON de structlog, uvicorn e libs de terceiros no mesmo formato (ADR-012)"""

import logging
import sys
from collections.abc import Mapping
from typing import Any, Final, TextIO

import structlog
from structlog.tracebacks import safe_str
from structlog.typing import EventDict, ExcInfo, Processor, WrappedLogger

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
# Sensíveis quando são um segmento inteiro do nome (otp, mas não footprint)
_SENSITIVE_SEGMENTS: Final = frozenset({"otp"})
# *_code só é segredo com um destes prefixos; status_code, zip_code, error_code não são
_SECRET_CODE_PREFIXES: Final = frozenset(
    {"verification", "otp", "mfa", "auth", "reset", "confirmation", "recovery", "pin"}
)
# Metadados sobre o segredo (token_type, password_changed_at, has_password), não o segredo
_METADATA_SUFFIXES: Final = (
    "_type",
    "_id",
    "_at",
    "_count",
    "s_used",
    "_name",
    "_present",
    "_rotation",
    "_attempts",
    "_requested",
)
_METADATA_PREFIXES: Final = ("has_", "max_")
REDACTED: Final = "[redacted]"

_HANDLER_NAME: Final = "veriditi"
# O ExceptionRenderer e o ProcessorFormatter precisam desses valores intactos
_UNTOUCHED_KEYS: Final = frozenset({"exc_info", "stack_info", "_record", "_from_structlog"})


def _normalize(key: str) -> str:
    return key.lower().replace("-", "_")


def _is_secret_code(segments: list[str]) -> bool:
    """code sozinho ou com prefixo de segredo; o hash de um código é tão sensível quanto ele"""
    if segments[-1] == "hash":
        segments = segments[:-1]
    if not segments or segments[-1] != "code":
        return False
    prefix = segments[:-1]
    return (
        not prefix
        or any(s in _SECRET_CODE_PREFIXES for s in prefix)
        or ("one_time" in "_".join(prefix))
    )


def is_sensitive_key(key: object) -> bool:
    """Por parte do nome, para pegar db_password, jwt_private_key, verification_code e afins"""
    if isinstance(key, bytes):
        key = key.decode("latin-1")
    if not isinstance(key, str) or not key:
        return False
    normalized = _normalize(key)
    segments = normalized.split("_")
    if _is_secret_code(segments):
        return True
    if normalized.endswith(_METADATA_SUFFIXES) or normalized.startswith(_METADATA_PREFIXES):
        return False
    if _SENSITIVE_SEGMENTS.intersection(segments):
        return True
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _is_sensitive_pair(value: list[Any] | tuple[Any, ...], in_headers: bool) -> bool:
    """Par (nome, valor) de header: nome em bytes (ASGI cru) ou dentro de uma chave *header*"""
    if len(value) != 2 or not isinstance(value[0], str | bytes):
        return False
    if not (isinstance(value[0], bytes) or in_headers):
        return False
    return isinstance(value[1], str | bytes) and is_sensitive_key(value[0])


def _redact(value: Any, in_headers: bool = False) -> Any:
    if isinstance(value, Mapping):
        return {
            k: REDACTED if is_sensitive_key(k) else _redact(v, _is_header_key(k))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        sensitive = _is_sensitive_pair(value, in_headers)
        items = [value[0], REDACTED] if sensitive else [_redact(v, in_headers) for v in value]
        return tuple(items) if isinstance(value, tuple) else items
    return value


def _is_header_key(key: object) -> bool:
    return isinstance(key, str) and "header" in _normalize(key)


def redact_sensitive(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Troca por [redacted] o valor de chaves sensíveis, inclusive aninhadas"""
    for key, value in event_dict.items():
        if key in _UNTOUCHED_KEYS:
            continue
        event_dict[key] = REDACTED if is_sensitive_key(key) else _redact(value, _is_header_key(key))
    return event_dict


# Mensagens que sabidamente repetem dados: SQL ("Duplicate entry '<email>'") e input do Pydantic
_DATA_EXCEPTIONS: Final = frozenset(
    {"sqlalchemy.exc.DBAPIError", "pydantic_core._pydantic_core.ValidationError"}
)
_DB_DRIVER_MODULES: Final = frozenset({"pymysql", "aiomysql", "sqlite3", "MySQLdb"})


def _carries_data(exc: BaseException) -> bool:
    if type(exc).__module__.split(".")[0] in _DB_DRIVER_MODULES:
        return True
    return any(
        f"{cls.__module__}.{cls.__qualname__}" in _DATA_EXCEPTIONS for cls in type(exc).__mro__
    )


def _db_errno(exc: BaseException) -> int | None:
    """Código do MySQL (1062, 1045...) do erro do driver, sem importar o SQLAlchemy"""
    args = getattr(getattr(exc, "orig", None) or exc, "args", ())
    if args and isinstance(args[0], int) and not isinstance(args[0], bool):
        return args[0]
    return None


def _data_exceptions(root: BaseException) -> dict[tuple[str, str], int | None]:
    """(tipo, mensagem) das exceções da cadeia e dos grupos que carregam dados"""
    found: dict[tuple[str, str], int | None] = {}
    seen: set[int] = set()
    pending: list[BaseException | None] = [root]
    while pending:
        exc = pending.pop()
        if exc is None or id(exc) in seen:
            continue
        seen.add(id(exc))
        if _carries_data(exc):
            found[(type(exc).__name__, safe_str(exc))] = _db_errno(exc)
        pending += [exc.__cause__, exc.__context__, getattr(exc, "orig", None)]
        if isinstance(exc, BaseExceptionGroup):
            pending += list(exc.exceptions)
    return found


def _redact_stacks(stacks: list[dict[str, Any]], found: dict[tuple[str, str], int | None]) -> None:
    for stack in stacks:
        key = (stack.get("exc_type"), stack.get("exc_value"))
        if key in found:
            stack["exc_value"] = REDACTED
            if stack.get("exc_notes"):
                stack["exc_notes"] = [REDACTED] * len(stack["exc_notes"])
            if (errno := found[key]) is not None:
                stack["db_errno"] = errno
        for group_member in stack.get("exceptions", []):
            _redact_stacks(group_member, found)


class _SafeExceptionFormatter:
    """Mantém tipo, frames e mensagem; só redige exceções que repetem dados de entrada"""

    def __init__(self) -> None:
        # show_locals=True (padrão) vazaria variáveis locais, como headers com o token
        self._inner = structlog.tracebacks.ExceptionDictTransformer(show_locals=False)

    def __call__(self, exc_info: ExcInfo) -> list[dict[str, Any]]:
        stacks = self._inner(exc_info)
        _redact_stacks(stacks, _data_exceptions(exc_info[1]))
        return stacks


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
            structlog.processors.ExceptionRenderer(_SafeExceptionFormatter()),
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
    # O aiosqlite loga em DEBUG cada statement com os parâmetros (e-mail, hash)
    for name in ("httpx", "httpcore", "aiosqlite"):
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
