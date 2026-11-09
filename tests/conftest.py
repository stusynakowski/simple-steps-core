"""Every test is checked for the airtight invariants (docs/design/reshaping.md §2.1).

Each step that runs, in any test, is checked right after it runs, against the
plan it had before (A6). A test fails on any break, so an edge case that
leaks shows up where it happens. Mark a test ``@pytest.mark.no_invariants``
only when it builds a broken state on purpose.
"""

from __future__ import annotations

import faulthandler
import os
import re
import signal
import subprocess
from datetime import date
from pathlib import Path

import pytest

from simple_steps_core.workflow import Workflow

#: Checks not yet enforced, with the step of docs/design/reshaping-plan.md
#: that enforces them. Empty: every check is enforced.
PENDING: dict[str, str] = {}


def pytest_configure(config):
    config.addinivalue_line("markers", "no_invariants: don't check the airtight invariants")
    # `kill -USR1 <pid>` dumps every thread's stack and the run goes on: sample a
    # slow run as often as needed to see where it spends its time
    # (tests/stress-failures.md, Hangs)
    faulthandler.register(signal.SIGUSR1, all_threads=True)


@pytest.fixture(autouse=True)
def _airtight(monkeypatch, request):
    if request.node.get_closest_marker("no_invariants"):
        yield
        return
    broken: list[str] = []
    run_step = Workflow._run_step

    def checked(self, step_id, *args, **kwargs):
        before = self.steps[step_id].output
        plan = before.meta.get("plan") if before.meta.get("staged") else None
        step = run_step(self, step_id, *args, **kwargs)
        broken.extend(self.check_invariants(step_id, plan))
        broken.extend(self.filed_unchanged())
        return step

    monkeypatch.setattr(Workflow, "_run_step", checked)
    yield
    enforced = [b for b in dict.fromkeys(broken) if b.split()[0] not in PENDING]
    assert not enforced, "airtight invariants broken:\n  " + "\n  ".join(enforced)


# ── every property-test failure goes on a list ─────────────────────────────
#: The property tests' failures, one entry per shrunk example, oldest first.
STRESS_FAILURES = Path(__file__).parent / "stress-failures.md"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed and item.path.name == "test_reshape_properties.py":
        _log_stress_failure(item.name, report.longreprtext)


def _log_stress_failure(test: str, text: str) -> None:
    """Append one failure to stress-failures.md: what broke and the example
    that shows it. An example already listed (hypothesis replays it) isn't
    added again."""
    lines = [line[1:].strip() if line.startswith("E") else line for line in text.splitlines()]
    start = next((i for i, line in enumerate(lines)
                  if line.startswith(("Failing test case:", "Falsifying example:"))), None)
    example = []
    if start is not None:
        example.append(lines[start].split(":", 1)[1].strip())   # "test_x(" shares the line
        for line in lines[start + 1:]:
            example.append(line)
            if line.strip() == ")":
                break
    example_text = "\n".join(example).strip()
    what = next((line for line in lines if line.startswith(("AssertionError", "assert", "Left "))),
                None) or next((line for line in reversed(lines)          # a crash: its error
                               if re.match(r"\w+(Error|Exception): ", line)), "see the test output")
    found = STRESS_FAILURES.read_text() if STRESS_FAILURES.exists() else ""
    if example_text and example_text in found:
        return
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, cwd=STRESS_FAILURES.parent).stdout.strip()
    except OSError:
        commit = "?"
    entry = (f"\n## {date.today().isoformat()} · `{test}` · at `{commit or '?'}`"
             f"{' · STRESS=1' if os.environ.get('STRESS') else ''}\n\n"
             f"- **Broke:** {what}\n- **Status:** open\n\n"
             f"```\n{example_text or 'no example printed'}\n```\n")
    with STRESS_FAILURES.open("a") as f:
        f.write(entry if found else _HEADER + entry)


_HEADER = """# Property-test failures

Every failure of the property tests (`tests/unit/test_reshape_properties.py`),
appended by `tests/conftest.py` as it happens: what broke and the shrunk
example that shows it. An example already here isn't added twice. When one is
fixed, set its status to the commit that fixed it and pin the example
(`@example(...)`) so it's checked on every run.
"""
