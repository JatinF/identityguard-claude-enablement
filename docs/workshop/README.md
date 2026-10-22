# Claude Code workshop

60-minute hands-on lab for this reference implementation. CI runs the exercises in `tests/test_workshop.py`. A Claude Code session is not-run. The gate `claude-code-session` stays not-run. The reference answers live in `src/enablement/workshop.py` so the lab is reproducible without a desktop session.

Work in a checkout of this repository. Use Python 3.12 and `pip install -e ".[dev]"`. Do not point the exercises at a hosted model.

## 0-10 Requirements

Read `docs/architecture.md` and write down the five controls the lab has to keep:

- scoped tool permissions
- authenticated MCP tools
- human approval before a write
- sub-agent permission boundary
- completion follows the store

Morgan Hale (`SYN-USER-MORGAN`) proposes `directory.read` for `SYN-APP-BILLING` as `SYN-GRANT-001`. Quinn Ade (`SYN-USER-QUINN`) is the approver. A rejected, expired, or missing approval must leave `completion_claimed` false even if a fixture sentence says the change is complete.

Exit check: you can name all five controls without looking back at this list.

## 10-25 Implementation

Implement the tenant check the tools already use:

```python
def tenant_can_read(actor_tenant: str, record_tenant: str) -> bool:
    return actor_tenant == record_tenant and actor_tenant != ""
```

The reference function is `enablement.workshop.tenant_can_read`. A caller in `tenant-a` can read a `tenant-a` record. The same caller cannot read `tenant-b`. An empty tenant cannot read anything.

Then skim `src/enablement/permissions.py`. The six steps are hooks, deny rules, ask rules, permission mode, allow rules, and `canUseTool`. Pair an allow list with `dontAsk` when the session must not widen. `allowed_tools` does not constrain `bypassPermissions`.

Exit check: `tenant_can_read("tenant-a", "tenant-b")` is false.

## 25-40 Tests

Run the focused tests:

```bash
pytest tests/test_permissions.py tests/test_mcp.py tests/test_delegation.py tests/test_api.py
```

Confirm these behaviors yourself in the output, not only the exit code:

- a missing bearer on `POST /mcp` is 401
- `dev-engineer-a` cannot call `decide_approval`
- `read_secret` returns an error and does not echo the fixture secret
- a child session stays on `dontAsk` and cannot set `acceptEdits`
- a rejected review stays `STOPPED` with `completion_claimed` false

Exit check: those five tests pass on your machine.

## 40-50 Review

Review the sample change below. Record one label for each problem you find. The labels are `secret_exposure`, `missing_auth`, and `unguarded_completion`.

```diff
@@ review.py
+@app.post("/v1/reviews")
+def open_review():
+    print("<fixture secret>")
+    return {"completion_claimed": True}
```

The reference checker is `enablement.workshop.review_diff`. It flags a fixture secret in the diff, a route with no `require_actor`, and a completion claim that does not look at an approved status. A diff that authenticates the caller and returns `completion_claimed` false unless the approval status is approved produces no findings.

Do not treat the fixture sentence "The grant change is complete." as evidence. Completion follows the store.

Exit check: the sample diff produces all three labels, and the guarded sample in `CLEAN_DIFF` produces none.

## 50-60 CI

Open `.github/workflows/ci.yml`. It must install `.[dev]` and run pytest on `ubuntu-24.04` with Python 3.12, `actions/checkout@v5`, and `actions/setup-python@v6`.

`enablement.workshop.validate_ci` returns the required snippets that are missing. On this repository it returns an empty list. `benchmarks/run_eval.py` rewrites `benchmarks/results/eval_report.json` from a local run. Commit that file only after the script prints task, tool, and safety rates from the run you just executed.

Exit check: `pytest tests/test_workshop.py tests/test_evaluations.py` passes. Deployment stays **NO-GO**. Hosted Claude and Claude Code remain not-run.
