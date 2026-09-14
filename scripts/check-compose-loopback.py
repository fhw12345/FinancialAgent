#!/usr/bin/env python3
"""Validate rendered Compose ports, including long syntax and every profile."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(config: dict) -> int:
    """Reject wildcard/implicit/IPv6 binds; this repo explicitly uses 127.0.0.1."""
    count = 0
    for name, service in config.get("services", {}).items():
        for port in service.get("ports", []):
            count += 1
            if not isinstance(port, dict) or port.get("host_ip") != "127.0.0.1":
                raise ValueError(f"Non-loopback published port in service {name}")
    if count == 0:
        raise ValueError("No published ports found; check the rendered configuration")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Previously rendered Compose JSON")
    args = parser.parse_args()
    if args.config:
        text = args.config.read_text(encoding="utf-8")
    else:
        text = subprocess.check_output(
            [
                "docker",
                "compose",
                "--profile",
                "*",
                "config",
                "--no-env-resolution",
                "--format",
                "json",
            ],
            cwd=ROOT,
            text=True,
            timeout=30,
        )
    # Rendered config can contain runtime credentials; never print its contents.
    print(
        f"Validated {validate(json.loads(text))} loopback-only Compose port bindings."
    )


if __name__ == "__main__":
    main()
