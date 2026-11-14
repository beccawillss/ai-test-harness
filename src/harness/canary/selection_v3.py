"""Offline selected-preference definition; the historical roster is immutable."""

from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

from harness.canary.controller import FIXTURES
from harness.canary.inputs import (
    JUDGE_ORDER,
    TARGET_MODEL,
    TARGET_REVISION,
    TARGET_TURNS,
    judge_inputs,
)
from harness.canary.recording import usage_metadata
from harness.core.fingerprints import fingerprint

DEFINITION = "salesagent-canary-selected-preferences-v3"
HARNESS_BASELINE = "b2c4878a261f2c17251c47437d8d49dd761ddc12"
A1 = "Please find a water-resistant day pack for a short canal-side walk. My maximum price is £60. I choose ACC-003 in Moss, 20L; please remember this product, colour and capacity as my preferences for this conversation and check that exact variant's availability. Do not apply a discount."
A2 = "For the pack and exact variant I selected earlier, validate WELCOME10 and quote the final price. Keep my saved preferences and price limit."
TURNS = tuple(
    replace(t, message=A1 if t.slot == "A1" else A2) if t.slot in ("A1", "A2") else t
    for t in TARGET_TURNS
)
ORDER = tuple(t.slot for t in TURNS)


@dataclass(frozen=True)
class Limits:
    chat_posts: int = 4
    logical_calls_per_turn: int = 6
    logical_calls_total: int = 24
    attempts_per_call: int = 3
    provider_attempts_total: int = 72
    sdk_retries: int = 2
    max_output_tokens: int = 2000
    reasoning_effort: str = "low"
    target_allowance_usd: str = "3"
    contingency_usd: str = "2"
    estimated_pause_usd: str = "5"
    project_monthly_limit_usd: str = "10"
    alerts_usd: tuple[str, ...] = ("2", "4", "5")


LIMITS = Limits()


def roster_fingerprint() -> str:
    """Existing hash format; preparing metadata executes no semantic judge."""
    return fingerprint(
        {
            "target": [vars(t) for t in TURNS],
            "judge": {k: v.prompt_hash for k, v in judge_inputs().items()},
            "order": list(JUDGE_ORDER),
        }
    )


def definition_fingerprint() -> str:
    """Definition identity, not live authority or a claim about deployed HEAD."""
    return fingerprint(
        {
            "definition": DEFINITION,
            "implementation_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "roster_fingerprint": roster_fingerprint(),
            "harness_baseline": HARNESS_BASELINE,
            "target_revision": TARGET_REVISION,
            "target_model": TARGET_MODEL,
            "fixtures": FIXTURES,
            "limits": asdict(LIMITS),
            "cost_estimator_sha256": sha256(
                inspect.getsource(usage_metadata).encode()
            ).hexdigest(),
            "scope": "offline-only; no controller integration or live authority",
            "judge_dispatch": "not_authorised",
            "human_prose_review": "required",
        }
    )
