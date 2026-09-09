"""Explicit evaluation release identity; never infer provenance while loading history."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .version import get_backend_version

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_COMMIT = re.compile(r"[0-9a-fA-F]{40}")


class EvaluationProvenance(BaseModel):
    backend_version: str
    git_commit: str | None = None
    source: Literal["git", "build", "unknown"] = "unknown"
    dirty: bool | None = None


def _capture() -> EvaluationProvenance:
    result = EvaluationProvenance(backend_version=get_backend_version())
    for name in ("FINANCIAL_AGENT_COMMIT", "GITHUB_SHA"):
        revision = os.environ.get(name, "")
        if _COMMIT.fullmatch(revision):
            return result.model_copy(
                update={"git_commit": revision.lower(), "source": "build"}
            )
    if not (REPOSITORY_ROOT / ".git").exists():
        return result
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).strip()
        if not _COMMIT.fullmatch(revision):
            return result
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return result.model_copy(
            update={
                "git_commit": revision.lower(),
                "source": "git",
                "dirty": bool(status.strip()),
            }
        )
    except (OSError, subprocess.SubprocessError):
        # Missing Git, a source-only image, or a slow mount is unknown, not clean.
        return result


async def capture_evaluation_provenance() -> EvaluationProvenance:
    """Capture once at run start off the event loop; callers retain this identity."""
    return await asyncio.to_thread(_capture)
