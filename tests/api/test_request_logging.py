import logging
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.request_context import get_request_id
from app.presentation.api.request_logging import RequestLoggingMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        # Echo the bound id so a test can prove the contextvar reaches the endpoint.
        return {"request_id": get_request_id() or ""}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    return TestClient(app, raise_server_exceptions=False)


def _access_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.request"]


def test_generates_a_request_id_response_header():
    response = _client().get("/ping")

    request_id = response.headers["X-Request-ID"]
    uuid.UUID(request_id)  # a parseable uuid4 hex when none was supplied


def test_echoes_an_inbound_request_id():
    response = _client().get("/ping", headers={"X-Request-ID": "trace-abc"})

    assert response.headers["X-Request-ID"] == "trace-abc"


def test_request_id_is_bound_during_the_request():
    # The id the endpoint saw must equal the one returned to the client — i.e. every log line
    # emitted while handling the request carries the same id and can be correlated.
    response = _client().get("/ping")

    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_each_request_without_a_header_gets_a_fresh_id():
    client = _client()
    first = client.get("/ping", headers={"X-Request-ID": "first"}).headers[
        "X-Request-ID"
    ]
    second = client.get("/ping").headers["X-Request-ID"]

    assert first == "first"
    assert second != "first"


def test_emits_one_structured_access_line(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        _client().get("/ping")

    records = _access_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.http_method == "GET"
    assert record.http_path == "/ping"
    assert record.http_status == 200
    assert isinstance(record.duration_ms, float)
    assert record.event == "http_request"


def test_health_checks_are_logged_below_info(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        _client().get("/health")

    assert _access_records(caplog) == []


def test_failed_request_is_logged_at_error_with_500(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        _client().get("/boom")

    records = _access_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].http_status == 500
