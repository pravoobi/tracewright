"""Write test-scaffold/page-objects/*.ts from an environment's stored Phase 1 registry.

    uv run python scripts/write-page-objects.py <tenant_id> <environment_id> [--out DIR]

Run it after build-registry so the page objects that generated specs import
match the locators that were verified against the live app.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.agents.generator.app_model import AppModelRegistry
from backend.src.agents.generator.page_objects import write_page_objects
from backend.src.storage.files import download_file, registry_path

DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "test-scaffold", "page-objects")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tenant_id")
    ap.add_argument("environment_id")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    registry = AppModelRegistry.from_dict(
        json.loads(download_file(registry_path(args.tenant_id, args.environment_id)))
    )
    for path in write_page_objects(registry, args.out):
        print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
