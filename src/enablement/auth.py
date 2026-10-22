"""Fixture bearers. They authorize nothing outside this process."""

from dataclasses import dataclass

from mcp.server.auth.provider import AccessToken

from enablement.errors import LabError


@dataclass(frozen=True)
class Actor:
    subject: str
    tenant_id: str
    role: str
    scopes: frozenset[str]
    session_id: str = ""


class LabAccessToken(AccessToken):
    role: str
    tenant_id: str
    subject: str


# client_id, subject, tenant, role, scopes
_TOKEN_ROWS = {
    "dev-engineer-a": (
        "engineer-a",
        "SYN-USER-MORGAN",
        "tenant-a",
        "engineer",
        frozenset({"grants.read", "policy.read", "approvals.request", "approvals.record"}),
    ),
    "dev-approver-a": (
        "approver-a",
        "SYN-USER-QUINN",
        "tenant-a",
        "approver",
        frozenset({"grants.read", "approvals.decide"}),
    ),
    "dev-engineer-b": (
        "engineer-b",
        "SYN-USER-BLAKE",
        "tenant-b",
        "engineer",
        frozenset({"grants.read", "policy.read", "approvals.request", "approvals.record"}),
    ),
    "dev-self-a": (
        "self-a",
        "SYN-USER-MORGAN",
        "tenant-a",
        "approver",
        frozenset({"grants.read", "approvals.decide"}),
    ),
}


def issue(token: str) -> LabAccessToken | None:
    row = _TOKEN_ROWS.get(token)
    if row is None:
        return None
    client_id, subject, tenant_id, role, scopes = row
    return LabAccessToken(
        token=token,
        client_id=client_id,
        scopes=sorted(scopes),
        role=role,
        tenant_id=tenant_id,
        subject=subject,
    )


def actor_from_token(token: str, session_id: str = "") -> Actor:
    issued = issue(token)
    if issued is None:
        raise LabError("unauthorized", "authentication required")
    return Actor(
        subject=issued.subject,
        tenant_id=issued.tenant_id,
        role=issued.role,
        scopes=frozenset(issued.scopes),
        session_id=session_id,
    )


def actor_from_access(access: LabAccessToken, session_id: str = "") -> Actor:
    return Actor(
        subject=access.subject,
        tenant_id=access.tenant_id,
        role=access.role,
        scopes=frozenset(access.scopes),
        session_id=session_id,
    )
