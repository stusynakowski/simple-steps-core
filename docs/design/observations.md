# Key dev observations

> What working on core has shown about the design: what to keep, where the
> trouble comes from, and what would help most. First written 2026-11-03 at
> `cbef958`, after a day of fixes (`41a575a`…`d69b5f1`) and the docs
> consolidation. Add to it as the picture changes; date each entry.
> The rules themselves are in [model.md](model.md); the open choices in
> [decisions.md](decisions.md).

## What's good: keep it

| | Observation | Evidence |
|---|---|---|
| G1 | **The boundary is right.** Everything the app can do to a workflow, a `Kernel` can do in plain Python. Core owns meaning, the app owns text and UI; the app's data lives in `extras`, never read or hashed. | A workflow the app saves runs the same in a terminal ([model.md §11](model.md#11-extras-and-the-saved-file)) |
| G2 | **Rows know where they came from.** Lineage on every row, tools that never see `#` columns, and a way back for every step's plan give real provenance. | [model.md §4](model.md#4-rows-identity-position-lineage), §7 |
| G3 | **It refuses to guess.** Rows pair only through a link core recorded, and a refusal writes the fix. `null`, `absent` and `[]` stay apart. | Where pandas aligns look-alike labels silently, core refuses ([history/reshaping.md §12](history/reshaping.md)) |
| G4 | **Reproducibility is built in.** Spec ids, tool-code hashes and data versions exist; most of "is this up to date?" is already there. | `workflow.identity()`, `Kernel.id`, `Kernel.diff` |
| G5 | **The test net is the strongest asset.** The invariant check runs after every step of every test; property tests generate workflows of every verb; the probe tests every app requirement; every property-test failure is listed until fixed. | On 2026-11-03 it found two silent wrong answers and three crashes the regular tests passed ([tests/stress-failures.md](../../tests/stress-failures.md)) |
| G6 | **Failures stay per cell.** One bad row is `failed` or `blocked`, says where it failed, and the other rows run. | [model.md §6](model.md#6-verbs-and-modifiers) |

## The biggest flaws

| | Observation | Evidence |
|---|---|---|
| F1 | **Too many interacting concepts per row.** A row has an id, a row number, lineage and relations to other steps (aligned, subset, child, group). Each verb must define its ids, lineage, order, plan, way back and staleness: roughly 20 verbs × 6 properties, each a place to be wrong. | Every bug found on 2026-11-03 sat at a seam between two of them: a join that mixed position with id, an expand that got its lineage wrong |
| F2 | **The identity promise is conditional, and wasn't written down.** A pick follows its row through everything core does, but not when a source's own data changes: at the root, identity is position. Provenance is only as strong as that link. | A row inserted at the top of a source made a saved pick return another patient, silently (D-picks) |
| F3 | **State is bookkeeping, not a fact.** Staleness and validity are flags set by edits and cleared by runs, so a state depends on the order of edits, not on what the workflow is. | An expression put back stays `stale`; a reader made `invalid` loses its values; a run on a stale input says `completed` ([model.md §8](model.md#8-states-in-a-session), decision SM) |
| F4 | **One concept, many partial implementations.** "How do these two steps' rows relate?" is answered by at least five helpers (`_same_ids`, `_aligned_root`, `_matched`, `trace`, `_reaches`), each covering some cases. `workflow.py` is 2,874 lines with 114 methods, mixing pairing, lineage, staleness, running and editing. | Measured at `cbef958` |
| F5 | **Wanting to know everything before running.** Deciding from the verbs alone is a good goal, but many facts depend on the data (row counts, whether rows stayed in order), so much logic has one branch for the plan and another after the run. Each pair can disagree. | A sort's plan put `#` columns where the run didn't (`03ab207`) |
| F6 | **Decisions made case by case, not from principles.** Without a small set of first principles, each new case gets its own ruling, and the rules pile up. | Strict alignment was decided and reversed within a day (CA-11); pairing was written three ways in three documents before the consolidation |
| F7 | **A large surface to write.** Pickers, verbs, column modifiers, wrappers, conditions, several spellings of one pick, and binding inference: much for users to learn and for the app's parser to accept. | The grammar (S3) is still the largest item in [plan.md](plan.md) |

## What would help most

| | Change | Answers |
|---|---|---|
| H1 | **Derive every state** from the workflow and a store of results filed by run key (spec id + data read), never from flags: the session model | F3; [model.md §8.1](model.md#81-the-proposed-session-model-sm), decision SM |
| H2 | **One function for how two steps' rows relate**, used everywhere, replacing the five helpers | F1, F4 |
| H3 | **Fewer primitive moves.** Build more verbs from a few well-tested ones (pack, unpack, choose, reorder, match), as grouping already is a pack plus a map, so each property has to be right once per primitive, not once per verb | F1, F5 |
| H4 | **Make source identity explicit**, so provenance has no hidden condition | F2; D-picks |
| H5 | **Decide from a short list of principles.** A new case is settled by them, or the list changes; it doesn't get a rule of its own | F6 |

The foundations (G1, G2, G5) are worth keeping; the flaws are mostly
accumulated complexity in how the rules were added, which is fixable.

## Lessons

| | Observation | Date |
|---|---|---|
| L1 | **Settle the session model before the session rules.** The editing rules (M7) were written case by case: which edit sets which mark. Deciding first that states are derived from the workflow and a result store (SM) would have made most of those rules unnecessary, and avoided the F1–F4 bugs. Start from the model; let the rules follow from it | 2026-11-03 |
