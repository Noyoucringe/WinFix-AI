"""Integration tests for the FastAPI backend."""

import pytest
from fastapi.testclient import TestClient

from app.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["diagnostic_tools"] >= 20
    assert body["remediation_tools"] >= 15


def test_tools_listing(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    tools = r.json()
    assert any(t["read_only"] for t in tools)
    assert any(not t["read_only"] for t in tools)


def test_diagnose_and_full_flow(client, scenario):
    from tests.scenarios import STORAGE_AFTER_CLEANUP, STORAGE_FULL

    scenario.use(STORAGE_FULL, after_fix=STORAGE_AFTER_CLEANUP)
    r = client.post("/api/diagnose", json={"problem": "My disk is almost full"})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]["category"] == "low_disk_space"
    assert body["proposals"]
    sid = body["session_id"]
    tool = body["proposals"][0]["tool"]

    # Approval returns the proposal card.
    a = client.post("/api/remediation/approve", json={"session_id": sid, "tool": tool})
    assert a.status_code == 200

    # Execution without approval is forbidden.
    denied = client.post("/api/remediation/execute",
                         json={"session_id": sid, "tool": tool, "approved": False})
    assert denied.status_code == 403

    # Execution with approval succeeds (result may be unsupported off-Windows).
    ok = client.post("/api/remediation/execute",
                     json={"session_id": sid, "tool": tool, "approved": True})
    assert ok.status_code == 200
    assert ok.json()["executed"] is True
    assert ok.json()["verification"]["checks"]

    # Re-verify reruns the measurements.
    again = client.post("/api/verify", json={"session_id": sid})
    assert again.status_code == 200


def test_history_endpoint(client):
    client.post("/api/diagnose", json={"problem": "My wifi keeps disconnecting"})
    r = client.get("/api/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_diagnose_rejects_empty_problem(client):
    r = client.post("/api/diagnose", json={"problem": ""})
    assert r.status_code == 422


def test_execute_unknown_session(client):
    r = client.post("/api/remediation/execute",
                    json={"session_id": "nope", "tool": "flush_dns", "approved": True})
    assert r.status_code == 404
