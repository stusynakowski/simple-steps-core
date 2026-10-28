"""examples/kernel_session.py, the walkthrough in docs/design/kernel-session.md,
runs and does what the guide says."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples"))

import kernel_session as ex  # noqa: E402

from simple_steps_core import Kernel  # noqa: E402


def test_the_walkthrough_runs(capsys):
    ex.main()
    out = capsys.readouterr().out
    assert "same spec: True" in out and "missing_step" in out
    assert "same id: True | same run: True" in out


def test_declaring_runs_nothing_and_a_value_is_born_completed():
    k = ex.build()
    assert k.needs_run() == {n: "staged" for n in ("p", "sick", "f", "side", "beds")}
    assert k.step("limit").state == "completed"


def test_moving_a_control_makes_exactly_its_readers_stale():
    k = ex.build()
    k.run_all()
    k["limit"] = 37.0
    assert k.needs_run() == {"sick": "stale: limit changed", "f": "stale: sick is stale",
                             "side": "stale: sick is stale", "beds": "stale: sick is stale"}
    k.run_all()
    assert k.step("sick").data["name"].tolist() == ["Ben", "Cy"]
    assert k.step("beds").data["value"].tolist() == ["B-B", "B-C"]


def test_a_saved_session_reloads_and_reruns_to_the_same_data():
    k = ex.build()
    k.run_all()
    loaded = Kernel.from_json(k.to_json(), ex.CATALOG)
    assert loaded.spec == k.spec
    loaded.run_all()
    for step in ("sick", "f", "side", "beds"):
        assert loaded.step(step).data.equals(k.step(step).data)


def test_a_changed_control_shows_in_the_diff():
    k = ex.build()
    other = ex.build()
    other["limit"] = 36.0
    steps = k.diff(other)["steps"]
    assert steps["limit"] == "recipe"
    assert steps["sick"] == "input limit"
