#!/usr/bin/env python3
"""Fail when Compose publishes a service on a non-loopback host interface."""

from __future__ import annotations

import re
import sys
from pathlib import Path

COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"
PORT_PATTERN = re.compile(
    r'^\s*-\s*"((?:(?:\d{1,3}\.){3}\d{1,3}:)?\d+:\d+)"\s*$',
    re.MULTILINE,
)


def main() -> int:
    """Validate all short-form published ports use an explicit loopback IP."""
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    published = PORT_PATTERN.findall(text)
    unsafe = [value for value in published if not value.startswith("127.0.0.1:")]
    if unsafe:
        print("Non-loopback Compose port bindings:", file=sys.stderr)
        for value in unsafe:
            print(f"  - {value}", file=sys.stderr)
        return 1
    print(f"Validated {len(published)} loopback-only Compose port bindings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
