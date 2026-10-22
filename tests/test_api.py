"""HTTP lab: missing bearer is 401, other tenants are 404, completion follows the store."""

from fastapi.testclient import TestClient

from enablement.api.app import create_app
from enablement.catalog import SECRET_MATERIAL


def _client():
    return TestClient(create_app())


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health_and_auth_boundaries():
    client = _client()
    health = client.get("/healthz")
    assert health.status_code == 200
    body = health.json()
    assert body["deployment_decision"] == "NO-GO"
    assert body["remote_called"] is False
    assert body["gates"]["hosted-model-run"] == "not-run"
    assert body["gates"]["claude-code-session"] == "not-run"
    assert client.post("/v1/reviews", json={"grant_id": "SYN-GRANT-001"}).status_code == 401
    assert client.post(
        "/v1/reviews",
        headers=_auth("nope"),
        json={"grant_id": "SYN-GRANT-001"},
    ).status_code == 401
    assert client.post(
        "/v1/reviews",
        headers=_auth("dev-engineer-a"),
        json={"grant_id": "SYN-GRANT-001", "extra": True},
    ).status_code == 422
    missing = client.post(
        "/v1/reviews",
        headers=_auth("dev-engineer-b"),
        json={"grant_id": "SYN-GRANT-001"},
    )
    assert missing.status_code == 404


def test_approval_gate_and_resume():
    client = _client()
    opened = client.post("/v1/reviews", headers=_auth("dev-engineer-a"), json={"grant_id": "SYN-GRANT-001"})
    assert opened.status_code == 200
    review = opened.json()
    assert review["status"] == "AWAITING_APPROVAL"
    assert review["completion_claimed"] is False
    assert review["remote_called"] is False
    assert review["sdk_parsed_tool_use"] is True
    session_id = review["session_id"]
    approval_id = review["approval_id"]

    own = client.post(
        f"/v1/approvals/{approval_id}/decision",
        headers=_auth("dev-engineer-a"),
        json={"decision": "approve"},
    )
    assert own.status_code == 403
    self_approve = client.post(
        f"/v1/approvals/{approval_id}/decision",
        headers=_auth("dev-self-a"),
        json={"decision": "approve"},
    )
    assert self_approve.status_code == 403

    approved = client.post(
        f"/v1/approvals/{approval_id}/decision",
        headers=_auth("dev-approver-a"),
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["approver_subject"] == "SYN-USER-QUINN"

    approver_resume = client.post(f"/v1/reviews/{session_id}/resume", headers=_auth("dev-approver-a"))
    assert approver_resume.status_code == 403
    other_tenant = client.get(f"/v1/reviews/{session_id}", headers=_auth("dev-engineer-b"))
    assert other_tenant.status_code == 404

    resumed = client.post(f"/v1/reviews/{session_id}/resume", headers=_auth("dev-engineer-a"))
    assert resumed.status_code == 200
    done = resumed.json()
    assert done["status"] == "COMPLETED"
    assert done["completion_claimed"] is True
    assert done["live_directory"] is False
    assert "complete" in done["model_text"]
    audit = client.get(f"/v1/audit/{session_id}", headers=_auth("dev-engineer-a"))
    assert audit.status_code == 200
    assert SECRET_MATERIAL not in audit.text
    steps = [item["tool"] for item in audit.json()["audit"]]
    assert steps == ["lookup_grant", "read_policy", "request_approval", "record_decision"]


def test_rejected_approval_does_not_claim_completion():
    client = _client()
    opened = client.post("/v1/reviews", headers=_auth("dev-engineer-a"), json={"grant_id": "SYN-GRANT-001"})
    approval_id = opened.json()["approval_id"]
    session_id = opened.json()["session_id"]
    rejected = client.post(
        f"/v1/approvals/{approval_id}/decision",
        headers=_auth("dev-approver-a"),
        json={"decision": "reject"},
    )
    assert rejected.status_code == 200
    resumed = client.post(f"/v1/reviews/{session_id}/resume", headers=_auth("dev-engineer-a"))
    body = resumed.json()
    assert body["status"] == "STOPPED"
    assert body["completion_claimed"] is False
    assert "complete" in body["model_text"]


def test_expired_approval_is_not_recorded():
    client = _client()
    opened = client.post("/v1/reviews", headers=_auth("dev-engineer-a"), json={"grant_id": "SYN-GRANT-001"})
    approval_id = opened.json()["approval_id"]
    client.app.state.store.expire(approval_id)
    expired = client.post(
        f"/v1/approvals/{approval_id}/decision",
        headers=_auth("dev-approver-a"),
        json={"decision": "approve"},
    )
    assert expired.status_code == 409
    assert expired.json()["error"] == "expired"
