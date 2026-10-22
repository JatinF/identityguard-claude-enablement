"""The six-step order from the Agent SDK permission docs, evaluated in-process."""

import pytest

from enablement.errors import LabError
from enablement.permissions import (
    evaluate,
    set_permission_mode,
    visible_tools,
)
from enablement.session import Session


def _allow(**kwargs):
    defaults = dict(
        mode="default",
        allowed_tools=[],
        disallowed_tools=[],
        ask_rules=[],
        hook=None,
        can_use_tool=None,
        kind="write",
    )
    defaults.update(kwargs)
    return evaluate("lookup_grant", {"grant_id": "SYN-GRANT-001"}, **defaults)


def test_hook_deny_wins_over_bypass():
    decision = evaluate(
        "lookup_grant",
        {},
        mode="bypassPermissions",
        allowed_tools=["lookup_grant"],
        disallowed_tools=[],
        ask_rules=[],
        hook=lambda _name, _payload: "deny",
    )
    assert decision.effect == "deny"
    assert decision.step == "hooks"
    assert decision.hook_runtime == "local-stand-in"


def test_hook_allow_does_not_skip_a_deny_rule():
    decision = evaluate(
        "read_secret",
        {"name": "directory-token"},
        mode="bypassPermissions",
        allowed_tools=["read_secret"],
        disallowed_tools=["read_secret"],
        ask_rules=[],
        hook=lambda _name, _payload: "allow",
        can_use_tool=lambda _name, _payload: True,
    )
    assert decision.effect == "deny"
    assert decision.step == "deny_rules"
    assert decision.callback_invoked is False


def test_default_hook_runtime_is_not_run():
    decision = _allow(kind="read")
    assert decision.effect == "allow"
    assert decision.hook_runtime == "not-run"


def test_bare_deny_removes_the_tool_and_blocks_bypass():
    assert "read_secret" not in visible_tools(["read_secret", "lookup_grant"], ["read_secret"])
    decision = evaluate(
        "read_secret",
        {},
        mode="bypassPermissions",
        allowed_tools=["*"],
        disallowed_tools=["read_secret"],
        ask_rules=[],
        can_use_tool=lambda _name, _payload: True,
    )
    assert decision.step == "deny_rules"


def test_scoped_deny_keeps_the_tool_and_blocks_matching_calls():
    names = visible_tools(["edit_workspace"], ["edit_workspace(*.secret)"])
    assert names == ["edit_workspace"]
    denied = evaluate(
        "edit_workspace",
        {"path": "notes.secret"},
        mode="bypassPermissions",
        allowed_tools=["edit_workspace"],
        disallowed_tools=["edit_workspace(*.secret)"],
        ask_rules=[],
        kind="edit",
    )
    allowed = evaluate(
        "edit_workspace",
        {"path": "notes.md"},
        mode="bypassPermissions",
        allowed_tools=[],
        disallowed_tools=["edit_workspace(*.secret)"],
        ask_rules=[],
        kind="edit",
    )
    assert denied.effect == "deny" and denied.step == "deny_rules"
    assert allowed.effect == "allow" and allowed.step == "permission_mode"


def test_user_interaction_reaches_the_callback_in_bypass():
    decision = evaluate(
        "record_decision",
        {"grant_id": "SYN-GRANT-001", "approval_id": "SYN-APR-001"},
        mode="bypassPermissions",
        allowed_tools=["record_decision"],
        disallowed_tools=[],
        ask_rules=[],
        can_use_tool=lambda _name, _payload: False,
    )
    assert decision.effect == "deny"
    assert decision.step == "can_use_tool"
    assert decision.callback_invoked is True


def test_dontask_denies_without_calling_the_callback():
    def boom(_name, _payload):
        raise AssertionError("callback invoked")

    decision = evaluate(
        "record_decision",
        {},
        mode="dontAsk",
        allowed_tools=["record_decision"],
        disallowed_tools=[],
        ask_rules=[],
        can_use_tool=boom,
    )
    assert decision.effect == "deny"
    assert decision.callback_invoked is False
    assert decision.step == "ask_rules"


def test_unanchored_allow_glob_does_not_approve():
    decision = evaluate(
        "edit_workspace",
        {"path": "notes.md"},
        mode="default",
        allowed_tools=["*"],
        disallowed_tools=[],
        ask_rules=[],
        can_use_tool=None,
        kind="edit",
    )
    assert decision.effect == "deny"
    assert decision.step == "can_use_tool"


def test_server_scoped_allow_glob_matches_the_lab_server():
    decision = _allow(allowed_tools=["mcp__identityguard__*"], kind="write")
    assert decision.effect == "allow"
    assert decision.step == "allow_rules"


def test_deny_globs_remove_mcp_tools():
    tools = ["lookup_grant", "read_policy"]
    assert visible_tools(tools, ["*"]) == []
    assert visible_tools(tools, ["mcp__*"]) == []


def test_accept_edits_stays_inside_the_workspace():
    inside = evaluate(
        "edit_workspace",
        {"path": "lab/notes.md", "content": "x"},
        mode="acceptEdits",
        allowed_tools=[],
        disallowed_tools=[],
        ask_rules=[],
        kind="edit",
    )
    outside = evaluate(
        "edit_workspace",
        {"path": "../notes.md", "content": "x"},
        mode="acceptEdits",
        allowed_tools=[],
        disallowed_tools=[],
        ask_rules=[],
        kind="edit",
    )
    assert inside.effect == "allow" and inside.step == "permission_mode"
    assert outside.effect == "deny"


def test_plan_mode_does_not_auto_approve_an_allow_rule():
    seen = []

    def callback(name, _payload):
        seen.append(name)
        return False

    decision = evaluate(
        "edit_workspace",
        {"path": "notes.md"},
        mode="plan",
        allowed_tools=["edit_workspace"],
        disallowed_tools=[],
        ask_rules=[],
        can_use_tool=callback,
        kind="edit",
    )
    assert decision.effect == "deny"
    assert decision.callback_invoked is True
    assert seen == ["edit_workspace"]


def test_reads_need_no_approval_and_bypass_ignores_the_allow_list():
    read = _allow(allowed_tools=[], kind="read")
    edit = evaluate(
        "edit_workspace",
        {"path": "notes.md"},
        mode="bypassPermissions",
        allowed_tools=["lookup_grant"],
        disallowed_tools=[],
        ask_rules=[],
        kind="edit",
    )
    assert read.effect == "allow" and read.step == "allow_rules"
    assert edit.effect == "allow" and edit.step == "permission_mode"


def test_auto_mode_is_not_run_and_a_child_cannot_widen():
    session = Session(
        session_id="SYN-SESSION-009",
        tenant_id="tenant-a",
        subject="SYN-USER-MORGAN",
        role="reader",
        scopes=frozenset({"grants.read"}),
        can_widen=False,
        mode="dontAsk",
    )
    with pytest.raises(LabError) as auto:
        set_permission_mode(session, "auto")
    with pytest.raises(LabError) as widened:
        session.set_mode("bypassPermissions")
    assert auto.value.code == "invalid"
    assert widened.value.code == "denied"
    assert session.mode == "dontAsk"
