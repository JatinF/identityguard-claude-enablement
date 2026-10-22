# Permission model

The evaluation order below is the order published by the Claude Agent SDK.

Source: [Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions). Accessed 2026-10-21.

`src/enablement/permissions.py` applies that order to this lab's tools. It is not the Claude Agent SDK process. `query()` is not called. The gate `claude-agent-sdk-process` stays not-run.

## Order

1. Hooks. A local hook callable can deny a call. A hook result of allow does not skip deny or ask rules. When the caller does not pass a hook, this step is not-run. The Claude Code hook runtime is not-run.
2. Deny rules. A matching deny blocks the call in every mode, including `bypassPermissions`. A bare name or a tool-name glob such as `*` or `mcp__*` removes the tool from the request. A scoped rule such as `edit_workspace(*.secret)` leaves the tool available and denies matching calls.
3. Ask rules, and tools that require a person. `record_decision` is in that set. In `dontAsk`, the call is denied and `canUseTool` is not called. In every other mode, including `bypassPermissions`, the call falls through to `canUseTool` even if an allow rule matches.
4. Permission mode.
   - `bypassPermissions` approves a call that reaches this step. `allowed_tools` does not constrain that approval.
   - `acceptEdits` approves `edit_workspace` only for a relative path inside the process-local workspace.
   - `plan` sends `edit_workspace` to `canUseTool` and does not treat an allow rule as approval.
   - `default` and `dontAsk` fall through.
   - `auto` is not-run. The lab rejects that mode.
5. Allow rules. A literal name matches. An allow glob is accepted only after the literal prefix `mcp__identityguard__`. An unanchored `*` does not approve anything. A read that needs no approval (`lookup_grant`, `read_policy`) is approved at this step.
6. `canUseTool`. `dontAsk` skips this step and denies the call. With no callback, the call is denied. The default callback approves `record_decision` only when the store has an unexpired approval from a different person.

## Session policies

| Session | Mode | Allowed | Denied | Ask |
| --- | --- | --- | --- | --- |
| Engineer | `default` | `lookup_grant`, `read_policy`, `request_approval`, `mcp__identityguard__*` | `read_secret`, `decide_approval`, `edit_workspace` | `record_decision` |
| Child | `dontAsk` | `lookup_grant`, `read_policy` | `read_secret`, `decide_approval`, `edit_workspace`, `request_approval`, `record_decision` | none |

A child copies `tenant_id`, `grant_id`, and the task text. It cannot set `bypassPermissions` or `acceptEdits`. It cannot decide the parent approval.

## What stays outside this module

- Claude Code hooks, settings.json, and the `auto` classifier.
- Critical-path shell removal and network-path read checks. This lab has no shell.
- A hosted model call. Assistant turns are fixtures parsed by the `anthropic` SDK.
