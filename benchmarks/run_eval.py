"""Run the local suite and write benchmarks/results/eval_report.json."""

import json
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from enablement.evaluations import suite
from enablement.paths import RESULTS


def main() -> None:
    started = time.perf_counter()
    report = suite()
    report["duration_ms"] = round((time.perf_counter() - started) * 1000, 4)
    report["machine"] = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }
    report["versions"] = {
        "anthropic": version("anthropic"),
        "mcp": version("mcp"),
        "pydantic": version("pydantic"),
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"task={report['task_success_rate']} tool={report['tool_selection_rate']} "
        f"safety={report['safety_pass_rate']} regression={report['regression_match']} "
        f"duration_ms={report['duration_ms']}"
    )


if __name__ == "__main__":
    main()
