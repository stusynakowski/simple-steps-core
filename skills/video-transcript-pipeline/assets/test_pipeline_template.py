"""The pipeline end to end, with fake models. No network, no GPU, no real video."""
import pytest

from simple_steps_core import (
    App, AppConfig, Operation, OrchestrationConfig, REGISTRY,
    StepExecutionConfig, is_frame,
)

# Importing the tools module is what registers the tools: the @register_tool
# and @spec.tool decorators run at import time.
import tools  # noqa: F401


class FakeTranscriber:
    """Returns canned text per filename, and can be told to fail on one."""
    def __init__(self, texts, fail_on=()):
        self.texts, self.fail_on, self.calls = texts, set(fail_on), []

    def transcribe(self, path: str) -> str:
        name = path.rsplit("/", 1)[-1]
        self.calls.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"decode failed: {name}")
        return self.texts[name]


class FakeLLM:
    """Deterministic completions, so assertions are about wiring not wording."""
    def __init__(self, fail_on=()):
        self.fail_on, self.prompts = set(fail_on), []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        body = prompt.split("\n", 1)[1]
        if any(bad in body for bad in self.fail_on):
            raise RuntimeError("llm refused")
        if prompt.startswith("One-word topic"):
            return "birds" if "bird" in body else "weather"
        return f"summary of {len(body.split())} words"


@pytest.fixture
def video_root(tmp_path):
    root = tmp_path / "shared"
    root.mkdir()
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (root / name).write_bytes(b"fake video bytes")
    return root


@pytest.fixture
def texts():
    return {"a.mp4": "a bird sings here", "b.mp4": "rain and more rain today",
            "c.mp4": "another bird calls"}


def _app(video_root, transcriber, llm):
    app = App(AppConfig(orchestrators=True, freeze=False), registry=REGISTRY)
    app.register_resource("videos", lambda: video_root)
    app.register_resource("transcriber", lambda: transcriber)
    app.register_resource("llm", lambda: llm)
    return app


def _pipeline(app):
    """videos -> transcribe -> llm -> table -> group -> stratified table."""
    wf = app.session("test").workflow()
    wf.add(Operation(step_id="step1", name="videos-list",
                     arguments={"pattern": "*.mp4"}))
    wf.add(Operation(step_id="step2", name="transcriber-transcribe",
                     orchestration=OrchestrationConfig(mode="map", over="step1"),
                     execution=StepExecutionConfig(concurrency=4, retries=1,
                                                   on_item_error="collect")))
    wf.add(Operation(step_id="step3", name="llm-analyze",
                     orchestration=OrchestrationConfig(mode="map", over="step2.ok"),
                     execution=StepExecutionConfig(concurrency=4, retries=1,
                                                   on_item_error="collect")))
    wf.add(Operation(step_id="step4", name="to_table",
                     arguments={"rows": "step3.ok"}))
    wf.add(Operation(step_id="step5", name="topic_of",
                     orchestration=OrchestrationConfig(mode="group", over="step4")))
    wf.add(Operation(step_id="step6", name="summarize_stratum",
                     orchestration=OrchestrationConfig(mode="map", over="step5")))
    wf.add(Operation(step_id="step7", name="to_table",
                     arguments={"rows": "step6.ok"}))
    return wf


def test_the_happy_path_produces_one_row_per_stratum(video_root, texts):
    app = _app(video_root, FakeTranscriber(texts), FakeLLM())
    wf = _pipeline(app)
    wf.run()

    table = wf["step7"].output.value
    assert is_frame(table)
    assert set(table["topic"]) == {"birds", "weather"}
    birds = table[table["topic"] == "birds"].iloc[0]
    assert birds["videos"] == 2
    assert birds["total_words"] == 7        # "a bird sings here" + "another bird calls"


def test_a_failed_transcription_does_not_sink_the_batch(video_root, texts):
    app = _app(video_root, FakeTranscriber(texts, fail_on=["b.mp4"]), FakeLLM())
    wf = _pipeline(app)
    wf.run()

    transcripts = wf["step2"].output.value
    assert len(transcripts.ok) == 2
    assert len(transcripts.failed) == 1
    assert "b.mp4" in transcripts.failed[0].error

    # The table is built from the successes only.
    assert set(wf["step7"].output.value["topic"]) == {"birds"}


def test_a_failed_llm_call_is_isolated_too(video_root, texts):
    app = _app(video_root, FakeTranscriber(texts), FakeLLM(fail_on=["rain"]))
    wf = _pipeline(app)
    wf.run()

    analyses = wf["step3"].output.value
    assert len(analyses.ok) == 2 and len(analyses.failed) == 1


def test_retries_are_attempted_before_an_item_is_failed(video_root, texts):
    transcriber = FakeTranscriber(texts, fail_on=["b.mp4"])
    wf = _pipeline(_app(video_root, transcriber, FakeLLM()))
    wf.run()

    # retries=1 means the bad file is attempted twice, the good ones once.
    assert transcriber.calls.count("b.mp4") == 2
    assert transcriber.calls.count("a.mp4") == 1


def test_the_transcriber_is_handed_a_path_not_a_decoded_image(video_root, texts):
    transcriber = FakeTranscriber(texts)
    wf = _pipeline(_app(video_root, transcriber, FakeLLM()))
    wf.run()

    assert sorted(transcriber.calls) == ["a.mp4", "b.mp4", "c.mp4"]


def test_the_source_step_is_only_a_handle_until_something_iterates_it(video_root, texts):
    app = _app(video_root, FakeTranscriber(texts), FakeLLM())
    wf = app.session("t").workflow()
    wf.add(Operation(step_id="step1", name="videos-list",
                     arguments={"pattern": "*.mp4"}))
    wf.run()

    listing = wf["step1"].output.value
    assert listing.count() == 3
    assert listing.version.startswith("n:3:")
    assert all(a.is_video for a in listing)


def test_every_required_resource_is_declared(video_root, texts):
    wf = _pipeline(_app(video_root, FakeTranscriber(texts), FakeLLM()))
    assert wf.missing_resources() == []
