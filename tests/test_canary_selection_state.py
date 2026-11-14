"""Pinned app persistence with v3 wording and scripted patches, never extraction proof."""

import pytest

pytest.importorskip("openai", reason="Pinned application runtime is optional")
pytest.importorskip("salesagent", reason="Pinned Sales Agent source required")

from salesagent.api.models import ChatRequest
from test_canary_state import patch, scripted_turn, service_for

from harness.canary.selection_acceptance import assess_selection
from harness.canary.selection_v3 import TURNS


def selected_patch():
    return patch(
        colour={"operation": "set", "value": "Moss"},
        size={"operation": "set", "value": "20L"},
        maximum_price={"operation": "set", "value": "60.00"},
    )


def test_v3_explicit_patch_persists_across_nonleading_followup_and_independent_b():
    service, traces, sessions, client = service_for(
        scripted_turn(selected_patch(), inventory=True)
        + scripted_turn()
        + scripted_turn(inventory=True)
    )
    replies = []
    for turn in TURNS[:3]:
        replies.append(
            service.chat(
                ChatRequest(session_id=turn.conversation, message=turn.message)
            )
        )
    assert (
        client.contexts[1]["colour"]
        is client.contexts[1]["size"]
        is client.contexts[1]["maximum_price"]
        is None
    )
    assert (
        client.contexts[2]["colour"],
        client.contexts[2]["size"],
        client.contexts[2]["maximum_price"],
    ) == ("Moss", "20L", "60.00")
    assert sessions.get_state("B").resolved_constraints.colour is None
    assert sessions.get_state("B").resolved_constraints.maximum_price is None
    assert sessions.get_state("A").resolved_constraints.colour == "Moss"
    assert len(sessions.get_state("A").history) == 2
    assert sessions.get_state("A").history[0].recommended_product_ids == ("ACC-003",)
    assert traces.get(replies[2].trace_id).turn_index == 2
    assert replies[0].recommendations[0].matched_variant is None
    assert not client.responses


@pytest.mark.parametrize("missing", [True, False])
def test_scripted_missing_antecedent_and_lost_current_state_remain_distinct(missing):
    initial = (
        patch(maximum_price={"operation": "set", "value": "60.00"})
        if missing
        else selected_patch()
    )
    later = patch(colour={"operation": "clear", "value": None})
    service, traces, _, client = service_for(
        scripted_turn(initial, inventory=True)
        + scripted_turn()
        + scripted_turn(later, inventory=True)
    )
    snapshots = {}
    reports = {}
    for turn in TURNS[:3]:
        reply = service.chat(
            ChatRequest(session_id=turn.conversation, message=turn.message)
        )
        saved = {
            "chat": reply.model_dump(mode="json"),
            "trace": traces.get(reply.trace_id).model_dump(mode="json"),
        }
        reports[turn.slot] = assess_selection(turn.slot, **saved, previous=snapshots)
        snapshots[turn.slot] = saved
    assert reports["A1"].current_state.status == ("FAIL" if missing else "PASS")
    assert reports["A2"].retention.status == ("SKIP" if missing else "FAIL")
    assert reports["A2"].current_state.status == "FAIL"
    assert not client.responses
