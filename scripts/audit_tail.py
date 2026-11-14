"""Acompanha a trilha de auditoria; roda dentro do container monitoring (make audit-tail)."""

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

BASE = "http://127.0.0.1:8000/internal/events"
TOKEN = os.environ["INTERNAL_API_TOKEN"]
PAGE = 200  # máximo da API
WINDOW = timedelta(minutes=2)  # folga para eventos confirmados fora de ordem
N = int(os.environ.get("AUDIT_N") or 10)


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


seen: set[str] = set()
for event in history():
    seen.add(event["event_id"])
    show(event)
print("-- aguardando novos eventos (Ctrl-C para sair)", flush=True)

while True:
    time.sleep(2)
    since = (datetime.now(UTC) - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
    for event in fetch(limit=PAGE, **{"from": since})["items"]:
        if event["event_id"] not in seen:
            seen.add(event["event_id"])
            show(event)
