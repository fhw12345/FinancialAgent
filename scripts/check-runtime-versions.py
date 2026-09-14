#!/usr/bin/env python3
"""Compare package metadata with real root/Health/OpenAPI responses (no API keys)."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def validate(expected: str, root: dict, health: dict, openapi: dict) -> None:
    actual = (
        root.get("version"),
        health.get("version"),
        openapi.get("info", {}).get("version"),
    )
    if actual != (expected,) * 3:
        raise ValueError(f"Runtime version mismatch: expected {expected}, got {actual}")
    if health.get("status") != "ok":
        raise ValueError("Health endpoint is not ready")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    args = parser.parse_args()
    expected = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"][
        "version"
    ]
    responses = []
    for path in ("/", "/api/health", "/openapi.json"):
        with urlopen(args.backend_url.rstrip("/") + path, timeout=10) as response:
            responses.append(json.load(response))
    validate(expected, *responses)
    print(f"Root, Health and OpenAPI agree with backend@{expected}")


if __name__ == "__main__":
    main()
