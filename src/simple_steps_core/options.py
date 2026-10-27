"""How core reads a formula: settings that will become kernel options.

Moved from grid.py unchanged (phase 2 of docs/design/cleanup-plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
import os


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class Settings:
    """Environment settings for how core reads a formula (009 §8).

    ``implicit_auto``: when on (the default), a step written with no
    orchestration — ``score(wf["r"])`` — gets auto (saved as ``mod.auto()``),
    and a direct call on a frame that doesn't fit as-is runs over its rows.
    When off, auto must be written: ``score[mod.auto()](wf["r"])``. Set it
    here, or with the environment variable ``SIMPLE_STEPS_IMPLICIT_AUTO=0``.
    """

    implicit_auto: bool = True


#: ``grid.settings.implicit_auto = False`` turns implicit auto off.
settings = Settings(implicit_auto=_env_flag("SIMPLE_STEPS_IMPLICIT_AUTO", True))
