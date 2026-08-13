"""Reading RunConfigs from YAML.

Deliberately outside `harness.core`: core must stay dependency-free, and
pyyaml is a dependency. Anyone constructing a RunConfig in code — the
harness's own test suite included — never pays for it. Install with the
`yaml` extra.

Scope note: a config file currently describes *how* to run (attempts,
mode, filters), not *what* to run against. Resolving `target:`/`pack:`
names to objects needs a registry, which does not exist yet; callers pass
those objects to the runner directly.
"""

from __future__ import annotations

from pathlib import Path

from harness.core.config import RunConfig
from harness.core.errors import ConfigError


def load_config(path: str | Path) -> RunConfig:
    """Parse a YAML file into a RunConfig, recording where it came from."""
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise ConfigError(
            "Reading YAML configs requires pyyaml. Install the extra: "
            "`uv add harness[yaml]`, or build the RunConfig in code."
        ) from exc

    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Cannot read config '{path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in '{path}': {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config '{path}' must be a YAML mapping, got {type(raw).__name__}."
        )

    # The file's own location always wins over any config_path written
    # inside it — provenance should not be forgeable by a typo.
    raw["config_path"] = str(path)

    try:
        return RunConfig.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid config '{path}': {exc}") from exc


__all__ = ["load_config"]
