"""A child session copies tenant context and cannot widen or approve."""

from enablement.agent import text_response, tool_response
from enablement.auth import actor_from_token
from enablement.delegation import delegate
from enablement.errors import LabError
from enablement.store import Store
from enablement.workflow import investigate


def test_child_copies_context_and_keeps_the_parent_approval_pending():
    store = Store()
    parent, _report = investigate(store, actor_from_token("dev-engineer-a"), "SYN-GRANT-001")
    script = [
        tool_response("toolu_child", "lookup_grant", {"grant_id": "SYN-GRANT-001"}, "msg_child"),
        text_response("Child stopped before any write.", "msg_child_end"),
    ]
    child, report = delegate(store, parent, "Read the grant and stop.", script)
    assert child.parent_id == parent.session_id
    assert child.context["tenant_id"] == "tenant-a"
    assert child.context["grant_id"] == "SYN-GRANT-001"
    assert child.context["task"] == "Read the grant and stop."
    assert "directory-token" not in child.context
    assert child.mode == "dontAsk"
    assert child.can_widen is False
    assert report["executed"] == ["lookup_grant"]
    assert report["remote_called"] is False
    try:
        child.set_mode("acceptEdits")
    except LabError as exc:
        assert exc.code == "denied"
    else:
        raise AssertionError("child widened permissions")
    assert store.approval(parent.approval_id)["status"] == "pending"
    assert child.completion_claimed is False
