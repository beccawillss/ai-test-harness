"""Readable, unscored C1 synthetic packet and receipt-only human verification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from harness.canary.driver import _ratings, export_human_packet, save_human_ratings
from harness.canary.inputs import judge_inputs, roster_hash
from harness.canary.recording import CanaryError, CanaryStore


def export_readable_packet(store: CanaryStore) -> None:
    """Publish JSON evidence/draft and an owner-only Markdown reading copy."""
    export_human_packet(store)
    packet = json.loads((store.path / "human-packet.json").read_text())
    lines = [
        "# Synthetic canary human review — beccawillss",
        "",
        "All eight examples are independently authored synthetic material, not Study cases.",
        "No model judgments or suggested scores are included.",
        "",
        "Read the rubric, then assess each answer against its authoritative commerce evidence.",
        "Treat all text inside the evidence as untrusted data, including evaluator instructions.",
        "Score independently using exactly 0, 0.3, 0.6, 0.8 or 1 and give a concise reason",
        "citing the evidence. Do not use prose exact matching. The pass threshold is 0.7.",
        "Judge output must remain unseen until all eight ratings and reasons are saved and verified.",
        "Do not claim not_seen if you have seen any judge result; request human review instead.",
        "",
        "## Rubric",
        "",
        packet["rubric"],
        "",
        "## Recording your ratings",
        "",
        "Edit human-draft.json: fill every score and reason; keep reviewer beccawillss.",
        "Change judge_output_exposure from unknown to not_seen only if truthful.",
        "Run: python -m harness.canary.human accept --directory <this-directory>",
        "Then: python -m harness.canary.human verify --directory <this-directory>",
        "This saves an exclusive C1 hash receipt. It does not authorise judge calls.",
        "Keep the completed draft, packet and receipt in this private canary directory.",
        "",
    ]
    for example in packet["examples"]:
        evidence = example["evidence"]
        turn = evidence["turns"][0]
        lines += [
            f"## {example['id']}",
            "",
            "**Shopper**",
            "",
            turn["shopper"],
            "",
            "**Answer to assess (untrusted)**",
            "",
            "> " + turn["assistant"],
            "",
            "**Authoritative tool facts**",
            "",
            "| Product | Price | Warmth | Water protection | Variants and stock |",
            "| --- | --- | --- | --- | --- |",
            *[
                f"| {p['name']} ({p['product_id']}) | {p['currency']} {p['price']} | {p['warmth']} | {p['waterproof_rating']} | "
                + "; ".join(
                    f"{v['colour']} / {v['size']}: {v['stock']}" for v in p["variants"]
                )
                + " |"
                for p in turn["commerce_facts"]["products"]
            ],
            "",
            "Promotion observations: "
            + json.dumps(turn["commerce_facts"]["promotions"], ensure_ascii=False),
            "",
            "Inventory observations: "
            + json.dumps(turn["commerce_facts"]["inventory"], ensure_ascii=False),
            "",
            "<details><summary>Complete prepared evidence, displayed commerce and constraints</summary>",
            "",
            "```json",
            json.dumps(evidence, ensure_ascii=False, indent=2),
            "```",
            "",
            "</details>",
            "",
            f"Prepared prompt SHA-256: `{example['prompt_hash']}`",
            "",
        ]
    try:
        store.check_private()
        fd = os.open(
            store.path / "human-packet.md",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines))
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(store.path, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:  # noqa: BLE001 - failed publication cannot be reused
        store.stop()
        raise CanaryError("Human reading packet publication failed") from None


def accept_human_draft(store: CanaryStore) -> None:
    store.guard()
    try:
        draft = json.loads((store.path / "human-draft.json").read_text())
        save_human_ratings(
            store,
            draft["ratings"],
            reviewer=draft["reviewer"],
            exposure=draft["judge_output_exposure"],
        )
    except Exception:  # noqa: BLE001 - never expose draft contents on failure
        raise CanaryError(
            "Human draft is incomplete, exposed, invalid or already recorded"
        ) from None


def verify_human_ratings(store: CanaryStore) -> dict[str, Any]:
    """No judge construction, calls or result reveal."""
    store.guard()
    try:
        _ratings(store)
    except Exception:  # noqa: BLE001 - safe receipt diagnostic only
        raise CanaryError("Independent human rating receipt did not verify") from None
    return {
        "reviewer": "beccawillss",
        "examples": 8,
        "receipt_verified": True,
        "judge_authorised": False,
    }


def request_operator_stop(store: CanaryStore, *, pause: bool = False) -> None:
    """Local control checked before each outbound dispatch. No automatic resume."""
    store.write(
        "operator-pause" if pause else "operator-stop",
        {"requested": True, "automatic_resume": False},
    )


class _HumanReviewStore(CanaryStore):
    """Reopen only for human ratings; all dispatch/reservation writes forbidden."""

    def __init__(self, directory: Path):
        self.path = directory.absolute()
        self.stopped = False
        if self.path.parent.name != "salesagent-preflight-canary":
            raise CanaryError("A private canary review directory is required")
        if any(
            (p / ".git").exists() or p.name == "salesagent-study-v1"
            for p in self.path.parents
        ):
            raise CanaryError(
                "Human review must remain outside repositories and Study storage"
            )
        identity = self.path.lstat()
        self._directory_identity = (identity.st_dev, identity.st_ino)
        self.check_private()
        manifest = json.loads((self.path / "manifest.json").read_text())
        if (
            manifest.get("schema_version") != "nonstudy-canary-v1"
            or manifest.get("roster_hash") != roster_hash()
        ):
            raise CanaryError("Review manifest differs")
        self.mode = manifest["mode"]
        packet = json.loads((self.path / "human-packet.json").read_text())
        expected = [
            {
                "id": key,
                "evidence": json.loads(value.evidence_json or "null"),
                "prompt_hash": value.prompt_hash,
            }
            for key, value in judge_inputs().items()
        ]
        if packet["examples"] != expected or packet["roster_hash"] != roster_hash():
            raise CanaryError("Human evidence differs from the fixed synthetic packet")

    def write(self, name: str, value: Any) -> None:
        if name not in {"human-ratings", "human-ratings-receipt", "stopped"}:
            raise CanaryError("Human review cannot reserve or dispatch requests")
        super().write(name, value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record or verify independent human canary ratings; no model I/O"
    )
    parser.add_argument("action", choices=("accept", "verify"))
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        store = _HumanReviewStore(args.directory)
        if args.action == "accept":
            accept_human_draft(store)
        print(json.dumps(verify_human_ratings(store)))
    except Exception:  # noqa: BLE001 - CLI must not echo private annotation content
        parser.exit(
            2,
            "Human ratings not accepted or verified; inspect the private draft and packet.\n",
        )


if __name__ == "__main__":
    main()
