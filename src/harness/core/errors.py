"""Exceptions the harness itself raises.

These are deliberately distinct from anything a target or scorer can
raise. A target/scorer exception is a *run outcome* — the runner records
Verdict.ERROR and keeps going (ADR 0001). The exceptions here are
*configuration bugs*: they escape the runner, abort before anything
executes, and cost nothing.
"""

from __future__ import annotations


class HarnessError(Exception):
    """Base for every error the harness raises about itself."""


class ConfigError(HarnessError):
    """A run was described incoherently and cannot be executed."""


class IncompatibleTargetError(ConfigError):
    """A pack needs response fields the target does not populate.

    Raised during validation, before a single case executes, so a RAG
    pack pointed at a plain model adapter fails at config time rather
    than as a wall of scorer errors halfway through a paid run.
    """

    def __init__(
        self,
        target_name: str,
        pack_name: str,
        missing: list[str],
        required_by: dict[str, list[str]] | None = None,
    ) -> None:
        self.target_name = target_name
        self.pack_name = pack_name
        self.missing = missing
        self.required_by = required_by or {}

        lines = [
            (
                f"Target '{target_name}' is not compatible with pack '{pack_name}': "
                f"missing {len(missing)} capability/capabilities."
            )
        ]
        for capability in missing:
            scorers = self.required_by.get(capability, [])
            needed = f" (required by: {', '.join(scorers)})" if scorers else ""
            lines.append(f"  - {capability}{needed}")
        lines.append(
            f"Either point the run at a target that declares these capabilities, "
            f"or drop the scorers that need them from '{pack_name}'."
        )
        super().__init__("\n".join(lines))


__all__ = ["ConfigError", "HarnessError", "IncompatibleTargetError"]
