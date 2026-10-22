"""CI executes the workshop exercises. Claude Code itself is not launched."""

import importlib.util

from enablement.paths import CI_WORKFLOW, ROOT, WORKSHOP
from enablement.workshop import (
    CLEAN_DIFF,
    LAB_SECTIONS,
    REQUIRED_CONTROLS,
    SAMPLE_DIFF,
    lab_duration_minutes,
    review_diff,
    tenant_can_read,
    validate_ci,
)


def test_lab_is_sixty_minutes_and_the_doc_lists_each_section():
    assert lab_duration_minutes() == 60
    text = WORKSHOP.read_text(encoding="utf-8")
    for section in LAB_SECTIONS:
        assert section["title"] in text
        assert f"{section['minute_start']}-{section['minute_end']}" in text
    for control in REQUIRED_CONTROLS:
        assert control in text
    assert "not-run" in text


def test_requirements_and_implementation_exercises():
    assert tenant_can_read("tenant-a", "tenant-a") is True
    assert tenant_can_read("tenant-a", "tenant-b") is False
    assert tenant_can_read("", "tenant-a") is False


def test_review_exercise_flags_the_sample_and_accepts_the_guarded_diff():
    assert review_diff(SAMPLE_DIFF) == ["secret_exposure", "missing_auth", "unguarded_completion"]
    assert review_diff(CLEAN_DIFF) == []


def test_ci_exercise_matches_the_workflow_file():
    assert validate_ci(CI_WORKFLOW.read_text(encoding="utf-8")) == []


def test_permission_doc_cites_the_sdk_order_and_the_agent_sdk_process_is_absent():
    text = (ROOT / "docs" / "permission-model.md").read_text(encoding="utf-8")
    for phrase in ("Hooks", "Deny rules", "Ask rules", "Permission mode", "Allow rules", "canUseTool"):
        assert phrase in text
    assert "2026-10-21" in text
    assert "https://code.claude.com/docs/en/agent-sdk/permissions" in text
    assert "not-run" in text
    assert importlib.util.find_spec("claude_agent_sdk") is None
