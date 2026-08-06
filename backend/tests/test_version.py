"""Tests for authoritative backend version metadata."""

import tomllib

from src.core.version import BACKEND_VERSION, SOURCE_PYPROJECT, get_backend_version


def test_backend_version_matches_source_package() -> None:
    """Bind-mounted development must prefer the current source metadata."""
    with SOURCE_PYPROJECT.open("rb") as pyproject_file:
        expected = tomllib.load(pyproject_file)["project"]["version"]

    assert get_backend_version() == expected
    assert BACKEND_VERSION == expected
    assert BACKEND_VERSION != "0.1.0"
