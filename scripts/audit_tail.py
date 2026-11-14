"""Acompanha a trilha de auditoria dentro do container monitoring (make audit-tail)"""

import contextlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import UTC, datetime, timedelta

BASE = "http://127.0.0.1:8000/internal/events"
TOKEN = os.environ["INTERNAL_API_TOKEN"]
PAGE = 200  # máximo da API
# A cauda só enxerga eventos com occurred_at dentro da janela e até PAGE por consulta:
# um evento mais velho que 2 min ou além do 200º da janela não aparece (o histórico sim)
WINDOW = timedelta(minutes=2)
SEEN_MAX = 5000


def parse_n(raw: str) -> int:
    try:
        n = int(raw or 10)
    except ValueError:
        n = 0
    if n < 1:
        print("n deve ser um inteiro >= 1", file=sys.stderr)
        sys.exit(2)
    return n


N = parse_n(os.environ.get("AUDIT_N", ""))


def fetch(**params: object) -> dict:
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-Internal-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def show(event: dict) -> None:
    print(
        f"{event['occurred_at']}  {event['service']:<12} {event['action']:<36} "
        f"{event['outcome']:<8} actor={event['actor_id']} req={event['request_id']}",
        flush=True,
    )


def history() -> list[dict]:
    """Histórico paginado por after_id (vale para eventos já gravados): guarda os N últimos"""
    items: list[dict] = []
    cursor = None
    while True:
        params = {"limit": PAGE, **({"after_id": cursor} if cursor else {})}
        page = fetch(**params)
        items = (items + page["items"])[-N:]
        cursor = page["next_cursor"]
        if cursor is None:
            return items


def main() -> None:
    seen: set[str] = set()
    order: deque[str] = deque()  # ids mais antigos saem primeiro, o conjunto não cresce sem fim

    def remember(event_id: str) -> bool:
        if event_id in seen:
            return False
        seen.add(event_id)
        order.append(event_id)
        if len(order) > SEEN_MAX:
            seen.discard(order.popleft())
        return True

    try:
        past = history()
    except (OSError, ValueError) as exc:
        sys.exit(f"monitoring indisponível: {type(exc).__name__}")
    for event in past:
        remember(event["event_id"])
        show(event)
    print("-- aguardando novos eventos (Ctrl-C para sair)", flush=True)

    while True:
        time.sleep(2)
        since = (datetime.now(UTC) - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            items = fetch(limit=PAGE, **{"from": since})["items"]
        except (OSError, ValueError) as exc:  # URLError, timeout, HTTPError e JSON inválido
            print(
                f"aviso: consulta falhou ({type(exc).__name__}), tentando de novo",
                file=sys.stderr,
                flush=True,
            )
            continue
        for event in items:
            if remember(event["event_id"]):
                show(event)


with contextlib.suppress(KeyboardInterrupt):
    main()
