"""sweep.py — run every check core has, under coverage, and report.

    .venv/bin/python scripts/sweep.py            # all suites
    .venv/bin/python scripts/sweep.py --stress   # and the property test at 2,000 examples

Runs the tests, the two tutorials (tutorial/tutorial.py: every capability;
tutorial/handover.py: everything core-handover/ asked for), both examples,
scripts/core_asks.py and the core-asks probe, each under coverage. Prints each
suite's own result line, then the lines of core they ran between them, per
module. A suite that crashes is reported, and the sweep goes on.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

SUITES = [
    ("tests", ["-m", "pytest", "-p", "no:warnings", "-p", "no:cacheprovider"]),
    ("tutorial", ["tutorial/tutorial.py"]),
    ("handover", ["tutorial/handover.py"]),
    ("kernel session", ["examples/kernel_session.py"]),
    ("all orchestrations", ["examples/all_orchestrations/pipeline.py"]),
    ("core asks", ["scripts/core_asks.py"]),
    ("core-asks probe", ["docs/design/core-asks/probe.py"]),
]


def last_line(text: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip() and set(ln.strip()) != {"."}]
    return lines[-1].strip() if lines else ""


def main() -> int:
    suites = list(SUITES)
    if "--stress" in sys.argv:
        suites.insert(1, ("property test ×2000", ["-m", "pytest", "-p", "no:warnings",
                                                  "tests/unit/test_reshape_properties.py"]))
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "COVERAGE_FILE": str(Path(tmp) / ".coverage"), "STRESS": "1"}
        if "--stress" not in sys.argv:
            env.pop("STRESS")
        print(f"{'suite':22} {'exit':>4}  result")
        failed = 0
        for name, args in suites:
            run = subprocess.run([PY, "-m", "coverage", "run", "-p", *args], cwd=ROOT, env=env,
                                 capture_output=True, text=True)
            failed += run.returncode != 0
            print(f"{name:22} {run.returncode:>4}  {last_line(run.stdout) or last_line(run.stderr)}")
        subprocess.run([PY, "-m", "coverage", "combine", "-q"], cwd=ROOT, env=env)
        out = Path(tmp) / "coverage.json"
        subprocess.run([PY, "-m", "coverage", "json", "-q", "-o", str(out)], cwd=ROOT, env=env)
        files = json.loads(out.read_text())["files"]
        print(f"\nlines of core run by all of them:\n{'module':28} {'lines':>6} {'run':>6} {'cover':>6}")
        rows = sorted(((Path(f).name, d["summary"]) for f, d in files.items()),
                      key=lambda r: r[1]["percent_covered"])
        for name, sm in rows:
            print(f"{name:28} {sm['num_statements']:>6} {sm['covered_lines']:>6} "
                  f"{sm['percent_covered']:>5.0f}%")
        statements = sum(sm["num_statements"] for _, sm in rows)
        covered = sum(sm["covered_lines"] for _, sm in rows)
        print(f"{'total':28} {statements:>6} {covered:>6} {100 * covered / statements:>5.0f}%")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
