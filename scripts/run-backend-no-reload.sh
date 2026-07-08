#!/usr/bin/env bash
# Run the FastAPI backend WITHOUT hot-reload — required for Generator
# Phase 1 (build_app_model) to work at all on Windows.
#
# Playwright's async API launches its browser as a subprocess, which
# needs asyncio's ProactorEventLoop on Windows (SelectorEventLoop's
# _make_subprocess_transport raises NotImplementedError). main.py sets
# WindowsProactorEventLoopPolicy at import time, and that works correctly
# when uvicorn is run directly -- but uvicorn's --reload mode spawns its
# worker via multiprocessing in a way that resets the policy back to
# Selector regardless, independent of anything in application code.
# Confirmed by testing both ways side by side: identical code, --reload
# gives _WindowsSelectorEventLoop, no --reload gives ProactorEventLoop.
#
# Trade-off: no hot-reload while running this. For normal work (anything
# that doesn't call the Generator's build-registry endpoint), use
# scripts/run-backend-dev.sh instead.
set -euo pipefail
export HF_HUB_DISABLE_SYMLINKS=1
uv run uvicorn backend.src.main:app --port 8000
