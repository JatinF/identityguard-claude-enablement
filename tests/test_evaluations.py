"""Re-run the suite and lock it to the committed report."""

import json

from enablement.evaluations import EXPECTED_CASE_IDS, suite
from enablement.paths import RESULTS


def test_suite_passes_and_matches_the_committed_report():
    fresh = suite()
    assert fresh["task_success_rate"] == 1.0
    assert fresh["tool_selection_rate"] == 1.0
    assert fresh["safety_pass_rate"] == 1.0
    assert fresh["regression_match"] is True
    assert fresh["remote_called"] is False
    assert fresh["deployment_decision"] == "NO-GO"
    assert fresh["cost"] == "no price applied"
    assert [case["id"] for case in fresh["cases"]] == EXPECTED_CASE_IDS
    assert all(case["passed"] for case in fresh["cases"])

    committed = json.loads(RESULTS.read_text(encoding="utf-8"))
    for key in (
        "task_success_rate",
        "tool_selection_rate",
        "safety_pass_rate",
        "regression_match",
        "deployment_decision",
        "remote_called",
        "cost",
        "evidence_class",
    ):
        assert committed[key] == fresh[key]
    assert [case["id"] for case in committed["cases"]] == [case["id"] for case in fresh["cases"]]
    assert [case["passed"] for case in committed["cases"]] == [case["passed"] for case in fresh["cases"]]
    assert committed["gates"]["claude-agent-sdk-process"] == "not-run"
    assert committed["gates"]["hosted-model-run"] == "not-run"
    assert committed["machine"]["python"].startswith("3.12")
    assert committed["duration_ms"] >= 0
    assert committed["versions"]["anthropic"] == "0.75.0"
    assert committed["versions"]["mcp"] == "1.20.0"
    assert committed["versions"]["pydantic"] == "2.13.4"
