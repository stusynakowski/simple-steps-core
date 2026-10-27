"""Every test is checked for the airtight invariants (docs/design/reshaping.md §2.1).

Each step that runs, in any test, is checked right after it runs, against the
plan it had before (A6). A test fails on any break, so an edge case that
leaks shows up where it happens. Mark a test ``@pytest.mark.no_invariants``
only when it builds a broken state on purpose.
"""

from __future__ import annotations

import pytest

from simple_steps_core.workflow import Workflow

#: Checks not yet enforced, with the step of docs/design/reshaping-plan.md that
#: enforces them. A5 (rows of two grids meet only through a recorded match) is
#: what step 4 (R-D7) builds; until then the tests that zip unrelated steps
#: break it, and are listed in the plan.
PENDING = {"A5": "step 4"}


def pytest_configure(config):
    config.addinivalue_line("markers", "no_invariants: don't check the airtight invariants")


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
        return step

    monkeypatch.setattr(Workflow, "_run_step", checked)
    yield
    enforced = [b for b in dict.fromkeys(broken) if b.split()[0] not in PENDING]
    assert not enforced, "airtight invariants broken:\n  " + "\n  ".join(enforced)
