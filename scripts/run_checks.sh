#!/usr/bin/env bash

set -euo pipefail

python -m pip install -e ".[dev]"
ruff check .
pytest -q
python -m build
