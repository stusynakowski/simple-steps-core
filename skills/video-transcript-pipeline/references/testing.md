# Testing a media + LLM pipeline

The hard part of testing this kind of pipeline is not the assertions — it is
arranging for the expensive, non-deterministic parts (a transcription model, an
LLM) to be absent without the test becoming a test of mocks. The resource
system already gives you the seam; this file is how to use it.

Contents:

- [The seam: fake the resource, run the real tools](#the-seam)
- [Writing a useful fake](#writing-a-useful-fake)
- [Fixtures](#fixtures)
- [What to assert](#what-to-assert)
- [Testing over HTTP](#testing-over-http)
- [When you do want the real model](#when-you-do-want-the-real-model)

## The seam

A tool declares its dependency with `Resource()`, and the engine injects
whatever is registered under that name. So a test registers a fake and every
tool runs its real code:

```python
app = App(AppConfig(orchestrators=True, freeze=False), registry=REGISTRY)
app.register_resource("videos", lambda: video_root)      # a real tmp dir
app.register_resource("transcriber", lambda: FakeTranscriber(texts))
app.register_resource("llm", lambda: FakeLLM())
```

Nothing is patched and no mocking library is involved. The tool bodies, the
orchestration, the reference resolution, the frame handling and the grouping
are all exercised for real — only the two external services are stand-ins.

This is also why the "a bound tool may use only its own resource" rule earns
its keep: each tool has exactly one seam, so there is exactly one thing to
substitute.

## Writing a useful fake

A fake that only returns canned values tests less than it could. Two extra
properties make it pull its weight.

**It records what it was asked.** This is how you assert that the transcriber
received a *path* rather than a decoded image, and that `retries=1` really
retried:

```python
class FakeTranscriber:
    def __init__(self, texts, fail_on=()):
        self.texts, self.fail_on, self.calls = texts, set(fail_on), []

    def transcribe(self, path: str) -> str:
        name = path.rsplit("/", 1)[-1]
        self.calls.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"decode failed: {name}")
        return self.texts[name]
```

```python
assert transcriber.calls.count("b.mp4") == 2      # retried once
assert transcriber.calls.count("a.mp4") == 1      # the good ones, once
```

**It can fail on demand.** Partial failure is the normal case in a batch of a
thousand videos, and it is the behavior a happy-path test never reaches.
`fail_on=["b.mp4"]` turns that into a one-line setup.

For an async client, make the fake async too — the engine awaits the tool, and
the fake has to match:

```python
class FakeLLM:
    async def complete(self, prompt: str) -> str:
        ...
```

Keep fake outputs **deterministic and derived from the input** (`f"summary of
{len(body.split())} words"`), so assertions are about wiring rather than about
model wording.

## Fixtures

Write real files. A shared filesystem of video is just a directory, and
`tmp_path` makes a real one for a fraction of a millisecond:

```python
@pytest.fixture
def video_root(tmp_path):
    root = tmp_path / "shared"
    root.mkdir()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (root / name).write_bytes(b"fake video bytes")
    return root
```

The bytes are nonsense, and that is fine — nothing decodes them, because the
transcriber is faked and `MediaAsset.from_path` only stats the file. You get
the real glob, the real handles, and a real version stamp.

If a tool *does* need a decodable file, `PIL.Image.new(...).save(path)` makes a
real image just as cheaply.

## What to assert

Ordered by how much they catch:

**Both halves of every fan-out.** The count of successes alone hides a silently
failing item:

```python
assert len(transcripts.ok) == 2
assert len(transcripts.failed) == 1
assert "b.mp4" in transcripts.failed[0].error
```

**The final table's content, not just its shape.** One row per stratum, with
the aggregate you expect:

```python
birds = table[table["topic"] == "birds"].iloc[0]
assert birds["videos"] == 2
assert birds["total_words"] == 7
```

**That failures are excluded from the table**, which is the actual contract of
`on_item_error="collect"`:

```python
assert set(wf["step7"].output.value["topic"]) == {"birds"}
```

**Wiring, before anything runs.** `wf.missing_resources() == []` catches a
resource nobody registered. `wf.validate()` additionally checks that tools
exist and references resolve in order — cheap, and it fails with a readable
table rather than a `KeyError` mid-run.

**The source is still lazy.** If it matters that listing did not read
everything:

```python
assert listing.count() == 3
assert listing.version.startswith("n:3:")
```

## Testing over HTTP

To test the served surface rather than the workflow objects, build the app from
your tools module and drive it with FastAPI's test client — no server process:

```python
import types
from fastapi.testclient import TestClient
from simple_steps_core.serving import app_from_module

module = types.SimpleNamespace(CONFIG={"freeze": False}, RESOURCES=[videos, fake_specs...])
app, config = app_from_module(module)
client = TestClient(app)

assert client.get("/tools").status_code == 200
result = client.post("/run", json={"steps": [
    {"step_id": "step1", "name": "videos-list", "arguments": {"pattern": "*.mp4"}},
    {"step_id": "step2", "name": "transcriber-transcribe",
     "orchestration": {"mode": "map", "over": "step1"}},
]})
assert [s["status"] for s in result.json()["steps"]] == ["completed", "completed"]
```

**Step ids must start with `step`.** The reference grammar only resolves tokens
matching `step*`, so `over: "s1"` is a *literal string*, not a reference to a
step called `s1`. Fanning out over one now raises a clear `TypeError` rather
than iterating the string character by character, but the fix is to name steps
`step1`, `step2`, … (or `step_ingest`, `step_transcribe`).

`RESOURCES` accepts a list of `ResourceSpec`, so a test can pass specs built
around fakes, e.g.
`ResourceSpec("transcriber", value=FakeTranscriber(texts))`.

## When you do want the real model

Keep those tests separate and opt-in, so the default suite stays fast and
offline:

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("RUN_MODEL_TESTS"), reason="opt-in")
def test_against_the_real_transcriber():
    ...
```

Point them at one short fixture clip, assert something robust (non-empty text,
a keyword you know is spoken) rather than an exact transcript, and never assert
on exact LLM wording — model output drifts and the test becomes noise.
