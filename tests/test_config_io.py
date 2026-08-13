"""Loading RunConfigs from YAML."""

from __future__ import annotations

import pytest

from harness.config_io import load_config
from harness.core.config import RunMode
from harness.core.errors import ConfigError
from harness.core.models import ScorerKind

YAML = """\
dataset_path: data/rag.jsonl
mode: explore
attempts: 3
include_tags: [smoke]
scorer_kinds: [deterministic]
model_versions:
  target: claude-opus-5
"""


def _write(tmp_path, text: str, name: str = "run.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_a_config(tmp_path):
    config = load_config(_write(tmp_path, YAML))

    assert config.dataset_path == "data/rag.jsonl"
    assert config.mode is RunMode.EXPLORE
    assert config.attempts == 3
    assert config.include_tags == ["smoke"]
    assert config.scorer_kinds == frozenset({ScorerKind.DETERMINISTIC})
    assert config.model_versions == {"target": "claude-opus-5"}


def test_config_path_records_where_the_file_came_from(tmp_path):
    path = _write(tmp_path, YAML)
    assert load_config(path).config_path == str(path)


def test_config_path_in_the_file_cannot_forge_provenance(tmp_path):
    path = _write(tmp_path, "config_path: somewhere/else.yaml\n")
    assert load_config(path).config_path == str(path)


def test_empty_file_yields_defaults(tmp_path):
    config = load_config(_write(tmp_path, ""))
    assert config.mode is RunMode.SCORE
    assert config.attempts == 1


def test_unknown_mode_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Invalid config"):
        load_config(_write(tmp_path, "mode: guess\n"))


def test_zero_attempts_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Invalid config"):
        load_config(_write(tmp_path, "attempts: 0\n"))


def test_malformed_yaml_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(_write(tmp_path, "attempts: [1, 2\n"))


def test_non_mapping_yaml_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(_write(tmp_path, "- just\n- a list\n"))


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read config"):
        load_config(tmp_path / "nope.yaml")
