"""Reference answers for the 60-minute workshop. CI executes these checks."""

from enablement.catalog import SECRET_MATERIAL

LAB_SECTIONS = [
    {"minute_start": 0, "minute_end": 10, "title": "Requirements"},
    {"minute_start": 10, "minute_end": 25, "title": "Implementation"},
    {"minute_start": 25, "minute_end": 40, "title": "Tests"},
    {"minute_start": 40, "minute_end": 50, "title": "Review"},
    {"minute_start": 50, "minute_end": 60, "title": "CI"},
]

REQUIRED_CONTROLS = [
    "scoped tool permissions",
    "authenticated MCP tools",
    "human approval before a write",
    "sub-agent permission boundary",
    "completion follows the store",
]

SAMPLE_DIFF = """
@@ review.py
+@app.post("/v1/reviews")
+def open_review():
+    print("SYN-SECRET-DO-NOT-RETURN")
+    return {"completion_claimed": True}
""".replace("SYN-SECRET-DO-NOT-RETURN", SECRET_MATERIAL)

CLEAN_DIFF = """
@@ review.py
+@app.post("/v1/reviews")
+def open_review(actor=Depends(require_actor)):
+    if approval["status"] != "approved":
+        return {"completion_claimed": False}
+    return {"completion_claimed": True}
"""

CI_NEEDLES = [
    "ubuntu-24.04",
    'python-version: "3.12"',
    "pytest",
    "actions/checkout@v5",
    "actions/setup-python@v6",
]


def lab_duration_minutes() -> int:
    return sum(item["minute_end"] - item["minute_start"] for item in LAB_SECTIONS)


def tenant_can_read(actor_tenant: str, record_tenant: str) -> bool:
    """Workshop implementation exercise. A caller sees only their tenant."""
    return actor_tenant == record_tenant and actor_tenant != ""


def review_diff(diff: str) -> list[str]:
    """Workshop review exercise. Findings are labels, not a rewrite of the diff."""
    findings = []
    if SECRET_MATERIAL in diff:
        findings.append("secret_exposure")
    added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+"))
    if "@app." in added and "require_actor" not in diff and "authorization" not in diff.lower():
        findings.append("missing_auth")
    claims_complete = "completion_claimed" in diff and "True" in diff
    guards_approval = 'status"] != "approved"' in diff or "status == \"approved\"" in diff
    if claims_complete and not guards_approval:
        findings.append("unguarded_completion")
    return findings


def validate_ci(workflow_text: str) -> list[str]:
    """Workshop CI exercise. Returns the required snippets that are absent."""
    return [needle for needle in CI_NEEDLES if needle not in workflow_text]
