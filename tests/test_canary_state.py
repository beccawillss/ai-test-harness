"""Optional pinned-application regressions; scripted model snapshots, no server.

Run with the approved Sales Agent source on PYTHONPATH and its locked runtime.
No application source or test helper is modified or copied into the harness.
"""

import json
from hashlib import sha256
from pathlib import Path

import pytest

pytest.importorskip("openai", reason="Pinned application runtime is optional")
salesagent = pytest.importorskip(
    "salesagent", reason="Pinned Sales Agent source required"
)

from pydantic import ValidationError
from salesagent.agent.final_output import AgentFinalOutput, ConstraintUpdates
from salesagent.agent.orchestrator import AgentOrchestrator
from salesagent.agent.responses_client import (
    FunctionCall,
    ModelResponse,
    ResponseMessage,
    ResponseUsage,
)
from salesagent.agent.tools.dispatcher import ToolDispatcher
from salesagent.api.models import ChatRequest
from salesagent.repositories.products import ProductRepository
from salesagent.repositories.promotions import PromotionRepository
from salesagent.repositories.sessions import InMemorySessionRepository
from salesagent.repositories.traces import InMemoryTraceRepository
from salesagent.services.chat import ChatService
from salesagent.services.commerce import CommerceService
from salesagent.services.pricing import PromotionPricingService
from salesagent.services.recommendations import RecommendationHydrator

from harness.canary.controller import FIXTURES
from harness.canary.inputs import TARGET_MODEL, TARGET_TURNS

APPLICATION = Path(salesagent.__file__).resolve().parents[2]


class ScriptedStateClient:
    """Only retain public context data, never full requests or instructions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.contexts = []

    def create_response(self, request):
        if request.previous_response_id is None:
            for message in request.input:
                if not isinstance(message, ResponseMessage):
                    continue
                try:
                    content = json.loads(message.content)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(content, dict)
                    and content.get("type") == "salesagent_context"
                ):
                    self.contexts.append(content["resolved_constraints"])
        if not self.responses:
            raise AssertionError("Unexpected model dispatch in scripted state test")
        return self.responses.pop(0)


def patch(**fields):
    values = ConstraintUpdates.retain_all().model_dump(mode="json")
    values.update(fields)
    return ConstraintUpdates.model_validate(values)


def scripted_turn(updates=None, *, inventory=False, colour="Moss", size="20L"):
    responses = []
    if inventory:
        responses.append(
            ModelResponse(
                response_id="synthetic-inventory",
                output_text="",
                function_calls=(
                    FunctionCall(
                        call_id="synthetic-inventory",
                        name="check_inventory",
                        arguments_json=json.dumps(
                            {"product_id": "ACC-003", "colour": colour, "size": size}
                        ),
                    ),
                ),
                usage=ResponseUsage(),
                status="completed",
            )
        )
    final = AgentFinalOutput(
        message="Synthetic shopper-facing answer.",
        nominated_product_ids=("ACC-003",) if inventory else (),
        nominated_promotion_code=None,
        constraint_updates=updates or ConstraintUpdates.retain_all(),
    )
    responses.append(
        ModelResponse(
            response_id="synthetic-final",
            output_text=final.model_dump_json(),
            function_calls=(),
            usage=ResponseUsage(),
            status="completed",
        )
    )
    return responses


def service_for(responses):
    assert {
        name: sha256((APPLICATION / "data" / name).read_bytes()).hexdigest()
        for name in FIXTURES
    } == FIXTURES
    commerce = CommerceService(
        ProductRepository(APPLICATION / "data/products.json"),
        PromotionRepository(APPLICATION / "data/discounts.json"),
    )
    client = ScriptedStateClient(responses)
    traces, sessions = InMemoryTraceRepository(), InMemorySessionRepository()
    orchestrator = AgentOrchestrator(
        responses_client=client,
        dispatcher=ToolDispatcher(commerce),
        model=TARGET_MODEL,
        reasoning_effort="low",
        max_output_tokens=2000,
    )
    service = ChatService(
        traces,
        orchestrator,
        RecommendationHydrator(commerce),
        PromotionPricingService(),
        sessions,
    )
    return service, traces, sessions, client


def test_explicit_variant_updates_commit_and_inventory_does_not_select_another_variant():
    updates = patch(
        colour={"operation": "set", "value": "Moss"},
        size={"operation": "set", "value": "20L"},
    )
    service, traces, sessions, client = service_for(
        scripted_turn(updates, inventory=True)
        + scripted_turn(inventory=True, colour="Black")
    )
    first = service.chat(ChatRequest(session_id="A", message="Please keep Moss 20L."))
    second = service.chat(
        ChatRequest(
            session_id="A",
            message="Also check Black stock, without changing my preference.",
        )
    )
    for response in (first, second):
        trace = traces.get(response.trace_id)
        assert (trace.resolved_constraints.colour, trace.resolved_constraints.size) == (
            "Moss",
            "20L",
        )
        assert response.recommendations[0].matched_variant is None
    assert client.contexts[1]["colour"] == "Moss"
    assert client.contexts[1]["size"] == "20L"
    state = sessions.get_state("A")
    assert (state.resolved_constraints.colour, state.resolved_constraints.size) == (
        "Moss",
        "20L",
    )
    assert [c.field for c in traces.get(first.trace_id).constraint_changes] == [
        "colour",
        "size",
    ]
    assert traces.get(second.trace_id).constraint_changes == []
    assert not client.responses


def test_a_and_b_are_independent_and_preferences_survive_successive_a_turns():
    updates = patch(
        colour={"operation": "set", "value": "Moss"},
        size={"operation": "set", "value": "20L"},
    )
    service, traces, sessions, client = service_for(
        scripted_turn(updates) + scripted_turn() + scripted_turn()
    )
    a1 = service.chat(ChatRequest(session_id="A", message="Moss 20L, please."))
    b1 = service.chat(
        ChatRequest(session_id="B", message="Have I given any preferences?")
    )
    a2 = service.chat(ChatRequest(session_id="A", message="Keep that exact variant."))
    assert client.contexts[0]["colour"] is None
    assert client.contexts[1]["colour"] is None
    assert client.contexts[1]["size"] is None
    assert (client.contexts[2]["colour"], client.contexts[2]["size"]) == ("Moss", "20L")
    assert traces.get(a1.trace_id).turn_index == traces.get(b1.trace_id).turn_index == 1
    assert traces.get(a2.trace_id).turn_index == 2
    assert sessions.get_state("B").resolved_constraints.colour is None
    assert sessions.get_state("B").resolved_constraints.size is None
    assert len(sessions.get_state("A").history) == 2
    assert len(sessions.get_state("B").history) == 1


def test_null_updates_retain_but_explicit_clear_removes_only_selected_preferences():
    set_variant = patch(
        colour={"operation": "set", "value": "Moss"},
        size={"operation": "set", "value": "20L"},
    )
    clear_colour = patch(colour={"operation": "clear", "value": None})
    clear_size = patch(size={"operation": "clear", "value": None})
    service, traces, sessions, client = service_for(
        scripted_turn(set_variant)
        + scripted_turn()
        + scripted_turn(clear_colour)
        + scripted_turn(clear_size)
    )
    replies = [
        service.chat(ChatRequest(session_id="A", message=message))
        for message in (
            "Moss 20L.",
            "Keep them.",
            "Forget the colour.",
            "Forget the size.",
        )
    ]
    states = [traces.get(r.trace_id).resolved_constraints for r in replies]
    assert [(s.colour, s.size) for s in states] == [
        ("Moss", "20L"),
        ("Moss", "20L"),
        (None, "20L"),
        (None, None),
    ]
    assert traces.get(replies[1].trace_id).constraint_changes == []
    assert [c.field for c in traces.get(replies[2].trace_id).constraint_changes] == [
        "colour"
    ]
    assert [c.field for c in traces.get(replies[3].trace_id).constraint_changes] == [
        "size"
    ]
    assert sessions.get_state("A").resolved_constraints.colour is None
    assert len(client.contexts) == 4


@pytest.mark.parametrize("field", ["colour", "size"])
def test_absent_strict_output_field_is_invalid_not_an_implicit_clear(field):
    values = ConstraintUpdates.retain_all().model_dump(mode="json")
    del values[field]
    with pytest.raises(ValidationError):
        ConstraintUpdates.model_validate(values)


@pytest.mark.parametrize(
    "updates",
    [
        patch(maximum_price={"operation": "set", "value": "60.00"}),
        patch(
            maximum_price={"operation": "set", "value": "60.00"},
            colour={"operation": "clear", "value": None},
            size={"operation": "clear", "value": None},
        ),
    ],
)
def test_a1_missing_variant_state_is_reproduced_without_an_inventory_or_merger_failure(
    updates,
):
    service, traces, sessions, client = service_for(
        scripted_turn(updates, inventory=True)
    )
    response = service.chat(
        ChatRequest(session_id="A", message=TARGET_TURNS[0].message)
    )
    trace = traces.get(response.trace_id)
    assert trace.errors == []
    assert trace.tool_calls[0].tool_name == "check_inventory"
    assert trace.tool_calls[0].result["data"]["available"] is True
    assert trace.tool_calls[0].result["data"]["stock"] == 5
    assert str(trace.resolved_constraints.maximum_price) == "60.00"
    assert (trace.resolved_constraints.colour, trace.resolved_constraints.size) == (
        None,
        None,
    )
    assert [c.field for c in trace.constraint_changes] == ["maximum_price"]
    assert sessions.get_state("A").history[0].user_message == TARGET_TURNS[0].message
    assert response.recommendations[0].matched_variant is None
    assert not client.responses


def test_explicit_patch_fixes_the_scripted_a1_state_without_inventing_from_tools():
    updates = patch(
        maximum_price={"operation": "set", "value": "60.00"},
        colour={"operation": "set", "value": "Moss"},
        size={"operation": "set", "value": "20L"},
    )
    service, traces, _, client = service_for(scripted_turn(updates))
    response = service.chat(
        ChatRequest(session_id="A", message=TARGET_TURNS[0].message)
    )
    trace = traces.get(response.trace_id)
    assert trace.tool_calls == []
    assert (trace.resolved_constraints.colour, trace.resolved_constraints.size) == (
        "Moss",
        "20L",
    )
    assert not client.responses
