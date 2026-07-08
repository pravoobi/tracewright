#!/usr/bin/env bash
# Run the FastAPI backend for local dev with hot-reload correctly scoped.
#
# Plain `uvicorn --reload` (with no --reload-dir) watches the entire cwd
# recursively. Run from the repo root and it watches the WHOLE repo —
# scripts/, frontend/, test-scaffold/, scratch files, anything — so any
# unrelated file edit triggers a full process restart. That resets every
# module-level cache, including embed.py's lazily-loaded BGE-M3 model,
# which costs ~25-50s to reload from scratch. This was silently the real
# cause of "slow" Planner/hybrid_search calls throughout dev, not the
# database index (see migration 0003's docstring for that investigation).
#
# Run this from the repo root: ./scripts/run-backend-dev.sh
set -euo pipefail
export HF_HUB_DISABLE_SYMLINKS=1
uv run uvicorn backend.src.main:app --reload --reload-dir backend/src --port 8000
