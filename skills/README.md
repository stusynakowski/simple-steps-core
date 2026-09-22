# Portable skills

Skills written here for **other** repos. They live outside `.claude/skills/` on
purpose, so they do not load in this repo — this is a library, and these
describe building applications *on top of* it.

## video-transcript-pipeline

Building and testing a service that reads media from a shared filesystem,
transcribes it, runs LLM operations across each item, and writes a stratified
summary table.

Install it in the application repo, either way:

```bash
# copy it in (the repo owns its own copy)
cp -r skills/video-transcript-pipeline /path/to/app-repo/.claude/skills/

# or make it available in every repo on this machine
ln -s "$PWD/skills/video-transcript-pipeline" ~/.claude/skills/video-transcript-pipeline
```

`assets/tools_template.py` and `assets/test_pipeline_template.py` are a working
pipeline and its passing test suite — copy both and replace the two
`_build_*` stubs with real model clients.
