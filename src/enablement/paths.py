"""Repository paths. parents[2] is the repository root."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results" / "eval_report.json"
WORKSHOP = ROOT / "docs" / "workshop" / "README.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
