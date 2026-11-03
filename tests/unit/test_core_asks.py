"""The core asks: every test in docs/design/core-asks/plan.md, run in the suite.

The tests themselves live in ``docs/design/core-asks/probe.py`` (the probe the
owner runs, PASS / FAIL per milestone); this file runs the same functions under
pytest. A test that holds today is a plain test ("keep green" in plan.md). One
that waits for its step of phase4-plan.md is ``xfail(strict=True)`` naming the
step, so it fails loudly the day it starts to hold and the mark comes off:
move its ID into ``HOLDS`` in the same commit.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PROBE = Path(__file__).resolve().parents[2] / "docs" / "design" / "core-asks" / "probe.py"
_spec = importlib.util.spec_from_file_location("core_asks_probe", _PROBE)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

#: Tests that pass (2026-11-02, from 6d9557c; S1 adds as it lands). Everything else waits.
HOLDS = frozenset({
    "TEST-L1", "TEST-L2", "TEST-L3a", "TEST-L3b", "TEST-L3c", "TEST-L3d", "TEST-L3e",
    "TEST-L4", "TEST-L5", "TEST-L5b",                         # M0
    "TEST-L7c",                                               # M1
    "TEST-L11b", "TEST-L14c", "TEST-L19",                    # M2
    "TEST-L20", "TEST-L21a", "TEST-L21b", "TEST-L24",         # M3
    "TEST-L27", "TEST-L28", "TEST-L31b",                     # M4
    "TEST-L38", "TEST-L39",                                   # M5
    "TEST-L43a", "TEST-L43b", "TEST-L43c",                   # M6
})

#: The phase4-plan.md step that makes a milestone's tests pass.
STEP = {"M0": "S1", "M1": "S5", "M2": "S5", "M3": "S4", "M4": "S3", "M5": "S3", "M6": "S11"}
#: Tests whose step isn't their milestone's.
STEP_OF = {"TEST-L21a": "S2", "TEST-L21b": "S2", "TEST-L41a": "S5", "TEST-L41b": "S5"}


def _cases():
    for milestone, tid, title, fn in probe.TESTS:
        marks = []
        if tid not in HOLDS:
            step = STEP_OF.get(tid, STEP[milestone])
            marks.append(pytest.mark.xfail(strict=True, reason=f"{step} ({milestone}): {title}"))
        yield pytest.param(fn, id=tid.replace("TEST-", "").replace(" ", "-"), marks=marks)


@pytest.mark.parametrize("fn", _cases())
def test_core_ask(fn):
    try:
        fn()
    except probe.Skip as e:
        pytest.skip(str(e))
    except (probe.Fail, probe.Refused) as e:
        pytest.fail(f"{type(e).__name__}: {e}", pytrace=False)
