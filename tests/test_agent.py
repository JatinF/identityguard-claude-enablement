"""The Anthropic SDK parses fixture tool calls. The socket is not opened."""

import json

from enablement.auth import actor_from_token
from enablement.catalog import SECRET_MATERIAL
from enablement.gates import FIXTURE_API_KEY, MODEL_NAME
from enablement.store import Store
from enablement.workflow import investigate


def test_sdk_parses_tool_use_and_keeps_session_messages():
    store = Store()
    _session, report = investigate(store, actor_from_token("dev-engineer-a"), "SYN-GRANT-001")
    assert report["sdk_parsed_tool_use"] is True
    assert report["remote_called"] is False
    assert report["hosts"] == ["anthropic.local"] * report["request_count"]
    assert report["request_count"] == 4
    second = json.loads(report["requests"][1].content)
    assert second["model"] == MODEL_NAME
    assert "recorded" in second["system"]
    assert [item["role"] for item in second["messages"][:3]] == ["user", "assistant", "user"]
    assert "tool_result" in json.dumps(second["messages"][2])
    offered = [item["name"] for item in second["tools"]]
    assert "lookup_grant" in offered
    assert "read_secret" not in offered
    assert report["requests"][0].headers["x-api-key"] == FIXTURE_API_KEY
    assert SECRET_MATERIAL not in report["requests"][1].content.decode()
