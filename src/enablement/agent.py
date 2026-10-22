"""Anthropic Messages tool loop. Responses come from an in-process fixture."""

import json
from collections.abc import Callable

import httpx
from anthropic import Anthropic
from anthropic.types import TextBlock, ToolUseBlock

from enablement.errors import LabError
from enablement.gates import FIXTURE_API_KEY, FIXTURE_BASE_URL, MODEL_NAME
from enablement.permissions import EDIT_TOOLS, READ_TOOLS, evaluate, visible_tools
from enablement.session import Session
from enablement.store import Store
from enablement.tools import execute

TOOL_SCHEMAS = [
    {
        "name": "lookup_grant",
        "description": "Read one synthetic grant in the caller's tenant.",
        "input_schema": {
            "type": "object",
            "properties": {"grant_id": {"type": "string"}},
            "required": ["grant_id"],
        },
    },
    {
        "name": "read_policy",
        "description": "Read one synthetic grant policy in the caller's tenant.",
        "input_schema": {
            "type": "object",
            "properties": {"policy_id": {"type": "string"}},
            "required": ["policy_id"],
        },
    },
    {
        "name": "request_approval",
        "description": "Ask a different person to approve a proposed grant.",
        "input_schema": {
            "type": "object",
            "properties": {"grant_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["grant_id", "reason"],
        },
    },
    {
        "name": "record_decision",
        "description": "Record a grant only after a separate approver has approved it.",
        "input_schema": {
            "type": "object",
            "properties": {"grant_id": {"type": "string"}, "approval_id": {"type": "string"}},
            "required": ["grant_id", "approval_id"],
        },
    },
    {
        "name": "decide_approval",
        "description": "Approve or reject a pending grant. Hidden from the engineer session.",
        "input_schema": {
            "type": "object",
            "properties": {"approval_id": {"type": "string"}, "decision": {"type": "string"}},
            "required": ["approval_id", "decision"],
        },
    },
    {
        "name": "read_secret",
        "description": "Denied. The tool is removed from engineer and child sessions.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "edit_workspace",
        "description": "Write a file in the process-local workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are a synthetic grant-review assistant for tenant data already in the prompt. "
    "Do not claim the grant is recorded unless a record_decision tool result says recorded true. "
    "Do not request secrets. Directory changes stay inside this process."
)


class FixtureTransport(httpx.BaseTransport):
    """Returns scripted Messages API bodies. It never opens a socket."""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host != "anthropic.local" or request.url.path != "/v1/messages":
            raise LabError("denied", "hosted model call blocked")
        if not self.script:
            raise LabError("invalid", "fixture script exhausted")
        body = self.script.pop(0)
        return httpx.Response(200, json=body)


def tool_response(tool_id: str, name: str, payload: dict, message_id: str) -> dict:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": MODEL_NAME,
        "content": [{"type": "tool_use", "id": tool_id, "name": name, "input": payload}],
        "stop_reason": "tool_use",
        "stop_sequence": None,
        "usage": {"input_tokens": 20, "output_tokens": 10},
    }


def text_response(text: str, message_id: str) -> dict:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": MODEL_NAME,
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 20, "output_tokens": 12},
    }


def run_turns(
    session: Session,
    store: Store,
    script: list[dict],
    user_text: str,
    *,
    hook: Callable[[str, dict], str] | None = None,
    can_use_tool: Callable[[str, dict], bool] | None = None,
) -> dict:
    transport = FixtureTransport(script)
    http_client = httpx.Client(transport=transport)
    client = Anthropic(
        api_key=FIXTURE_API_KEY,
        base_url=FIXTURE_BASE_URL,
        http_client=http_client,
        max_retries=0,
    )
    offered = visible_tools([item["name"] for item in TOOL_SCHEMAS], session.disallowed_tools)
    tools = [item for item in TOOL_SCHEMAS if item["name"] in offered]
    messages: list[dict] = [{"role": "user", "content": user_text}]
    if can_use_tool is None:
        can_use_tool = _default_callback(session, store)

    try:
        remote = _consume(client, session, store, messages, tools, hook, can_use_tool)
    finally:
        http_client.close()
    session.messages = messages
    remote["request_count"] = len(transport.requests)
    remote["hosts"] = [request.url.host for request in transport.requests]
    remote["offered_tools"] = offered
    remote["requests"] = transport.requests
    remote["remote_called"] = any(host != "anthropic.local" for host in remote["hosts"])
    return remote


def _consume(client, session, store, messages, tools, hook, can_use_tool):
    parsed_tool_use = False
    executed: list[str] = []
    denied: list[dict] = []
    for _turn in range(8):
        message = client.messages.create(
            model=MODEL_NAME,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
        )
        assistant_blocks = []
        tool_results = []
        texts = []
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                parsed_tool_use = True
                assistant_blocks.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input)}
                )
                result_text, is_error, ran = _handle_tool(session, store, block.name, dict(block.input), hook, can_use_tool)
                if ran:
                    executed.append(block.name)
                else:
                    denied.append({"tool": block.name, "step": session.audit[-1]["step"]})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            elif isinstance(block, TextBlock):
                texts.append(block.text)
                assistant_blocks.append({"type": "text", "text": block.text})
        messages.append({"role": "assistant", "content": assistant_blocks})
        if texts:
            session.model_text = "\n".join(texts)
        if message.stop_reason != "tool_use":
            break
        messages.append({"role": "user", "content": tool_results})
    else:
        raise LabError("invalid", "turn limit reached")
    return {
        "executed": executed,
        "denied": denied,
        "sdk_parsed_tool_use": parsed_tool_use,
    }


def _kind(tool_name: str) -> str:
    if tool_name in READ_TOOLS:
        return "read"
    if tool_name in EDIT_TOOLS:
        return "edit"
    return "write"


def _handle_tool(session, store, name, arguments, hook, can_use_tool):
    decision = evaluate(
        name,
        arguments,
        mode=session.mode,
        allowed_tools=session.allowed_tools,
        disallowed_tools=session.disallowed_tools,
        ask_rules=session.ask_rules,
        hook=hook,
        can_use_tool=can_use_tool,
        kind=_kind(name),
    )
    session.audit.append(
        {
            "tool": name,
            "effect": decision.effect,
            "step": decision.step,
            "reason": decision.reason,
            "callback_invoked": decision.callback_invoked,
            "hook_runtime": decision.hook_runtime,
        }
    )
    if decision.effect != "allow":
        return json.dumps({"ok": False, "error": decision.reason}), True, False
    try:
        payload = execute(session.actor(), store, session.workspace, name, arguments)
    except LabError as exc:
        return json.dumps({"ok": False, "error": exc.message, "code": exc.code}), True, False
    if name == "request_approval":
        session.approval_id = payload["approval_id"]
    return json.dumps({"ok": True, **payload}), False, True


def _default_callback(session: Session, store: Store):
    def can_use(tool_name: str, tool_input: dict) -> bool:
        if tool_name != "record_decision":
            return False
        actor = session.actor()
        return store.record_allowed(
            str(tool_input.get("approval_id", "")),
            actor.tenant_id,
            actor.subject,
            actor.role,
            str(tool_input.get("grant_id", "")),
        )

    return can_use
