#!/usr/bin/env bash

set -euo pipefail

python -m pip install -e ".[dev]"
ruff check .
pytest -q --cov --cov-report=term-missing
python -m build
