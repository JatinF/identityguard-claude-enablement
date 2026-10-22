"""Authenticated MCP server and tool-level authorization over in-process ASGI."""

import json

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from enablement.catalog import SECRET_MATERIAL
from enablement.mcp_server import create_mcp
from enablement.store import Store


def _factory(app):
    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://enablement.local",
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    return factory


async def _call(store, token, name, arguments):
    server = create_mcp(store)
    app = server.streamable_http_app()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with server.session_manager.run():
        async with streamablehttp_client(
            "http://enablement.local/mcp",
            headers=headers,
            httpx_client_factory=_factory(app),
            terminate_on_close=False,
        ) as (read, write, _session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool(name, arguments)
                return listed, result


def test_missing_and_unknown_bearers_are_rejected():
    async def scenario():
        server = create_mcp(Store())
        app = server.streamable_http_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://enablement.local",
        ) as client:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
            missing = await client.post("/mcp", json=payload)
            unknown = await client.post("/mcp", headers={"Authorization": "Bearer not-a-token"}, json=payload)
        assert missing.status_code == 401
        assert unknown.status_code == 401

    anyio.run(scenario)


def test_typed_tools_and_tool_level_authorization():
    store = Store()

    async def scenario():
        listed, lookup = await _call(store, "dev-engineer-a", "lookup_grant", {"grant_id": "SYN-GRANT-001"})
        schema = next(tool.inputSchema for tool in listed.tools if tool.name == "lookup_grant")
        assert schema["properties"]["grant_id"]["type"] == "string"
        assert {tool.name for tool in listed.tools} >= {
            "lookup_grant",
            "read_policy",
            "request_approval",
            "decide_approval",
            "record_decision",
            "read_secret",
        }
        assert lookup.isError is False
        body = json.loads(lookup.content[0].text)
        assert body["found"] is True
        assert body["principal"] == "SYN-APP-BILLING"

        _listed, hidden = await _call(store, "dev-engineer-a", "lookup_grant", {"grant_id": "SYN-GRANT-002"})
        hidden_body = json.loads(hidden.content[0].text)
        assert hidden_body["found"] is False
        assert "SYN-MARKER-TENANT-B" not in hidden.content[0].text

        _listed, opened = await _call(
            store,
            "dev-engineer-a",
            "request_approval",
            {"grant_id": "SYN-GRANT-001", "reason": "directory.read needs a separate approver"},
        )
        approval_id = json.loads(opened.content[0].text)["approval_id"]

        _listed, engineer_decide = await _call(
            store,
            "dev-engineer-a",
            "decide_approval",
            {"approval_id": approval_id, "decision": "approve"},
        )
        assert engineer_decide.isError is True
        assert "missing scope approvals.decide" in engineer_decide.content[0].text

        _listed, self_decide = await _call(
            store,
            "dev-self-a",
            "decide_approval",
            {"approval_id": approval_id, "decision": "approve"},
        )
        assert self_decide.isError is True
        assert "requester cannot approve" in self_decide.content[0].text

        _listed, secret = await _call(store, "dev-engineer-a", "read_secret", {"name": "directory-token"})
        assert secret.isError is True
        assert SECRET_MATERIAL not in secret.content[0].text

        _listed, approved = await _call(
            store,
            "dev-approver-a",
            "decide_approval",
            {"approval_id": approval_id, "decision": "approve"},
        )
        assert approved.isError is False
        assert json.loads(approved.content[0].text)["status"] == "approved"

        _listed, recorded = await _call(
            store,
            "dev-engineer-a",
            "record_decision",
            {"grant_id": "SYN-GRANT-001", "approval_id": approval_id},
        )
        recorded_body = json.loads(recorded.content[0].text)
        assert recorded_body["recorded"] is True
        assert recorded_body["live_directory"] is False

    anyio.run(scenario)
