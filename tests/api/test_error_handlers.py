from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.presentation.api.error_handlers import register_exception_handlers


def test_unhandled_exception_returns_generic_500_without_leaking_details():
    app = FastAPI()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    register_exception_handlers(app)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret internal detail" not in response.text
