"""Contract tests for the app-level surface every route in this package
reuses: health, bearer-token auth, the acting-identity header. Adapted from
`agency-v1/tests/test_app.py`, trimmed to what KATA-2's `main.py` exposes
(no `seed`/`llm` health fields or `/me/next` — those belong to the `engine`
package, KATA-2's follow-up issue).
"""

import logging
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.main import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def test_health_needs_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "learning"
    assert body["version"] == "1.2.1"


def test_health_db_reports_missing_database_url(client):
    r = client.get("/health/db")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "database_unconfigured"


def test_whoami_without_token_is_401(client):
    r = client.get("/whoami", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthorized"


def test_whoami_with_wrong_token_is_401(client):
    r = client.get(
        "/whoami",
        headers={"Authorization": "Bearer nope", "X-Acting-Identity": "slack:U1"},
    )
    assert r.status_code == 401


def test_whoami_without_identity_is_422(client):
    r = client.get("/whoami", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_whoami_accepts_the_web_service_token(client, monkeypatch):
    """Contract change #7: WEB_SERVICE_TOKEN is accepted exactly like the
    Hermes token; the acting identity, not the token, says who is calling."""
    monkeypatch.setenv("WEB_SERVICE_TOKEN", "web-token")
    r = client.get(
        "/whoami",
        headers={"Authorization": "Bearer web-token", "X-Acting-Identity": "web:auth0|abc"},
    )
    assert r.status_code == 200
    assert r.json()["acting_identity"]["platform"] == "web"


def test_whoami_rejects_the_web_token_when_it_is_unconfigured(client, monkeypatch):
    monkeypatch.delenv("WEB_SERVICE_TOKEN", raising=False)
    r = client.get(
        "/whoami",
        headers={"Authorization": "Bearer web-token", "X-Acting-Identity": "web:auth0|abc"},
    )
    assert r.status_code == 401


def test_whoami_echoes_acting_identity(client):
    r = client.get(
        "/whoami",
        headers={
            "Authorization": "Bearer test-token",
            "X-Acting-Identity": "slack:U123;alt=uuid-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["acting_identity"] == {
        "platform": "slack",
        "external_id": "U123",
        "alt_id": "uuid-1",
    }


def test_cli_entrypoints_exit_zero():
    from learning_service.cli import main

    assert main(["retention"]) == 0
    assert main(["replay"]) == 0
    assert main(["bogus"]) == 2


def test_request_log_includes_method_path_status_and_acting_identity(client, caplog):
    with caplog.at_level(logging.INFO, logger="learning_service.request"):
        r = client.get(
            "/whoami",
            headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"},
        )
    assert r.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "learning_service.request"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "GET" in message
    assert "/whoami" in message
    assert "200" in message
    assert "slack:U1" in message
    assert "test-token" not in message


def test_health_probe_requests_are_not_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger="learning_service.request"):
        r = client.get("/health")
    assert r.status_code == 200
    assert not [rec for rec in caplog.records if rec.name == "learning_service.request"]
