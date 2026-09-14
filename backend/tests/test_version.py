"""Tests for authoritative backend version metadata."""

import tomllib
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from src.core.version import BACKEND_VERSION, SOURCE_PYPROJECT, get_backend_version


def test_backend_version_matches_source_package() -> None:
    """Bind-mounted development must prefer the current source metadata."""
    with SOURCE_PYPROJECT.open("rb") as pyproject_file:
        expected = tomllib.load(pyproject_file)["project"]["version"]

    assert get_backend_version() == expected
    assert BACKEND_VERSION == expected
    assert BACKEND_VERSION != "0.1.0"


def test_installed_metadata_when_source_missing(tmp_path) -> None:
    with (
        patch("src.core.version.SOURCE_PYPROJECT", tmp_path / "absent.toml"),
        patch("src.core.version.version", return_value="1.2.3") as installed,
    ):
        assert get_backend_version() == "1.2.3"
        installed.assert_called_once_with("financial-agent-backend")


def test_source_only_fallback_when_package_missing(tmp_path) -> None:
    with (
        patch("src.core.version.SOURCE_PYPROJECT", tmp_path / "absent.toml"),
        patch("src.core.version.version", side_effect=PackageNotFoundError),
    ):
        assert get_backend_version() == "0.0.0+development"
