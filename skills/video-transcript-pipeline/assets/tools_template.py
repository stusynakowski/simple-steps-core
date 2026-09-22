"""Video transcript pipeline: shared FS -> transcribe -> LLM -> stratified table."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from simple_steps_core import (
    Collection, Group, ListCollection, MediaAsset, Resource, ResourceSpec,
    register_tool,
)

# ── 1. the shared filesystem ──────────────────────────────────────────────
def _video_root() -> Path:
    return Path(os.environ.get("VIDEO_ROOT", "/mnt/shared/video")).expanduser()

videos = ResourceSpec("videos", factory=_video_root,
                      check=lambda root: root.is_dir(),
                      description="Shared filesystem holding source video.")

@videos.tool("list", description="Every video under the shared root.")
def list_videos(pattern: str = "**/*.mp4", root=Resource()) -> Collection:
    paths = sorted(root.glob(pattern))
    newest = max((p.stat().st_mtime_ns for p in paths), default=0)
    return ListCollection(items=[MediaAsset.from_path(p) for p in paths],
                          version=f"n:{len(paths)}:mtime:{newest}")

# ── 2. transcription ──────────────────────────────────────────────────────
transcription = ResourceSpec("transcriber", factory=lambda: _build_transcriber(),
                             description="Speech-to-text model or client.")

def _build_transcriber():
    raise RuntimeError("wire your transcriber here")

@transcription.tool("transcribe", description="Transcribe one video to text.")
def transcribe(video: MediaAsset, transcriber=Resource()) -> dict:
    # Video is whole-clip: hand over the PATH. video.open() is images only.
    text = transcriber.transcribe(video.path)
    return {"video": video.name, "path": video.path, "text": text,
            "words": len(text.split())}

# ── 3. LLM operations ─────────────────────────────────────────────────────
llm_ops = ResourceSpec("llm", factory=lambda: _build_llm(),
                       description="Chat/completions client.")

def _build_llm():
    raise RuntimeError("wire your llm here")

@llm_ops.tool("analyze", description="Summarize and label one transcript.")
async def analyze(transcript: dict, llm=Resource()) -> dict:
    summary = await llm.complete(f"Summarize:\n{transcript['text']}")
    topic = await llm.complete(f"One-word topic:\n{transcript['text']}")
    return {**transcript, "summary": summary, "topic": topic.strip().lower()}

# ── 4. stratify ───────────────────────────────────────────────────────────
@register_tool("to_table", description="Turn a list of row dicts into a table.",
               type="dataframe")
def to_table(rows: list) -> pd.DataFrame:
    return pd.DataFrame(list(rows))

@register_tool("topic_of", description="The stratum a row belongs to.")
def topic_of(row: dict) -> str:
    return row["topic"]

@register_tool("summarize_stratum", description="One output row per stratum.")
def summarize_stratum(group: Group) -> dict:
    rows = group.rows
    return {"topic": group.key, "videos": len(group),
            "total_words": int(rows["words"].sum()),
            "mean_words": round(float(rows["words"].mean()), 1)}

CONFIG = {"title": "video pipeline", "freeze": False}
RESOURCES = [videos, transcription, llm_ops]

if __name__ == "__main__":
    from simple_steps_core.serving import Server
    Server().run()
