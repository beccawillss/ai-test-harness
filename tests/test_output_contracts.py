"""Opt-in anchors preserve continuous legacy scoring and artifact identities."""

import hashlib
import json
from pathlib import Path

import pytest
from test_replay import fixture_run, prepare, scorer, settings

from harness.core.calibration import (
    CalibrationManifest,
    CalibrationResult,
    FrozenAnnotationSet,
)
from harness.core.fingerprints import canonical_json, fingerprint
from harness.core.models import RunResult
from harness.core.replay import EvaluatorConfiguration, PreparedReplay, prepare_replay
from harness.core.runner import _scorer_snapshot
from harness.scorers.output_contracts import ScoreOutputContract


@pytest.mark.parametrize(
    "anchors",
    [
        (),
        (True,),
        (False,),
        (0.3, 0.3),
        (1.0, 0.0),
        (-0.1,),
        (1.1,),
        (float("nan"),),
        (float("inf"),),
        ("0.3",),
    ],
)
def test_invalid_anchor_contract(anchors):
    with pytest.raises(ValueError):
        ScoreOutputContract(id="test-v1", anchors=anchors)


@pytest.mark.parametrize("anchor", [0.0, 0.3, 0.6, 0.8, 1.0])
def test_exact_anchors_accepted(anchor):
    contract = ScoreOutputContract(id="test-v1", anchors=(0.0, 0.3, 0.6, 0.8, 1.0))
    scoring = scorer(output_validation=contract)
    value, _ = scoring.parse_judgement(
        json.dumps({"score": anchor, "reason": "Synthetic"})
    )
    assert value == anchor
    assert _scorer_snapshot(scoring)["output_validation"] == contract.model_dump(
        mode="json"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "continuous"),
        ("schema_version", "unknown"),
        ("id", " "),
        ("extra", True),
    ],
)
def test_invalid_contract_shape(field, value):
    with pytest.raises(ValueError):
        ScoreOutputContract.model_validate_json(
            canonical_json({"id": "test-v1", "anchors": [0, 1], field: value})
        )


def test_historical_continuous_output_and_frozen_golden_documents():
    path = Path("tests/fixtures/prospective/legacy.json")
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == "1a5e209688f781fb27ed1ab0ff90d09a1441b71f2b7dac87a6624b5cc694e7b8"
    )
    fixture = json.loads(path.read_text())
    scoring = scorer()
    assert scoring.preparation_configuration == fixture["scorer_configuration"]
    assert "output_validation" not in _scorer_snapshot(scoring)
    assert scoring.parse_judgement('{"score":0.7,"reason":"Synthetic."}')[0] == 0.7
    models = {
        "source": RunResult,
        "prepared": PreparedReplay,
        "manifest": CalibrationManifest,
        "frozen": FrozenAnnotationSet,
        "analysis": CalibrationResult,
    }
    for key, model in models.items():
        saved = fixture["documents"][key]
        loaded = model.model_validate_json(saved["json"])
        assert loaded.model_dump_json() == saved["json"]
        assert fingerprint(loaded.model_dump(mode="json")) == saved["hash"]


def test_contract_changes_evaluator_input_and_historical_compatibility():
    old = scorer()
    source, cases, _ = fixture_run(old)
    prepared = prepare(source, cases, old)
    new = scorer(
        output_validation=ScoreOutputContract(
            id="test-v1", anchors=(0.0, 0.3, 0.6, 0.8, 1.0)
        )
    )
    evaluator = EvaluatorConfiguration(
        scorer_json=canonical_json(old.preparation_configuration), judge=settings()
    )
    kwargs = {
        "judge_configuration": settings(),
        "database_locator": "runs/source.sqlite",
        "case_id": "a",
        "source_attempt": 4,
        "attempts": 1,
        "source_evaluator": evaluator,
    }
    with pytest.raises(ValueError):
        prepare_replay(source, cases, new, **kwargs)
    changed = prepare_replay(source, cases, new, allow_reconfigured=True, **kwargs)
    assert changed.compatibility == "different"
    assert changed.input_hash != prepared.input_hash
    assert any("output_validation" in d for d in changed.differences)
