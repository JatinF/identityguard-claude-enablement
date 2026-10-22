"""Authenticated MCP server. The transport under test is in-process ASGI."""

import json

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import AnyHttpUrl

from enablement.auth import LabAccessToken, actor_from_access
from enablement.errors import LabError
from enablement.store import Store
from enablement.tools import (
    decide_approval,
    lookup_grant,
    read_policy,
    read_secret,
    record_decision,
    request_approval,
)


class FixtureVerifier:
    """Accepts the lab's fixture bearers and rejects every other string."""

    async def verify_token(self, token: str) -> LabAccessToken | None:
        from enablement.auth import issue

        return issue(token)


def create_mcp(store: Store) -> FastMCP:
    server = FastMCP(
        "identityguard-lab",
        instructions="Synthetic grant tools. Tokens are fixtures and the directory is local.",
        auth=AuthSettings(
            issuer_url=AnyHttpUrl("https://auth.example.invalid"),
            resource_server_url=AnyHttpUrl("http://enablement.local/mcp"),
            required_scopes=[],
        ),
        token_verifier=FixtureVerifier(),
        json_response=True,
        stateless_http=True,
    )

    def actor():
        access = get_access_token()
        if not isinstance(access, LabAccessToken):
            raise ToolError("authentication required")
        return actor_from_access(access)

    def guard(fn):
        try:
            return json.dumps(fn())
        except LabError as exc:
            raise ToolError(exc.message) from exc

    @server.tool(name="lookup_grant")
    def lookup_grant_tool(grant_id: str) -> str:
        """Read one synthetic grant in the caller tenant."""
        return guard(lambda: lookup_grant(actor(), store, grant_id))

    @server.tool(name="read_policy")
    def read_policy_tool(policy_id: str) -> str:
        """Read one synthetic policy in the caller tenant."""
        return guard(lambda: read_policy(actor(), store, policy_id))

    @server.tool(name="request_approval")
    def request_approval_tool(grant_id: str, reason: str) -> str:
        """Open an approval for a proposed grant."""
        return guard(lambda: request_approval(actor(), store, grant_id, reason))

    @server.tool(name="decide_approval")
    def decide_approval_tool(approval_id: str, decision: str) -> str:
        """Approve or reject. The requester cannot decide."""
        return guard(lambda: decide_approval(actor(), store, approval_id, decision))

    @server.tool(name="record_decision")
    def record_decision_tool(grant_id: str, approval_id: str) -> str:
        """Record a grant after a different approver has approved it."""
        return guard(lambda: record_decision(actor(), store, grant_id, approval_id))

    @server.tool(name="read_secret")
    def read_secret_tool(name: str) -> str:
        """Denied for every token. The secret value is not returned."""
        return guard(lambda: read_secret(actor(), name))

    return server
