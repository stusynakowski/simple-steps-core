"""
proposals.py — the agent proposes; the user disposes (docs/dev_plan/122 §3).

One turn:

1. build the scope (:mod:`.scope`): tools, resources, the workflow so far;
2. ask the model for steps to add or change, as JSON —
   ``{"summary", "steps": [{"name", "formula"}], "remove": [names]}`` — the
   "updated list of expressions". It's a far easier shape for a small local
   model than edit commands;
3. **check every formula** before the user sees it: it compiles, reads only
   earlier steps (``wf[…]``), names only usable resources (``res[…]``), and
   uses only real tools (for a resource, only its marked methods). Problems go
   back to the model for a corrected answer, up to ``Agent.retries`` times;
4. return the proposal as **changes** — use a ready-made resource, add /
   change / remove a step, each with its problem if one is left — which the
   UI applies through the same commands the console uses (``res[…] = …``,
   ``add``, ``set``, ``remove``).

The agent never runs a step, never edits the workflow itself, and never sees a
resource object: the worst it can produce is a suggestion the checks refuse.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .model import Agent, ModelError, chat_json

_NAME = re.compile(r"^[A-Za-z_][\w-]*$")

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "formula": {"type": "string"}},
                "required": ["name", "formula"],
            },
        },
        "remove": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "steps"],
}

SYSTEM_PROMPT = """\
You are the Simple Steps agent. You help a user build a workflow: an ordered \
list of steps, like rows of formulas in a spreadsheet. You PROPOSE steps; the \
user reviews them and runs them. You never run anything.

Each step has a name and one formula, in exactly this syntax:
  =tool[mod.VERB(settings)](wf["earlier_step"], argument=value)

Rules:
- wf["name"] is the only way to read another step, and only an EARLIER step.
- res["name"] is a resource (a model, a database). Use only the resources listed.
- Everything else is a literal: "text", 3, [1, 2], {"a": 1}.
- Use only the tools listed. A tool's parameters are filled from the input's \
columns with the same names, or from arguments.
- Verbs, inside the brackets:
  map (one result per row; name="col" names the new column), \
filter (keep rows where the tool returns true), expand (a list result becomes \
rows), collapse (rows into one value; by="col" for one per group), \
group (label each row; name="col"), select(columns=[...]), drop(columns=[...]), \
rename(columns={"old": "new"}), sort(by="col", ascending=False), slice(stop=2), \
distinct(columns=[...]), widen(columns=[...]), source() (no input: runs once).
- A verb that applies no tool uses identity: =identity[mod.select(columns=["n"])](wf["readings"])
- New data from literals: =to_rows[mod.source()](data='{"city": ["SF", "LA"], "n": [1, 2]}')
- A resource's own tool: =res["db"].lookup[mod.map()](wf["keys"])
- A tool that needs a resource: =summarize[mod.map()](wf["notes"], llm=res["llm"])
- Combine steps: =join(wf["a"], wf["b"], on="key", how="left"), =stack(wf["a"], wf["b"]), \
=zip_(wf["a"], wf["b"])

Answer with JSON only:
{"summary": "one or two sentences: what your steps do, or the answer to a question",
 "steps": [{"name": "short_snake_case", "formula": "=..."}],
 "remove": []}
List only the steps to ADD or CHANGE, in workflow order. To change a step, \
reuse its name. Put a step's name in "remove" only if the user asks to delete \
it. If the user only asks a question, answer in "summary" with no steps.
"""


def _strip(formula: str) -> str:
    return (formula or "").strip().lstrip("=").strip()


def _usable_resources(workflow_resources: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Every resource a formula may name, with a declaration for its type."""
    from ..resources import LOADED
    usable = {name: dict(decl) for name, decl in (workflow_resources or {}).items()}
    for name, loaded in LOADED.items():
        usable.setdefault(name, {"source": "loaded", "type": loaded.type.__name__})
    return usable


def _final_order(existing: List[str], proposed: List[Dict[str, str]], removed: List[str]) -> List[str]:
    """Step names after the proposal: changed steps stay put; a new step goes
    after the step before it in the proposal (or at the end)."""
    order = [n for n in existing if n not in removed]
    anchor: Optional[str] = order[-1] if order else None
    for step in proposed:
        name = step["name"]
        if name in order:
            anchor = name
            continue
        index = order.index(anchor) + 1 if anchor in order else len(order)
        order.insert(index, name)
        anchor = name
    return order


def check_step(step: Dict[str, str], earlier: List[str],
               resources: Mapping[str, Dict[str, Any]], existing: bool = False) -> Optional[str]:
    """Why *step* can't be used, or None. *earlier*: the steps it may read.
    *existing*: it changes a step that's already there, whose name (a UI label
    such as "Step 1") is kept as it is."""
    from simple_steps_core import grid
    from ..decorators import OPERATION_REGISTRY
    from ..operation_formula import FormulaError, compile_formula, is_canonical
    from ..resources import ResourceError, resource_type

    name, formula = step.get("name", ""), step.get("formula", "")
    if not existing and not _NAME.match(name or ""):
        return f"{name!r} isn't a usable step name (letters, digits and _, starting with a letter)"
    if not _strip(formula):
        return "the formula is empty"
    if not is_canonical(formula):
        return 'the formula must use the syntax tool[mod.verb()](wf["step"], …); it names no step or verb'
    try:
        compiled = compile_formula(formula)
    except FormulaError as exc:
        return str(exc)
    for ref in compiled.reads:
        if ref not in earlier:
            shown = ", ".join(earlier) or "none"
            return f'reads wf["{ref}"], which isn\'t an earlier step (earlier steps: {shown})'
    for res in compiled.resources:
        if res not in resources:
            shown = ", ".join(f'res["{r}"]' for r in resources) or "none"
            return f'uses res["{res}"], which this workflow doesn\'t have (it has: {shown})'
    if compiled.is_combine:
        return None
    if compiled.bound_to:
        try:
            cls = resource_type(resources[compiled.bound_to], compiled.bound_to)
        except ResourceError as exc:
            return str(exc)
        tools = grid.resource_entry(cls).get("tools", {})
        if f"{cls.__name__}.{compiled.tool_id}" not in tools:
            shown = ", ".join(t.split(".", 1)[1] for t in tools) or "none"
            return f"{compiled.tool_id} is not a tool of {cls.__name__}; its tools are: {shown}"
        return None
    if compiled.tool_id not in OPERATION_REGISTRY and compiled.tool_id not in grid.BUILTIN_TOOLS:
        return f"there's no tool named {compiled.tool_id}"
    return None


def check_proposal(proposed: List[Dict[str, str]], removed: List[str],
                   existing: List[str], resources: Mapping[str, Dict[str, Any]]) -> Dict[str, str]:
    """``{step name: problem}`` for every proposed step that can't be used."""
    problems: Dict[str, str] = {}
    seen = set()
    for step in proposed:
        if step["name"] in seen:
            problems[step["name"]] = "the proposal lists this step twice"
        seen.add(step["name"])
    order = _final_order(existing, proposed, removed)
    for step in proposed:
        if step["name"] in problems:
            continue
        earlier = order[: order.index(step["name"])] if step["name"] in order else list(order)
        problem = check_step(step, earlier, resources, existing=step["name"] in existing)
        if problem:
            problems[step["name"]] = problem
    for name in removed:
        if name not in existing:
            problems[f"remove:{name}"] = f"there's no step named {name} to remove"
    return problems


def _parse(answer: Mapping[str, Any]) -> Tuple[str, List[Dict[str, str]], List[str]]:
    summary = str(answer.get("summary") or "").strip()
    steps = []
    for item in answer.get("steps") or []:
        if isinstance(item, dict) and item.get("name"):
            formula = _strip(str(item.get("formula") or ""))
            steps.append({"name": str(item["name"]).strip(), "formula": f"={formula}" if formula else ""})
    removed = [str(n).strip() for n in answer.get("remove") or [] if str(n).strip()]
    return summary, steps, removed


def _ready_made_to_use(proposed: List[Dict[str, str]], workflow_resources: Mapping[str, Any],
                       problems: Mapping[str, str]) -> List[Dict[str, Any]]:
    """Ready-made resources the proposal uses that the workflow doesn't list yet.

    A step can only run with a resource its workflow's ``resources`` section
    declares, so the proposal adds the declaration first — the same
    ``res["x"] = Type(…)`` the Resources menu and the console send.
    """
    from ..operation_formula import FormulaError, compile_formula
    from ..resources import LOADED

    wanted: List[str] = []
    for step in proposed:
        if step["name"] in problems:
            continue
        try:
            names = compile_formula(step["formula"]).resources
        except FormulaError:
            continue
        wanted += [n for n in names if n in LOADED and n not in (workflow_resources or {})]
    out = []
    for name in dict.fromkeys(wanted):
        loaded = LOADED[name]
        settings = ", ".join(f"{k}={v!r}" for k, v in loaded.visible.items())
        out.append({"kind": "resource", "name": name,
                    "definition": f"{loaded.type.__name__}({settings})", "problem": None})
    return out


def changes(proposed: List[Dict[str, str]], removed: List[str],
            existing: Mapping[str, str], problems: Mapping[str, str],
            workflow_resources: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """The proposal as the UI shows it, in the order to apply it: ready-made
    resources to add to the workflow, then add / change / remove steps."""
    names = list(existing)
    order = _final_order(names, proposed, removed)
    out: List[Dict[str, Any]] = _ready_made_to_use(proposed, workflow_resources or {}, problems)
    for step in proposed:
        name = step["name"]
        if name in existing:
            if _strip(existing[name]) == _strip(step["formula"]):
                continue                      # unchanged: nothing to apply
            out.append({"kind": "change", "name": name, "formula": step["formula"],
                        "before": existing[name], "problem": problems.get(name)})
        else:
            i = order.index(name)
            out.append({"kind": "add", "name": name, "formula": step["formula"],
                        "after": order[i - 1] if i > 0 else None, "problem": problems.get(name)})
    for name in removed:
        out.append({"kind": "remove", "name": name, "problem": problems.get(f"remove:{name}")})
    return out


def propose(agent: Agent, message: str, steps: List[Mapping[str, Any]],
            workflow_resources: Mapping[str, Any], history: List[Mapping[str, str]],
            session_id: Optional[str]) -> Dict[str, Any]:
    """One agent turn: a checked proposal for *message*."""
    from .scope import catalog_text, resources_text, workflow_text

    existing = {str(s.get("name")): str(s.get("formula") or "") for s in steps if s.get("name")}
    resources = _usable_resources(workflow_resources)
    scope = "\n\n".join([catalog_text(), resources_text(workflow_resources),
                         workflow_text(list(steps), session_id)])
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Here is what you can use and the workflow so far.\n\n{scope}"},
        {"role": "assistant", "content": '{"summary": "Understood.", "steps": [], "remove": []}'},
    ]
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": str(turn["content"])[:2000]})
    messages.append({"role": "user", "content": message})

    summary, proposed, removed, problems = "", [], [], {}
    attempts = 0
    for attempts in range(1, agent.retries + 2):
        answer = chat_json(agent, messages, SCHEMA)
        summary, proposed, removed = _parse(answer)
        problems = check_proposal(proposed, removed, list(existing), resources)
        if not problems:
            break
        listed = "\n".join(f"- {k}: {v}" for k, v in problems.items())
        messages.append({"role": "assistant", "content": json.dumps(answer)})
        messages.append({"role": "user", "content":
                         f"Some steps can't be used:\n{listed}\n"
                         "Fix them and answer with the complete JSON again."})
    return {
        "summary": summary,
        "changes": changes(proposed, removed, existing, problems, workflow_resources),
        "model": agent.model,
        "attempts": attempts,
    }


__all__ = ["SCHEMA", "SYSTEM_PROMPT", "check_step", "check_proposal", "changes", "propose",
           "ModelError"]
