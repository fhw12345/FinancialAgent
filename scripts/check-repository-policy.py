#!/usr/bin/env python3
"""Block changed source over 500 lines and PR-wide version/lock drift."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".sh"}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=30)


def versions(backend: str, frontend: str) -> tuple[str, str]:
    return tomllib.loads(backend)["project"]["version"], json.loads(frontend)["version"]


def validate_versions(
    before: tuple[str, str], after: tuple[str, str], require_bump: bool
) -> None:
    old = [tuple(map(int, version.split("."))) for version in before]
    new = [tuple(map(int, version.split("."))) for version in after]
    if any(b < a for a, b in zip(old, new, strict=True)):
        raise ValueError("Component version decreased")
    if require_bump and old == new:
        raise ValueError("Implementation changes require a component version bump")


def validate_length(path: str, text: str) -> None:
    if Path(path).suffix in SOURCE_SUFFIXES and len(text.splitlines()) > 500:
        raise ValueError(f"{path} exceeds 500 lines")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="PR merge base, not HEAD~1")
    args = parser.parse_args()
    base = git("merge-base", args.base, "HEAD").strip()
    paths = git("diff", "--name-only", "--diff-filter=ACMRD", "-z", base).split("\0")
    paths += git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    paths = sorted({path for path in paths if path})
    for path in paths:
        if Path(path).suffix in SOURCE_SUFFIXES and (ROOT / path).is_file():
            validate_length(path, (ROOT / path).read_text(encoding="utf-8"))
    before = versions(
        git("show", f"{base}:backend/pyproject.toml"),
        git("show", f"{base}:frontend/package.json"),
    )
    after = versions(
        (ROOT / "backend/pyproject.toml").read_text(),
        (ROOT / "frontend/package.json").read_text(),
    )
    validate_versions(
        before,
        after,
        any(not p.startswith("docs/") and not p.endswith(".md") for p in paths),
    )
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text())
    if lock["version"] != after[1] or lock["packages"][""]["version"] != after[1]:
        raise ValueError("Frontend lock version differs from package metadata")
    print(f"Changed-source length and PR-wide versions passed ({len(paths)} files)")


if __name__ == "__main__":
    main()
