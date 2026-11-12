from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from structlog.testing import capture_logs

from monitoring_service.dependencies import get_audit_event_repository
from monitoring_service.models import AuditEventRecord
from veriditi_common.audit import AuditEvent, AuditOutcome, HttpAuditLogger
from veriditi_common.db import Database
from veriditi_common.logging import REDACTED

URL = "/internal/events"
ACCEPTED = {"status": "accepted"}
UNAUTHORIZED = {"detail": {"code": "unauthorized", "message": "Não autenticado."}}

EventFactory = Callable[..., dict[str, Any]]
Headers = dict[str, str]


async def _records(db: Database) -> list[AuditEventRecord]:
    async with db.session_factory() as session:
        return list(await session.scalars(select(AuditEventRecord).order_by(AuditEventRecord.id)))


async def test_valid_event_is_accepted_with_server_received_at(
    client: AsyncClient,
    auth_headers: Headers,
    make_event: EventFactory,
    db: Database,
    received_at: datetime,
) -> None:
    body = make_event(occurred_at="2026-11-12T09:00:00.123456-03:00", actor_id=42)

    resp = await client.post(URL, json=body, headers=auth_headers)

    assert resp.status_code == 202
    assert resp.json() == ACCEPTED
    [record] = await _records(db)
    assert str(record.event_id) == body["event_id"]
    assert record.received_at == received_at
    assert record.occurred_at.isoformat() == "2026-11-12T12:00:00.123456+00:00"
    assert record.actor_id == 42


async def test_resend_is_accepted_without_duplicating(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory, db: Database
) -> None:
    body = make_event()

    first = await client.post(URL, json=body, headers=auth_headers)
    second = await client.post(URL, json=body, headers=auth_headers)
    upper = await client.post(
        URL, json={**body, "event_id": body["event_id"].upper()}, headers=auth_headers
    )

    assert [r.status_code for r in (first, second, upper)] == [202, 202, 202]
    assert first.json() == second.json() == upper.json() == ACCEPTED
    assert len(await _records(db)) == 1


async def test_sensitive_metadata_is_stored_redacted(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory, db: Database
) -> None:
    body = make_event(metadata={"password": "s3cr3t", "email_masked": "a***@example.com"})

    await client.post(URL, json=body, headers=auth_headers)

    [record] = await _records(db)
    assert record.metadata_ == {"password": REDACTED, "email_masked": "a***@example.com"}


SECRET_NAMES = [
    "password",
    "token",
    "code",
    "secret",
    "recoveryCodes",
    "backup_codes",
    "codes",
    "código",
    "auth.code",
    "otp code",
    "otpauth_uri",
    "seed",
]
KEPT_NAMES = ["status_code", "error_code", "zip_code", "token_type", "email_masked"]


async def test_secret_names_never_reach_storage(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory, db: Database
) -> None:
    metadata = {name: "s3cr3t" for name in SECRET_NAMES}
    metadata |= {name: "kept" for name in KEPT_NAMES}
    metadata["nested"] = [{name: "s3cr3t" for name in SECRET_NAMES}]

    await client.post(URL, json=make_event(metadata=metadata), headers=auth_headers)

    [record] = await _records(db)
    assert "s3cr3t" not in repr(record.metadata_)
    assert record.metadata_ is not None
    assert {name: record.metadata_[name] for name in KEPT_NAMES} == dict.fromkeys(
        KEPT_NAMES, "kept"
    )


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Internal-Token": "wrong-token-0123456789"}],
    ids=["missing", "wrong"],
)
async def test_post_requires_internal_token(
    client: AsyncClient, make_event: EventFactory, headers: Headers
) -> None:
    resp = await client.post(URL, json=make_event(), headers=headers)

    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED


async def test_token_is_checked_before_the_body(client: AsyncClient) -> None:
    resp = await client.post(URL, json={"received_at": "x"})

    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED


async def test_null_request_id_is_accepted(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    resp = await client.post(URL, json=make_event(request_id=None), headers=auth_headers)

    assert resp.status_code == 202


def _without(body: dict[str, Any], key: str) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k != key}


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda b: _without(b, "event_id"), id="no-event_id"),
        pytest.param(lambda b: _without(b, "occurred_at"), id="no-occurred_at"),
        pytest.param(lambda b: _without(b, "request_id"), id="no-request_id-key"),
        pytest.param(lambda b: {**b, "occurred_at": "2026-11-12T12:00:00"}, id="naive"),
        pytest.param(lambda b: {**b, "received_at": "2026-11-12T12:00:00Z"}, id="received_at"),
        pytest.param(lambda b: {**b, "id": 1}, id="id"),
        pytest.param(lambda b: {**b, "hash": "0" * 64}, id="hash"),
        pytest.param(lambda b: {**b, "action": "notification.user.registered"}, id="prefix"),
        pytest.param(lambda b: {**b, "outcome": "ok"}, id="outcome"),
        pytest.param(lambda b: {**b, "actor_ip": "999.1.1.1"}, id="actor_ip"),
        pytest.param(lambda b: {**b, "actor_id": 0}, id="actor_id"),
        pytest.param(lambda b: {**b, "service": "a" * 41}, id="service-length"),
        pytest.param(lambda b: {**b, "resource_id": "r" * 65}, id="resource_id-length"),
        pytest.param(lambda b: {**b, "metadata": [1, 2]}, id="metadata-not-object"),
    ],
)
async def test_invalid_payload_is_rejected(
    client: AsyncClient,
    auth_headers: Headers,
    make_event: EventFactory,
    db: Database,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    resp = await client.post(URL, json=mutate(make_event()), headers=auth_headers)

    assert resp.status_code == 422
    assert await _records(db) == []


async def test_malformed_json_is_rejected(client: AsyncClient, auth_headers: Headers) -> None:
    headers = {**auth_headers, "Content-Type": "application/json"}

    resp = await client.post(URL, content=b"{not json", headers=headers)

    assert resp.status_code == 422


async def test_storage_failure_is_internal_error_not_accepted(
    app: FastAPI, client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    class BrokenRepository:
        async def add(self, event: AuditEvent, *, received_at: datetime) -> bool:
            raise RuntimeError("banco fora")

    app.dependency_overrides[get_audit_event_repository] = BrokenRepository

    resp = await client.post(URL, json=make_event(), headers=auth_headers)

    assert resp.status_code == 500
    assert resp.json()["detail"]["code"] == "internal_error"


async def test_http_audit_logger_delivers_to_the_real_app(
    app: FastAPI, token: str, db: Database
) -> None:
    event = AuditEvent(service="auth", action="auth.user.registered", outcome=AuditOutcome.SUCCESS)

    with capture_logs() as logs:
        async with AsyncClient(transport=ASGITransport(app=app)) as http:
            await HttpAuditLogger(http, "http://monitoring.test", SecretStr(token)).record(event)

    assert all(line["event"] != "audit_delivery_failed" for line in logs)
    [record] = await _records(db)
    assert record.event_id == event.event_id


async def test_http_audit_logger_with_wrong_token_falls_back(app: FastAPI, db: Database) -> None:
    event = AuditEvent(service="auth", action="auth.user.registered", outcome=AuditOutcome.SUCCESS)
    wrong = SecretStr("wrong-token-0123456789")

    with capture_logs() as logs:
        async with AsyncClient(transport=ASGITransport(app=app)) as http:
            await HttpAuditLogger(http, "http://monitoring.test", wrong).record(event)

    [failure] = [line for line in logs if line["event"] == "audit_delivery_failed"]
    assert failure["status_code"] == 401
    assert await _records(db) == []


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_events_cannot_be_edited_or_removed(
    client: AsyncClient, auth_headers: Headers, method: str
) -> None:
    resp = await client.request(method, URL, headers=auth_headers)

    assert resp.status_code == 405
    assert resp.json()["detail"]["code"] == "method_not_allowed"


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
async def test_single_event_route_does_not_exist(
    client: AsyncClient, auth_headers: Headers, method: str
) -> None:
    resp = await client.request(method, f"{URL}/1", headers=auth_headers)

    assert resp.status_code == 404


def test_no_route_accepts_edit_methods(app: FastAPI) -> None:
    # Pelo OpenAPI: o FastAPI guarda os routers incluídos aninhados em app.routes
    paths = app.openapi()["paths"]
    methods = {method for operations in paths.values() for method in operations}

    assert set(paths[URL]) == {"get", "post"}
    assert not methods & {"put", "patch", "delete"}


async def _post_all(client: AsyncClient, headers: Headers, *bodies: dict[str, Any]) -> None:
    for body in bodies:
        assert (await client.post(URL, json=body, headers=headers)).status_code == 202


async def test_get_returns_the_stored_event(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    body = make_event(
        occurred_at="2026-11-12T09:00:00.123456-03:00",
        actor_id=42,
        actor_ip="203.0.113.7",
        request_id="3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55",
        resource_type="user",
        resource_id="42",
        metadata={"email_masked": "a***@example.com", "password": "x"},
    )
    await _post_all(client, auth_headers, body)

    resp = await client.get(URL, headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {
        "items": [
            {
                "id": 1,
                "event_id": body["event_id"],
                "occurred_at": "2026-11-12T12:00:00.123456Z",
                "received_at": "2026-11-12T15:00:00.654321Z",
                "service": "auth",
                "action": "auth.user.registered",
                "outcome": "success",
                "actor_id": 42,
                "actor_ip": "203.0.113.7",
                "request_id": "3f2b8c1e-8a4e-4a39-9a2b-1f1e0c9d7a55",
                "resource_type": "user",
                "resource_id": "42",
                "metadata": {"email_masked": "a***@example.com", "password": REDACTED},
            }
        ],
        "next_cursor": None,
    }


async def test_get_without_metadata_returns_empty_object(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    await _post_all(client, auth_headers, make_event())

    [item] = (await client.get(URL, headers=auth_headers)).json()["items"]

    assert item["metadata"] == {}


async def test_get_requires_internal_token(client: AsyncClient) -> None:
    resp = await client.get(URL)

    assert resp.status_code == 401
    assert resp.json() == UNAUTHORIZED


async def test_get_filters(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    await _post_all(
        client,
        auth_headers,
        make_event(actor_id=1, occurred_at="2026-11-12T12:00:00Z"),
        make_event(actor_id=2, occurred_at="2026-11-12T13:00:00Z"),
        make_event(actor_id=1, action="auth.user.logged_in", occurred_at="2026-11-12T14:00:00Z"),
    )

    async def ids(**params: Any) -> list[int]:
        resp = await client.get(URL, params=params, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        return [item["id"] for item in resp.json()["items"]]

    assert await ids(actor_id=1) == [1, 3]
    assert await ids(action="auth.user.logged_in") == [3]
    # 10:00-03:00 = 13:00Z inclusivo; 14:00Z exclusivo
    assert await ids(**{"from": "2026-11-12T10:00:00-03:00", "to": "2026-11-12T14:00:00Z"}) == [2]


async def test_get_paginates_by_id(
    client: AsyncClient, auth_headers: Headers, make_event: EventFactory
) -> None:
    await _post_all(client, auth_headers, make_event(), make_event(), make_event())

    first = (await client.get(URL, params={"limit": 2}, headers=auth_headers)).json()
    cursor = first["next_cursor"]
    last = await client.get(URL, params={"limit": 2, "after_id": cursor}, headers=auth_headers)

    assert [item["id"] for item in first["items"]] == [1, 2]
    assert cursor == 2
    assert [item["id"] for item in last.json()["items"]] == [3]
    assert last.json()["next_cursor"] is None


async def test_get_rejects_inverted_time_range(client: AsyncClient, auth_headers: Headers) -> None:
    params = {"from": "2026-11-13T00:00:00Z", "to": "2026-11-12T00:00:00Z"}

    resp = await client.get(URL, params=params, headers=auth_headers)

    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_time_range"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"actor_id": 0},
        {"after_id": -1},
        {"from": "2026-11-12T00:00:00"},
        {"action": ""},
    ],
    ids=["limit-0", "limit-201", "actor_id-0", "after_id-negative", "naive-from", "empty-action"],
)
async def test_get_rejects_invalid_query(
    client: AsyncClient, auth_headers: Headers, params: dict[str, Any]
) -> None:
    resp = await client.get(URL, params=params, headers=auth_headers)

    assert resp.status_code == 422


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda b: _without(b, "event_id"), id="missing-field"),
        pytest.param(lambda b: {**b, "action": "notification.user.registered"}, id="model"),
        pytest.param(lambda b: {**b, "outcome": "ok", "unexpected": 1}, id="field-and-extra"),
    ],
)
async def test_validation_error_does_not_echo_metadata(
    client: AsyncClient,
    auth_headers: Headers,
    make_event: EventFactory,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    body = mutate(make_event(metadata={"password": "s3cr3t-in-echo"}))

    resp = await client.post(URL, json=body, headers=auth_headers)

    assert resp.status_code == 422
    assert "s3cr3t-in-echo" not in resp.text
    assert all(set(item) == {"type", "loc", "msg"} for item in resp.json()["detail"])
