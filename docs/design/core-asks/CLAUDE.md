# Working on the core asks

- The target is `model.md`; the order of work and the tests are `plan.md`.
  Build milestone by milestone (M0 first: it stops wrong answers).
- Done means `python probe.py M<n>` prints PASS for every test in that
  milestone, and every "keep green" test still passes.
- Verify by running, never by reading docs. If a "today" result in plan.md is
  wrong, rerun the probe and correct the table.
- Never change a test's expectation to make it pass. If the model is wrong,
  say so; the owner decides, and model.md and plan.md change together.
- No silent results: refuse, or fail the cell with a reason. Never a null
  that looks like data.
- Lineage and `#<step>` are read-only and never reach a tool.
- Each behaviour change is confirmed with the owner in small pieces.
