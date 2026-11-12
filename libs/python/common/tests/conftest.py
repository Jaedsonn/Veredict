import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import structlog

from veriditi_common.logging import configure_logging

JsonLogs = Callable[[], list[dict[str, Any]]]


def _reset_logging() -> None:
    root = logging.getLogger()
    for handler in [h for h in root.handlers if h.name == "veriditi"]:
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)
    structlog.reset_defaults()


@pytest.fixture
def reset_logging() -> Iterator[None]:
    """Desfaz o configure_logging, que mexe no root logger e no structlog"""
    yield
    _reset_logging()


@pytest.fixture
def json_logs(reset_logging: None) -> JsonLogs:
    """Saída real do configure_logging (contextvars, service e redação) lida linha a linha"""
    stream = io.StringIO()
    configure_logging("svc-test", stream=stream, level="DEBUG")

    def read() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    return read
