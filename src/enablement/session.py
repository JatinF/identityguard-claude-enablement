"""Local agent sessions. A session is not a Claude Code session."""

from dataclasses import dataclass, field

from enablement.auth import Actor
from enablement.permissions import (
    CHILD_ALLOWED,
    CHILD_DENIED,
    CHILD_MODE,
    ENGINEER_ALLOWED,
    ENGINEER_ASK,
    ENGINEER_DENIED,
    set_permission_mode,
)


@dataclass
class Session:
    session_id: str
    tenant_id: str
    subject: str
    role: str
    scopes: frozenset[str]
    mode: str = "default"
    allowed_tools: list[str] = field(default_factory=lambda: list(ENGINEER_ALLOWED))
    disallowed_tools: list[str] = field(default_factory=lambda: list(ENGINEER_DENIED))
    ask_rules: list[str] = field(default_factory=lambda: list(ENGINEER_ASK))
    parent_id: str | None = None
    can_widen: bool = True
    context: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)
    audit: list = field(default_factory=list)
    workspace: dict[str, str] = field(default_factory=dict)
    grant_id: str = ""
    approval_id: str = ""
    status: str = "OPEN"
    completion_claimed: bool = False
    model_text: str = ""

    def actor(self) -> Actor:
        return Actor(self.subject, self.tenant_id, self.role, self.scopes, self.session_id)

    def set_mode(self, mode: str) -> str:
        return set_permission_mode(self, mode)

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "parent_id": self.parent_id,
            "tenant_id": self.tenant_id,
            "subject": self.subject,
            "role": self.role,
            "mode": self.mode,
            "grant_id": self.grant_id,
            "approval_id": self.approval_id,
            "status": self.status,
            "completion_claimed": self.completion_claimed,
            "can_widen": self.can_widen,
            "context": dict(self.context),
        }


def engineer_session(store, token_actor: Actor, grant_id: str) -> Session:
    session = Session(
        session_id=store.next_session_id(),
        tenant_id=token_actor.tenant_id,
        subject=token_actor.subject,
        role="engineer",
        scopes=token_actor.scopes,
        mode="default",
        grant_id=grant_id,
        context={"tenant_id": token_actor.tenant_id, "grant_id": grant_id, "task": "review the proposed grant"},
    )
    store.remember_session(session.snapshot())
    return session


def child_session(store, parent: Session, task: str) -> Session:
    """Copy tenant and task context. The child cannot widen its permission mode."""
    session = Session(
        session_id=store.next_session_id(),
        tenant_id=parent.tenant_id,
        subject=parent.subject,
        role="reader",
        scopes=frozenset({"grants.read", "policy.read"}),
        mode=CHILD_MODE,
        allowed_tools=list(CHILD_ALLOWED),
        disallowed_tools=list(CHILD_DENIED),
        ask_rules=[],
        parent_id=parent.session_id,
        can_widen=False,
        grant_id=parent.grant_id,
        context={
            "tenant_id": parent.tenant_id,
            "grant_id": parent.grant_id,
            "task": task,
            "parent_id": parent.session_id,
        },
    )
    store.remember_session(session.snapshot())
    return session
