"""Grant review. Completion follows the store, not the fixture sentence."""

from enablement.agent import run_turns, text_response, tool_response
from enablement.auth import Actor
from enablement.errors import LabError
from enablement.session import Session, engineer_session
from enablement.store import Store
from enablement.tools import decide_approval


def investigate_script(grant_id: str) -> list[dict]:
    return [
        tool_response("toolu_lookup", "lookup_grant", {"grant_id": grant_id}, "msg_01"),
        tool_response("toolu_policy", "read_policy", {"policy_id": "SYN-POLICY-GRANT"}, "msg_02"),
        tool_response(
            "toolu_request",
            "request_approval",
            {"grant_id": grant_id, "reason": "directory.read needs a separate approver"},
            "msg_03",
        ),
        text_response("Approval is pending. The grant is not recorded.", "msg_04"),
    ]


def resume_script(grant_id: str, approval_id: str) -> list[dict]:
    return [
        tool_response(
            "toolu_record",
            "record_decision",
            {"grant_id": grant_id, "approval_id": approval_id},
            "msg_05",
        ),
        text_response("The grant change is complete.", "msg_06"),
    ]


def investigate(store: Store, actor: Actor, grant_id: str) -> tuple[Session, dict]:
    if store.grant_for(grant_id, actor.tenant_id) is None:
        raise LabError("not_found", "grant not found")
    session = engineer_session(store, actor, grant_id)
    report = run_turns(
        session,
        store,
        investigate_script(grant_id),
        f"Review {grant_id} for a synthetic directory.read grant.",
    )
    session.status = "AWAITING_APPROVAL" if session.approval_id else "STOPPED"
    session.completion_claimed = False
    store.remember_session(session.snapshot())
    return session, report


def decide(store: Store, actor: Actor, approval_id: str, decision: str) -> dict:
    return decide_approval(actor, store, approval_id, decision)


def resume(store: Store, session: Session) -> tuple[Session, dict]:
    if session.role != "engineer":
        raise LabError("unauthorized", "engineer role required")
    report = run_turns(
        session,
        store,
        resume_script(session.grant_id, session.approval_id),
        "Continue the review after the approval decision.",
    )
    grant = store.grant_for(session.grant_id, session.tenant_id)
    recorded = bool(grant and grant["status"] == "recorded")
    session.status = "COMPLETED" if recorded else "STOPPED"
    session.completion_claimed = recorded
    store.remember_session(session.snapshot())
    return session, report


def public_view(session: Session, report: dict | None = None) -> dict:
    body = session.snapshot()
    body["model_text"] = session.model_text
    body["model_text_class"] = "EXAMPLE"
    body["remote_called"] = False if report is None else report["remote_called"]
    body["sdk_parsed_tool_use"] = False if report is None else report["sdk_parsed_tool_use"]
    body["executed_tools"] = [] if report is None else report["executed"]
    body["live_directory"] = False
    return body
