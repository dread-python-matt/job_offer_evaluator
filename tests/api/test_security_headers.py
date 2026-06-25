from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.presentation.api.security_headers import SecurityHeadersMiddleware


def _client(enable_hsts: bool) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return TestClient(app)


def test_adds_baseline_security_headers():
    response = _client(enable_hsts=False).get("/ping")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_omits_hsts_when_disabled():
    response = _client(enable_hsts=False).get("/ping")

    assert "Strict-Transport-Security" not in response.headers


def test_sends_hsts_when_enabled():
    response = _client(enable_hsts=True).get("/ping")

    assert "max-age=" in response.headers["Strict-Transport-Security"]
