---
name: video-transcript-pipeline
description: Build and test a simple-steps-core service that reads media from a shared filesystem, transcribes it, runs LLM operations over each item, and writes a stratified summary table. Use this skill whenever the user is working on a media/transcript/LLM pipeline in a repo that depends on simple-steps-core — transcribing video or audio, fanning an LLM call out across many files, grouping results into strata, or standing the whole thing up behind Server().run(). Also use it when they ask how to test such a pipeline without hitting real models, since the fake-resource patterns here are the intended approach.
---

# Video transcript pipeline

A pipeline that turns a folder of video into one summary table, in five moves:

```
videos-list        a Collection of MediaAsset handles from the shared filesystem
  → map transcribe     one transcript per video      (slow, I/O bound, can fail)
  → map analyze        LLM summary + label per item  (slow, I/O bound, can fail)
  → to_table           the per-video rows as a frame
  → group / map        one row per stratum → the output table
```

`assets/tools_template.py` is this pipeline as working code and
`assets/test_pipeline_template.py` is its test suite. Both run green. Copy them
and replace the two `_build_*` stubs — that is faster and less error-prone than
writing it from scratch, and the rest of this document explains the decisions
baked into them.

## The six rules that are easy to get wrong

Each of these is a silent-wrong-answer trap rather than an error you'd notice.

**1. Hand a video's *path* to the transcriber, never `asset.open()`.**
`MediaAsset.open()` decodes images and deliberately raises on video. A
transcription client wants a path or bytes:

```python
text = transcriber.transcribe(video.path)      # or video.read_bytes()
```

**2. A source tool returns a `Collection`, not a list of decoded anything.**
Video files are large and the shared filesystem changes underneath you. Return
handles plus a cheap `version` stamp, so the step stores a recipe and a
snapshot stays small:

```python
@videos.tool("list")
def list_videos(pattern: str = "**/*.mp4", root = Resource()) -> Collection:
    paths = sorted(root.glob(pattern))
    newest = max((p.stat().st_mtime_ns for p in paths), default=0)
    return ListCollection(items=[MediaAsset.from_path(p) for p in paths],
                          version=f"n:{len(paths)}:mtime:{newest}")
```

**3. Consume `step.ok`, not the whole `MapResult`.** A `map` returns per-item
outcomes. Referencing `step2` downstream hands the next step the wrapper;
`step2.ok` hands it the successful values:

```python
orchestration=OrchestrationConfig(mode="map", over="step2.ok")
```

**4. Group returns `Groups`, whose items are records — use `.key` and `.rows`.**
This is what makes the stratified table possible: the per-stratum tool needs
both the label and the rows to write its output row.

```python
def summarize_stratum(group) -> dict:
    return {"topic": group.key, "videos": len(group),
            "total_words": int(group.rows["words"].sum())}
```

**5. Name steps `step1`, `step2`, … — the reference grammar requires it.**
Only tokens starting with `step` resolve; `over="s1"` is a literal string, not
a reference. That now raises a clear error instead of fanning out over the
*characters* of the string, but the fix is the naming.

**6. A DataFrame's rows arrive as plain dicts.** Orchestrating over a frame
iterates rows (not column names), and `filter`/`group` hand back frames. So a
per-row tool is `def topic_of(row: dict) -> str: return row["topic"]` — no
pandas import needed in the tool.

## Resources: one per external dependency, injected

Three resources, each a `ResourceSpec` owning the tools that use it. Bound tool
ids are namespaced `{resource}-{tool}`, and a bound tool may use **its own
resource and no other** — that rule is enforced at import time, and it is what
makes the fakes in testing drop in cleanly.

```python
videos        = ResourceSpec("videos",      factory=_video_root, check=lambda r: r.is_dir())
transcription = ResourceSpec("transcriber", factory=_build_transcriber)
llm_ops       = ResourceSpec("llm",         factory=_build_llm)

RESOURCES = [videos, transcription, llm_ops]     # the server/dashboard read this
```

Keep the model clients behind **small interfaces you define** —
`transcriber.transcribe(path) -> str`, `llm.complete(prompt) -> str` — rather
than importing a vendor SDK into the tool. Two payoffs: swapping providers
touches one factory, and tests substitute a fake at the same seam with no
mocking library and no network.

Write the LLM tool as `async def` when the client is async; the engine awaits it
and `concurrency` then runs real parallel calls. A sync client is fine too —
sync tools are run off the event loop in a thread, so `concurrency` still
applies.

## Failure policy: collect, don't abort

One unreadable video should not waste an hour of transcription. Set this per
step and read both halves afterwards:

```python
execution=StepExecutionConfig(concurrency=4, retries=1, on_item_error="collect")
```

- `step.ok` — the values that worked, which the table is built from.
- `step.failed` — outcomes carrying `index` and `error`, to inspect or re-drive.

`retries=1` means a failing item is attempted twice. Tune `concurrency` to the
model's rate limit, not to the machine's cores — these are I/O-bound calls.

## Testing

Full patterns in `references/testing.md`; read it when writing the tests. The
short version, because it's the part people skip:

**Fake at the resource boundary.** Register a fake object for the resource name
and the real tools run unchanged:

```python
app.register_resource("transcriber", lambda: FakeTranscriber(texts))
app.register_resource("llm", lambda: FakeLLM())
```

**Make fakes observable and fallible.** A fake that records its calls
(`self.calls`) lets you assert the transcriber got *paths*, and that retries
actually retried. A fake that fails on one named input lets you test the
partial-failure path — which is the behavior that matters most in production
and the one that never gets exercised by a happy-path test.

**Write real files, not mocks, for the filesystem.** `tmp_path` with a few
byte-sized `.mp4` files exercises the real glob, the real `MediaAsset`, and the
real version stamp, at no cost.

**Assert on both halves of a fan-out.** `len(result.ok) == 2 and
len(result.failed) == 1` says more than a happy-path row count.

**Check the wiring cheaply**: `wf.missing_resources() == []` catches a resource
that no one registered, before anything runs.

## Standing it up

```python
CONFIG = {"title": "video pipeline", "port": 8000}
RESOURCES = [videos, transcription, llm_ops]

if __name__ == "__main__":
    from simple_steps_core.serving import Server
    Server().run()
```

`python tools.py` serves it; `GET /tools` lists the contracts and `POST /run`
takes `{"steps": [...]}`. For a visual run instead, swap in
`from simple_steps_core.streamlit import Dashboard` and `Dashboard().run()` —
the grid shows the video handles, the per-item fan-out, and one tab per stratum.

Needs `pip install "simple-steps-core[api]"` (or `[dashboard]`).

## Where to look next

- `assets/tools_template.py` — the pipeline, ready to copy.
- `assets/test_pipeline_template.py` — its seven tests, ready to copy.
- `references/testing.md` — fakes, fixtures, and what to assert.
- The `simple-steps-core` skill in the library's own repo covers the general
  framework (resources, orchestration modes, references, guardrails, tool UI).
  This skill is only the media/LLM slice.
