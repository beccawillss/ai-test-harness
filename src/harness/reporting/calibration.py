"""Separate reviewer and post-freeze analyst renderers; evaluation text is inert."""

from __future__ import annotations

import html
import json
from collections import Counter
from typing import Any

from harness.core.calibration import BlindPacket, CalibrationResult


def inert(text: str) -> str:
    # An escaped HTML pre element prevents Markdown links, images and fences from
    # being interpreted. Escape quotes as well for conservative downstream HTML.
    return "<pre>" + html.escape(text, quote=True) + "</pre>\n"


def render_packet(packet: BlindPacket) -> str:
    if not isinstance(packet, BlindPacket):
        raise TypeError("Blind renderer accepts only a BlindPacket")
    parts = [
        "# Independent human review\n",
        "Evaluation data: review sharing permissions before distributing.\n",
        inert(packet.contract.instructions),
        "## Rating contract\n",
        inert(
            json.dumps(
                packet.contract.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
        ),
    ]
    for item in packet.items:
        parts += [
            f"## Item {item.example_id}\n",
            inert(
                json.dumps(json.loads(item.evidence_json), ensure_ascii=False, indent=2)
            ),
        ]
    return "\n".join(parts)


def _render_details(result: CalibrationResult, *, legacy: bool = False) -> str:
    summary = result.summary
    parts = [
        "# Exploratory human–judge agreement evidence\n"
        if legacy
        else "# Calibration analyst appendix\n",
        "Status: provisional_uncalibrated. Evaluation data; source and human content require sharing controls.\n",
        summary["interpretation"]
        + " Score intervals have no assumed universal quantitative meaning. Human ratings are observations, not an infallible answer key.\n",
        f"Planned: {summary['planned_examples']}; frozen human: {summary['frozen_humans']}; missing human: {summary['missing_humans']}; missing judge: {summary['missing_judges']}; completed judge scores: {summary['completed_judge_scores']}; errors: {summary['judge_errors']}; distinct cases: {summary['distinct_cases']}.\n",
        "## Exposure and input verification\n",
        summary["primary_note"],
        inert(
            json.dumps(
                {
                    "primary": summary["primary_blind_verified"],
                    "cohorts": summary["cohorts"],
                },
                indent=2,
            )
        ),
        "Historical input reconstruction does not prove historical request bytes. Exposed results are not blind calibration. Groups and repeated case families are not independent population samples.\n",
        "## Descriptive metrics\n",
        "Equal fixed-response weights; integer confusion counts and call rates are separately call-weighted. No mean-threshold or majority judge verdict is assigned.\n",
        inert(json.dumps(summary["exploratory_all"], indent=2)),
        "## Per-response comparisons\n",
    ]
    for index, row in enumerate(summary["rows"], 1):
        parts += [
            f"### {row['example_id']}\n"
            if legacy
            else f"### E{index:02d}\n\nExample: {row['example_id']}\n",
            inert(json.dumps(row, ensure_ascii=False, indent=2)),
        ]
    parts += ["## Human-only dimensions and overlapping case families\n"]
    if legacy:
        parts += [
            inert(
                json.dumps(
                    {
                        "dimensions": summary["human_dimensions"],
                        "families_nonadditive": summary["case_families_nonadditive"],
                    },
                    indent=2,
                )
            )
        ]
    else:
        dimensions = _collected_dimensions(summary)
        parts += [
            inert(json.dumps(dimensions, indent=2))
            if dimensions
            else "Human dimension ratings were not collected in this pilot.\n"
        ]
        families = summary["case_families_nonadditive"]
        parts += [
            inert(json.dumps(families, indent=2))
            if families
            else "No case-family breakdowns were collected.\n"
        ]
    parts += [
        "## Analyst provenance and ordered reasons\n",
        "Manual issue comparisons are unblinded interpretation, not independent ratings. Unreviewed does not imply issue agreement.\n",
        inert(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)),
    ]
    return "\n".join(parts)


def render_legacy_report(result: CalibrationResult) -> str:
    """Exact original layout, solely to validate existing immutable bundles."""
    return _render_details(result, legacy=True)


def render_appendix(result: CalibrationResult) -> str:
    """Full comparisons and original payload; result.json remains canonical."""
    return _render_details(result)


def _collected_dimensions(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {
            category: data
            for category, data in categories.items()
            if data["human_count"]
        }
        for key, categories in summary["human_dimensions"].items()
        if any(
            data["human_count"]
            for category, data in categories.items()
            if category != "unassessed"
        )
    }


def _cell(value: str) -> str:
    # Numeric HTML entities are inert under CommonMark, including brackets,
    # pipes, backticks and backslashes. Never interpolate raw evaluation prose.
    return "".join(
        c if c.isalnum() or c in " .,:;_/-" else f"&#{ord(c)};"
        for c in value.replace("\n", " ")
    )


def _number(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    return format(value, "+.4f" if signed else ".4f").rstrip("0").rstrip(".")


def _rate(value: float | None, numerator: float, denominator: int) -> str:
    return (
        "— (no eligible pairs)"
        if value is None
        else f"{value:.1%} ({numerator:g}/{denominator})"
    )


def _notable(row: dict[str, Any]) -> bool:
    return bool(
        (row["mae"] is not None and row["mae"] > 0)
        or row["verdict_matches"] < row["verdict_pairs"]
        or row["distribution"]["threshold_crossing"]
        or row["human_inside_observed_range"] is False
        or row["distribution"]["error_count"]
        or not row["distribution"]["completed_score_count"]
        or row["status"] != "matched"
    )


def _issues(relations: list[str]) -> str:
    labels = {
        "same_issue_different_severity": "same issue, different severity",
        "same_issue": "same issue",
        "different_issue": "different issues (recognition disagreement)",
        "partial_overlap": "partial overlap (recognition disagreement)",
        "human_only_issue": "human-only issue (recognition disagreement)",
        "judge_only_issue": "judge-only issue (recognition disagreement)",
        "no_issue_both": "no issue in either",
        "unclear": "unclear",
        "unreviewed": "unreviewed",
    }
    counts = Counter(relations)
    return (
        "; ".join(f"{labels[key]} ×{count}" for key, count in counts.items())
        or "unreviewed"
    )


def render_report(result: CalibrationResult) -> str:
    """Concise human summary; all numbers come from unchanged agreement metrics."""
    s = result.summary
    totals = s["exploratory_all"]
    matrix = totals["confusion_matrix"]
    parts = [
        "# Exploratory human–judge agreement evidence\n",
        "**Status: provisional_uncalibrated.** Numeric differences are descriptive rubric-scale distances, not calibrated prediction errors. This pilot does not establish statistical reliability or general calibration.\n",
        "## Collection\n",
        f"Planned examples: **{s['planned_examples']}** · Frozen human annotations: **{s['frozen_humans']}** · Matched examples: **{totals['matched_examples']}** · Completed judge calls: **{s['completed_judge_scores']}** · Judge errors: **{s['judge_errors']}** · Distinct cases: **{s['distinct_cases']}**.\n",
        f"Missing human ratings: {s['missing_humans']}; missing judge records: {s['missing_judges']}.\n",
        "## Exposure and verification\n",
        "**No eligible genuinely blind ratings.**"
        if not s["primary_blind_verified"]["matched_examples"]
        else f"Eligible declared-unexposed, frozen-request-verified ratings: {s['primary_blind_verified']['matched_examples']}.",
        "`historical_input_reconstructed` rebuilds evidence but cannot prove historical request bytes. `frozen_request_verified` checks saved actual-call fingerprints. Exposed evidence is not blind calibration; the combined metrics below are exploratory.\n",
        "## Headline metrics\n",
        "Each fixed response has equal weight in MAE, signed difference and equal-response verdict agreement. Call-level rates weight individual completed calls. Positive signed difference means the judge scored higher.\n",
        "| Metric | Value |\n| --- | --- |",
        f"| MAE | {_number(totals['mae'])} |",
        f"| Mean signed difference | {_number(totals['mean_signed_difference'], signed=True)} |",
        f"| Equal-response verdict agreement | {_rate(totals['equal_response_verdict_agreement'], totals['verdict_response_agreement_sum'], totals['verdict_response_denominator'])} response-fraction sum / responses |",
        f"| Call-level verdict agreement | {_rate(totals['call_agreement'], totals['call_matches'], totals['call_pairs'])} |",
        f"| Exact score agreement | {_rate(totals['exact_score_agreement'], totals['exact_matches'], totals['score_pairs'])} calls |",
        f"| Call-level confusion counts | Human PASS: judge PASS **{matrix['human_pass_judge_pass']}**, FAIL **{matrix['human_pass_judge_fail']}**; human FAIL: judge PASS **{matrix['human_fail_judge_pass']}**, FAIL **{matrix['human_fail_judge_fail']}** |\n",
        "## Cohorts\n",
        "Verdict agreement is equal-response; exact-score agreement is call-weighted. Cohort counts include missing/error examples; rate denominators include only eligible pairs.\n",
        "| Cohort | Examples | MAE | Verdict agreement | Exact-score agreement | Qualification |\n| --- | ---: | ---: | --- | --- | --- |",
    ]
    for name, metrics in s["cohorts"].items():
        exposure, verification = name.split("/", 1)
        qualification = (
            "Declared unexposed"
            if exposure == "not_seen"
            else "Unrated"
            if exposure == "unrated"
            else "Exposure unknown"
            if exposure == "unknown"
            else "Exposed; not blind"
        ) + (
            "; request bytes unproven"
            if verification == "historical_input_reconstructed"
            else "; saved request verified"
            if verification == "frozen_request_verified"
            else "; no judge record"
        )
        parts.append(
            f"| {_cell(name)} | {metrics['example_count']} | {_number(metrics['mae'])} | {_rate(metrics['equal_response_verdict_agreement'], metrics['verdict_response_agreement_sum'], metrics['verdict_response_denominator'])} | {_rate(metrics['exact_score_agreement'], metrics['exact_matches'], metrics['score_pairs'])} | {qualification} |"
        )
    if not s["cohorts"]:
        parts.append("| None | 0 | — | — | — | No paired evidence |")
    parts += [
        "\n## Notable disagreements and missing evidence\n",
        "Δ is mean signed judge−human difference; MAE retains absolute per-call distances. Links map display labels to full opaque identities in the appendix. Human scores outside the observed range are marked ‘outside’.\n",
        "| Example | Human | Judge scores / distribution | Δ / MAE | Verdict agreement | Crossing | Manual issue relation |\n| --- | --- | --- | --- | --- | --- | --- |",
    ]
    notable_count = 0
    for index, row in enumerate(s["rows"], 1):
        if not _notable(row):
            continue
        notable_count += 1
        distribution = row["distribution"]
        values = distribution["scores_by_attempt"]
        scores = (
            ", ".join("ERROR" if v is None else _number(v) for v in values)
            if len(values) <= 5
            else f"n={distribution['completed_score_count']}; mean {_number(distribution['mean'])}; range {_number(distribution['min'])}–{_number(distribution['max'])}; errors {distribution['error_count']}"
        )
        human_verdict = (
            "—"
            if row["human_score"] is None
            else "SKIP"
            if row["human_passed"] is None
            else "PASS"
            if row["human_passed"]
            else "FAIL"
        )
        human = f"{_number(row['human_score'])} {human_verdict}" + (
            "; outside" if row["human_inside_observed_range"] is False else ""
        )
        crossing = (
            "—"
            if distribution["threshold_crossing"] is None
            else "yes"
            if distribution["threshold_crossing"]
            else "no"
        )
        parts.append(
            f"| [E{index:02d}](analyst_appendix.md#e{index:02d}) | {human} | {scores or 'No completed observations'} | {_number(row['mean_signed_difference'], signed=True)} / {_number(row['mae'])} | {_rate(row['verdict_agreement'], row['verdict_matches'], row['verdict_pairs'])} | {crossing} | {_cell(_issues(row['issue_relations']))} |"
        )
    if not notable_count:
        parts.append(
            "| None | — | — | — | — | — | No notable disagreements or missing evidence |"
        )
    relations = [relation for row in s["rows"] for relation in row["issue_relations"]]
    recognition = sum(
        r
        in {
            "human_only_issue",
            "judge_only_issue",
            "different_issue",
            "partial_overlap",
        }
        for r in relations
    )
    severity = relations.count("same_issue_different_severity")
    parts += [
        "\n## Findings and limitations\n",
        f"Responses with score disagreement: {len(s['numeric_disagreements'])}; verdict disagreement: {len(s['threshold_disagreements'])}; threshold crossing: {sum(bool(r['distribution']['threshold_crossing']) for r in s['rows'])}. These categories can overlap.\n",
        (
            f"Manually reviewed call pairs: {len(result.issues)}; issue-recognition disagreement: {recognition}; same issue, different severity: {severity}. Unreviewed: {relations.count('unreviewed')} call pairs.\n"
            if result.issues
            else f"Manual issue recognition and severity have not been reviewed ({relations.count('unreviewed')} unreviewed call pairs).\n"
        ),
        "Human dimension ratings were not collected in this pilot.\n"
        if not _collected_dimensions(s)
        else "Collected human-only dimension ratings and overlapping case-family breakdowns are in the appendix; they are not judge dimension ratings.\n",
        "Issue relations are manually supplied after freeze and are unblinded. Neither equal/different scores nor a score of 1.0 establishes issue recognition. ERROR is not a quality score; SKIP has no verdict comparison. Single observations provide no repeatability evidence; five calls do not establish a general variance rate. Human ratings are observations, not an infallible answer key.\n",
        "See [analyst_appendix.md](analyst_appendix.md) for complete comparisons, ordered reasons, optional breakdowns, contracts, selection and provenance. [result.json](result.json) remains the complete machine-readable source of truth. Both documents contain evaluation data and require the same sharing controls as the source.\n",
    ]
    return "\n".join(parts)
