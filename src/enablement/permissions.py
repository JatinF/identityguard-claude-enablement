"""Permission evaluation in the order published by the Claude Agent SDK.

Accessed 2026-10-21:
https://code.claude.com/docs/en/agent-sdk/permissions

The Claude Code hook runtime, auto mode, and the Agent SDK process are not-run.
A hook callable, when supplied, is a local stand-in for step 1.
"""

from collections.abc import Callable
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

from enablement.errors import LabError
from enablement.gates import MCP_SERVER_NAME

HOOKS = "hooks"
DENY_RULES = "deny_rules"
ASK_RULES = "ask_rules"
PERMISSION_MODE = "permission_mode"
ALLOW_RULES = "allow_rules"
CAN_USE_TOOL = "can_use_tool"

MODES = {"default", "dontAsk", "acceptEdits", "bypassPermissions", "plan"}

ENGINEER_ALLOWED = [
    "lookup_grant",
    "read_policy",
    "request_approval",
    "mcp__identityguard__*",
]
ENGINEER_DENIED = ["read_secret", "decide_approval", "edit_workspace"]
ENGINEER_ASK = ["record_decision"]

CHILD_ALLOWED = ["lookup_grant", "read_policy"]
CHILD_DENIED = [
    "read_secret",
    "decide_approval",
    "edit_workspace",
    "request_approval",
    "record_decision",
]
CHILD_MODE = "dontAsk"

USER_INTERACTION = {"record_decision"}
READ_TOOLS = {"lookup_grant", "read_policy"}
EDIT_TOOLS = {"edit_workspace"}

Hook = Callable[[str, dict], str]
Callback = Callable[[str, dict], bool]


@dataclass(frozen=True)
class PermissionDecision:
    effect: str
    step: str
    reason: str
    callback_invoked: bool
    hook_runtime: str


def full_tool_name(tool_name: str) -> str:
    return f"mcp__{MCP_SERVER_NAME}__{tool_name}"


def split_rule(rule: str) -> tuple[str, str | None]:
    if "(" in rule and rule.endswith(")"):
        name, scope = rule.split("(", 1)
        return name, scope[:-1]
    return rule, None


def _glob(pattern: str) -> bool:
    return any(mark in pattern for mark in "*?")


def rule_matches(rule: str, tool_name: str, tool_input: dict, *, allow: bool) -> bool:
    name, scope = split_rule(rule)
    full = full_tool_name(tool_name)
    if _glob(name):
        if allow:
            prefix = f"mcp__{MCP_SERVER_NAME}__"
            if not name.startswith(prefix):
                return False
            server_segment = name[len("mcp__") :].split("__", 1)[0]
            if _glob(server_segment):
                return False
            name_ok = fnmatch(full, name)
        else:
            name_ok = fnmatch(tool_name, name) or fnmatch(full, name)
        if not name_ok:
            return False
    elif name not in {tool_name, full}:
        return False
    if scope is None:
        return True
    target = str(tool_input.get("path") or tool_input.get("target") or "")
    normalized = target.replace("\\", "/")
    base = PurePosixPath(normalized).name if normalized else ""
    return fnmatch(normalized, scope) or fnmatch(base, scope)


def tool_removed(tool_name: str, disallowed_tools: list[str]) -> bool:
    for rule in disallowed_tools:
        _name, scope = split_rule(rule)
        if scope is None and rule_matches(rule, tool_name, {}, allow=False):
            return True
    return False


def visible_tools(tool_names: list[str], disallowed_tools: list[str]) -> list[str]:
    return [name for name in tool_names if not tool_removed(name, disallowed_tools)]


def contained_path(path: str) -> bool:
    if not path or path.startswith(("/", "\\")) or ":" in path:
        return False
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return bool(parts) and ".." not in parts


def set_permission_mode(session, mode: str) -> str:
    if mode == "auto":
        raise LabError("invalid", "auto mode is not-run")
    if mode not in MODES:
        raise LabError("invalid", "unsupported permission mode")
    if not session.can_widen and mode in {"bypassPermissions", "acceptEdits"}:
        raise LabError("denied", "child session cannot widen permissions")
    session.mode = mode
    return mode


def evaluate(
    tool_name: str,
    tool_input: dict,
    *,
    mode: str,
    allowed_tools: list[str],
    disallowed_tools: list[str],
    ask_rules: list[str],
    hook: Hook | None = None,
    can_use_tool: Callback | None = None,
    kind: str = "write",
) -> PermissionDecision:
    if mode not in MODES:
        return _decision("deny", PERMISSION_MODE, "unsupported permission mode", False, "not-run")

    hook_runtime = "not-run"
    if hook is not None:
        hook_runtime = "local-stand-in"
        if hook(tool_name, tool_input) == "deny":
            return _decision("deny", HOOKS, "hook denied the call", False, hook_runtime)

    if any(rule_matches(rule, tool_name, tool_input, allow=False) for rule in disallowed_tools):
        return _decision("deny", DENY_RULES, "deny rule matched", False, hook_runtime)

    asks = tool_name in USER_INTERACTION or any(
        rule_matches(rule, tool_name, tool_input, allow=False) for rule in ask_rules
    )
    if asks:
        if mode == "dontAsk":
            return _decision("deny", ASK_RULES, "dontAsk denies prompts", False, hook_runtime)
        return _callback(can_use_tool, tool_name, tool_input, hook_runtime, "user interaction")

    if mode == "bypassPermissions":
        return _decision("allow", PERMISSION_MODE, "bypassPermissions approved the call", False, hook_runtime)

    if mode == "acceptEdits" and (kind == "edit" or tool_name in EDIT_TOOLS):
        path = str(tool_input.get("path") or "")
        if contained_path(path):
            return _decision("allow", PERMISSION_MODE, "acceptEdits approved a workspace edit", False, hook_runtime)

    if mode == "plan" and (kind == "edit" or tool_name in EDIT_TOOLS):
        return _callback(can_use_tool, tool_name, tool_input, hook_runtime, "plan mode does not auto-approve edits")

    if any(rule_matches(rule, tool_name, tool_input, allow=True) for rule in allowed_tools):
        return _decision("allow", ALLOW_RULES, "allow rule matched", False, hook_runtime)

    if kind == "read" or tool_name in READ_TOOLS:
        return _decision("allow", ALLOW_RULES, "read needs no approval", False, hook_runtime)

    if mode == "dontAsk":
        return _decision("deny", CAN_USE_TOOL, "dontAsk skipped the callback", False, hook_runtime)

    return _callback(can_use_tool, tool_name, tool_input, hook_runtime, "permission mode fell through")


def _callback(callback, tool_name, tool_input, hook_runtime, why: str) -> PermissionDecision:
    if callback is None:
        return _decision("deny", CAN_USE_TOOL, "no canUseTool callback", False, hook_runtime)
    approved = bool(callback(tool_name, tool_input))
    if approved:
        return _decision("allow", CAN_USE_TOOL, f"canUseTool approved the call ({why})", True, hook_runtime)
    return _decision("deny", CAN_USE_TOOL, f"canUseTool denied the call ({why})", True, hook_runtime)


def _decision(effect: str, step: str, reason: str, callback_invoked: bool, hook_runtime: str) -> PermissionDecision:
    return PermissionDecision(effect, step, reason, callback_invoked, hook_runtime)
