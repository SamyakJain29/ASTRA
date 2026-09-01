"""Smoke tests for the initial research repository scaffold."""

import importlib
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILES = (
    Path("configs/data.yaml"),
    Path("configs/baseline.yaml"),
    Path("configs/experiment.yaml"),
)

EXPECTED_DIRECTORIES = (
    Path("configs"),
    Path("data/raw"),
    Path("data/interim"),
    Path("data/processed"),
    Path("data/external"),
    Path("docs"),
    Path("scripts"),
    Path("src/astra/data"),
    Path("src/astra/features"),
    Path("src/astra/models"),
    Path("src/astra/evaluation"),
    Path("src/astra/context"),
    Path("src/astra/memory"),
    Path("src/astra/explain"),
    Path("src/astra/utils"),
)


def test_astra_package_imports() -> None:
    """The top-level ASTRA package should be importable."""
    astra = importlib.import_module("astra")

    assert astra.__name__ == "astra"


@pytest.mark.parametrize("relative_path", CONFIG_FILES)
def test_configuration_file_is_readable(relative_path: Path) -> None:
    """Each required configuration file should contain valid YAML."""
    config_path = PROJECT_ROOT / relative_path

    assert config_path.is_file()
    yaml.safe_load(config_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("relative_path", EXPECTED_DIRECTORIES)
def test_expected_directory_exists(relative_path: Path) -> None:
    """Each required repository directory should exist."""
    assert (PROJECT_ROOT / relative_path).is_dir()

