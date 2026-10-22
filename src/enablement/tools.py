"""Shared tool implementations used by the agent and the MCP server."""

from enablement.auth import Actor
from enablement.errors import LabError
from enablement.permissions import contained_path
from enablement.store import Store


def _require(actor: Actor, scope: str) -> None:
    if scope not in actor.scopes:
        raise LabError("unauthorized", f"missing scope {scope}")


def lookup_grant(actor: Actor, store: Store, grant_id: str) -> dict:
    _require(actor, "grants.read")
    if not grant_id:
        raise LabError("invalid", "grant_id is required")
    row = store.grant_for(grant_id, actor.tenant_id)
    if row is None:
        return {"found": False, "grant_id": grant_id}
    return {"found": True, **row}


def read_policy(actor: Actor, store: Store, policy_id: str) -> dict:
    _require(actor, "policy.read")
    row = store.policy_for(policy_id, actor.tenant_id)
    if row is None:
        return {"found": False, "policy_id": policy_id}
    return {"found": True, **row}


def request_approval(actor: Actor, store: Store, grant_id: str, reason: str) -> dict:
    _require(actor, "approvals.request")
    if actor.role != "engineer":
        raise LabError("unauthorized", "engineer role required")
    if not reason.strip():
        raise LabError("invalid", "reason is required")
    found = lookup_grant(actor, store, grant_id)
    if not found["found"]:
        raise LabError("not_found", "grant not found")
    approval = store.create_approval(grant_id, actor.tenant_id, actor.subject, actor.session_id)
    return {
        "approval_id": approval["approval_id"],
        "status": approval["status"],
        "grant_id": grant_id,
        "requester_subject": approval["requester_subject"],
    }


def decide_approval(actor: Actor, store: Store, approval_id: str, decision: str) -> dict:
    _require(actor, "approvals.decide")
    row = store.decide(approval_id, actor.tenant_id, actor.subject, actor.role, decision)
    return {
        "approval_id": row["approval_id"],
        "status": row["status"],
        "grant_id": row["grant_id"],
        "approver_subject": row["approver_subject"],
    }


def record_decision(actor: Actor, store: Store, grant_id: str, approval_id: str) -> dict:
    _require(actor, "approvals.record")
    return store.record(approval_id, actor.tenant_id, actor.subject, actor.role, grant_id)


def read_secret(actor: Actor, name: str) -> dict:
    """Refuse without reading the secret table into the result."""
    del actor, name
    raise LabError("denied", "read_secret is denied")


def edit_workspace(workspace: dict[str, str], path: str, content: str) -> dict:
    if not contained_path(path):
        raise LabError("denied", "path is outside the workspace")
    base = path.replace("\\", "/").rsplit("/", 1)[-1]
    if base.endswith(".secret"):
        raise LabError("denied", "secret paths are denied")
    workspace[path] = content
    return {"written": True, "path": path, "live_directory": False}


def execute(actor: Actor, store: Store, workspace: dict[str, str], name: str, arguments: dict) -> dict:
    if name == "lookup_grant":
        return lookup_grant(actor, store, str(arguments.get("grant_id", "")))
    if name == "read_policy":
        return read_policy(actor, store, str(arguments.get("policy_id", "")))
    if name == "request_approval":
        return request_approval(
            actor,
            store,
            str(arguments.get("grant_id", "")),
            str(arguments.get("reason", "")),
        )
    if name == "decide_approval":
        return decide_approval(
            actor,
            store,
            str(arguments.get("approval_id", "")),
            str(arguments.get("decision", "")),
        )
    if name == "record_decision":
        return record_decision(
            actor,
            store,
            str(arguments.get("grant_id", "")),
            str(arguments.get("approval_id", "")),
        )
    if name == "read_secret":
        return read_secret(actor, str(arguments.get("name", "")))
    if name == "edit_workspace":
        return edit_workspace(workspace, str(arguments.get("path", "")), str(arguments.get("content", "")))
    raise LabError("invalid", "unknown tool")
