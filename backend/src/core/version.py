"""Authoritative backend version access.

Reads the installed package metadata so FastAPI diagnostics cannot drift from
``backend/pyproject.toml``. Editable source-only environments receive an
explicit development fallback rather than the historical ``0.1.0`` placeholder.
"""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE_NAME = "financial-agent-backend"
DEVELOPMENT_VERSION = "0.0.0+development"
SOURCE_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def get_backend_version() -> str:
    """Return source metadata during development, otherwise installed metadata."""
    if SOURCE_PYPROJECT.is_file():
        with SOURCE_PYPROJECT.open("rb") as pyproject_file:
            project = tomllib.load(pyproject_file).get("project", {})
        source_version = project.get("version")
        if isinstance(source_version, str) and source_version:
            return source_version
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return DEVELOPMENT_VERSION


BACKEND_VERSION = get_backend_version()
