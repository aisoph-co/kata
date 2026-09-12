"""App skeleton (spec §API → Authentication): `/health` unauthenticated,
`/whoami` requires a bearer token and `X-Acting-Identity`.
"""

from __future__ import annotations

import os

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from learning_service.main import app  # noqa: E402

client = TestClient(app)


def test_health_is_unauthenticated():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "1.2.1"


def test_whoami_requires_bearer_token():
    r = client.get("/whoami", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_whoami_requires_acting_identity_header():
    r = client.get("/whoami", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422


def test_whoami_returns_the_parsed_identity():
    r = client.get(
        "/whoami", headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "signal:+1555;alt=uuid-1"}
    )
    assert r.status_code == 200
    assert r.json()["acting_identity"] == {"platform": "signal", "external_id": "+1555", "alt_id": "uuid-1"}
