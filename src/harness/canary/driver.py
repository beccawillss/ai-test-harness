"""Single-use bounded canary APIs. Every transport is explicitly supplied."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from harness.canary.inputs import (
    ANCHORS,
    JUDGE_MODEL,
    JUDGE_ORDER,
    TARGET_MODEL,
    TARGET_REVISION,
    TARGET_TURNS,
    judge_inputs,
    roster_hash,
    scorer,
)
from harness.canary.recording import CanaryError, CanaryStore, ProviderTransport
from harness.core.fingerprints import fingerprint
from harness.core.models import TargetResponse, TestCase
from harness.judges.openai import OpenAIJudge
from harness.targets._salesagent_contract import (
    ARGUMENTS,
    WARMTH_RESULTS,
    Chat,
    ToolResult,
    Trace,
)
from harness.targets.salesagent import SalesAgentTarget


def _trace(raw: Any) -> dict[str, Any]:
    trace = Trace.model_validate(raw)
    datetime.fromisoformat(trace.timestamp)
    if trace.errors:
        raise CanaryError("Canary trace reports an execution error")
    validation = trace.recommendation_validation
    if validation.validation_errors or not all(
        getattr(validation, field)
        for field in (
            "all_products_exist",
            "prices_match_catalogue",
            "urls_match_catalogue",
            "stock_claims_validated",
        )
    ):
        raise CanaryError("Canary recommendation validation failed")
    safe = trace.model_dump(mode="json")
    if safe["pricing"] is not None:
        safe["pricing"]["base_price"] = safe["pricing"].pop("original_price")
    for original, tool in zip(trace.tool_calls, safe["tool_calls"]):
        envelope = ToolResult.model_validate(original.result)
        if (
            original.status != "success"
            or not envelope.success
            or envelope.error is not None
            or envelope.tool_name != original.tool_name
        ):
            raise CanaryError("Canary tool did not succeed")
        tool["arguments"] = (
            ARGUMENTS[original.tool_name]
            .model_validate(original.arguments)
            .model_dump(mode="json", exclude_unset=True)
        )
        tool["result"] = {
            "tool_name": original.tool_name,
            "success": True,
            "error": None,
            "data": WARMTH_RESULTS[original.tool_name]
            .model_validate(envelope.data)
            .model_dump(mode="json"),
        }
    return safe


def _observations(slot: str, chat: dict[str, Any], trace: dict[str, Any]) -> None:
    """Functional canary checks; not new Study assertions or scoring rules."""
    calls = trace["tool_calls"]
    names = {c["tool_name"] for c in calls}
    constraints = trace["resolved_constraints"]
    if trace["model"] != TARGET_MODEL:
        raise CanaryError("Canary observed an unexpected target model")
    if slot == "B1":
        if (
            any(value is not None and value != [] for value in constraints.values())
            or chat["promotion"] is not None
            or chat["pricing"] is not None
            or chat["recommendations"]
        ):
            raise CanaryError("Fresh-session canary evidence contains shopping state")
        return  # Truthfulness of the prose is also reviewed by a human.
    required = (
        {"get_product", "validate_discount"}
        if slot == "A2"
        else {"search_products", "get_product", "check_inventory"}
    )
    if not required <= names:
        raise CanaryError("Expected canary tool coverage is missing")
    pid, colour, size, stock, price = (
        ("ACC-001", "Rust", "One Size", 6, "22.00")
        if slot == "B2"
        else ("ACC-003", "Moss", "20L", 5, "55.00")
    )
    products = [c["result"]["data"] for c in calls if c["tool_name"] == "get_product"]
    if not any(p["product_id"] == pid and p["price"] == price for p in products):
        raise CanaryError("Canary product facts differ")
    if (
        str(constraints.get("colour")).casefold() != colour.casefold()
        or str(constraints.get("size")).casefold() != size.casefold()
    ):
        raise CanaryError("Canary variant state differs")
    if slot != "A2":
        inventory = [
            c["result"]["data"] for c in calls if c["tool_name"] == "check_inventory"
        ]
        if not any(
            i["product_id"] == pid
            and i["colour"] == colour
            and i["size"] == size
            and i["stock"] == stock
            and i["available"]
            for i in inventory
        ):
            raise CanaryError("Canary inventory differs")
        if chat["promotion"] is not None or (
            chat["pricing"] and chat["pricing"]["discount_code"] is not None
        ):
            raise CanaryError("Canary inherited an unrequested promotion")
    else:
        promotion, pricing = chat["promotion"], chat["pricing"]
        validated = [
            c["result"]["data"] for c in calls if c["tool_name"] == "validate_discount"
        ]
        if not any(
            p["code"] == "WELCOME10" and p["valid"] and p["discount_percent"] == "10.00"
            for p in validated
        ):
            raise CanaryError("Canary promotion validation differs")
        if (
            not promotion
            or promotion["code"] != "WELCOME10"
            or not promotion["valid"]
            or promotion["discount_percent"] != "10.00"
            or not pricing
            or pricing["product_id"] != pid
            or pricing["base_price"] != "55.00"
            or pricing["final_price"] != "49.50"
            or pricing["discount_code"] != "WELCOME10"
            or pricing["discount_percent"] != "10.00"
            or pricing["currency"] != "GBP"
        ):
            raise CanaryError("Canary displayed quote differs")


class ReplayTransport(httpx.MockTransport):
    """Exact saved public exchanges only; any miss fails, never opens a socket."""

    def __init__(self, exchanges: dict[str, Any], conversation: str):
        if set(exchanges) != {t.slot for t in TARGET_TURNS} or conversation not in {
            "A",
            "B",
        }:
            raise CanaryError("Replay requires the exact canary roster")
        self.exchanges = json.loads(json.dumps(exchanges))
        self.turns = [t for t in TARGET_TURNS if t.conversation == conversation]
        self.position = 0
        super().__init__(self._reply)

    def _reply(self, request: httpx.Request) -> httpx.Response:
        if self.position >= 4:
            raise CanaryError("Offline replay exhausted")
        turn = self.turns[self.position // 2]
        saved = self.exchanges[turn.slot]
        if self.position % 2 == 0:
            expected = {"message": turn.message}
            if self.position:
                expected["session_id"] = self.exchanges[self.turns[0].slot]["chat"][
                    "session_id"
                ]
            if (
                request.method != "POST"
                or request.url.path != "/api/v1/chat"
                or json.loads(request.content) != expected
            ):
                raise CanaryError("Offline replay request mismatch")
            result = saved["chat"]
        else:
            if (
                request.method != "GET"
                or request.url.path != "/api/v1/traces/" + saved["chat"]["trace_id"]
            ):
                raise CanaryError("Offline trace replay mismatch")
            result = saved["trace"]
        self.position += 1
        return httpx.Response(200, json=result)


def replay_target(exchanges: dict[str, Any]) -> dict[str, TargetResponse]:
    responses = {}
    for conversation in ("A", "B"):
        transport = ReplayTransport(exchanges, conversation)
        target = SalesAgentTarget(
            "http://127.0.0.1:1",
            transport=transport,
            target_revision=TARGET_REVISION,
            evidence_version="salesagent-evidence-v3",
        )
        try:
            case = TestCase(
                id="NONSTUDY-CANARY-" + conversation,
                input={
                    "turns": [
                        t.message
                        for t in TARGET_TURNS
                        if t.conversation == conversation
                    ]
                },
            )
            responses[conversation] = target.invoke(case)
            if transport.position != 4:
                raise CanaryError("Incomplete offline replay")
        finally:
            target.close()
    return responses


def save_human_ratings(
    store: CanaryStore,
    ratings: dict[str, dict[str, Any]],
    *,
    reviewer: str,
    exposure: str,
) -> None:
    """Record eight independent human anchors before any judge dispatch/reveal."""
    store.guard()
    if (store.path / "reserved-judge-stage.json").exists():
        raise CanaryError("Human ratings must precede all canary judging")
    if (
        reviewer != "beccawillss"
        or exposure != "not_seen"
        or set(ratings) != set(JUDGE_ORDER)
    ):
        raise CanaryError(
            "Complete ratings and a truthful unexposed declaration are required"
        )
    for rating in ratings.values():
        if (
            set(rating) != {"score", "reason"}
            or type(rating["score"]) not in (float, int)
            or rating["score"] not in ANCHORS
            or not isinstance(rating["reason"], str)
            or not rating["reason"].strip()
        ):
            raise CanaryError("Human ratings require valid anchors and reasons")
    data = {
        "roster_hash": roster_hash(),
        "reviewer": reviewer,
        "judge_output_exposure": exposure,
        "ratings": ratings,
    }
    store.write("human-ratings", data)
    store.write("human-ratings-receipt", {"fingerprint": fingerprint(data)})


def export_human_packet(store: CanaryStore) -> None:
    """Unscored synthetic evidence plus a blank, truthfully unknown declaration."""
    store.guard()
    if (store.path / "reserved-judge-stage.json").exists():
        raise CanaryError("Canary human packet must precede judging")
    prepared = judge_inputs()
    examples = []
    for identifier, value in prepared.items():
        if value.evidence_json is None:
            raise CanaryError("Synthetic human evidence is missing")
        examples.append(
            {
                "id": identifier,
                "evidence": json.loads(value.evidence_json),
                "prompt_hash": value.prompt_hash,
            }
        )
    store.write(
        "human-packet",
        {
            "roster_hash": roster_hash(),
            "rubric": scorer().rubric,
            "anchors": list(ANCHORS),
            "pass_threshold": 0.7,
            "examples": examples,
        },
    )
    store.write(
        "human-draft",
        {
            "reviewer": "beccawillss",
            "judge_output_exposure": "unknown",
            "ratings": {
                identifier: {"score": None, "reason": ""} for identifier in prepared
            },
        },
    )


def _ratings(store: CanaryStore) -> dict[str, Any]:
    data = json.loads((store.path / "human-ratings.json").read_text())
    receipt = json.loads((store.path / "human-ratings-receipt.json").read_text())
    if (
        receipt != {"fingerprint": fingerprint(data)}
        or data["roster_hash"] != roster_hash()
        or set(data["ratings"]) != set(JUDGE_ORDER)
        or data["reviewer"] != "beccawillss"
        or data["judge_output_exposure"] != "not_seen"
    ):
        raise CanaryError("Human rating receipt differs")
    for rating in data["ratings"].values():
        scorer().parse_judgement(json.dumps(rating))
    return data


class CanaryDriver:
    def __init__(self, store: CanaryStore):
        self.store = store

    def run_target(
        self, transport: httpx.BaseTransport, *, base_url: str = "http://127.0.0.1:1"
    ) -> dict[str, TargetResponse]:
        self.store.guard()
        if not isinstance(transport, httpx.BaseTransport):
            raise CanaryError("An explicit target transport is required")
        if self.store.mode == "offline" and not isinstance(
            transport, httpx.MockTransport
        ):
            raise CanaryError("Offline target I/O requires an explicit mock transport")
        url = httpx.URL(base_url)
        if (
            url.scheme != "http"
            or url.host != "127.0.0.1"
            or url.userinfo
            or url.query
            or url.fragment
            or url.path not in ("", "/")
        ):
            raise CanaryError("Canary target must be a loopback HTTP server")
        self.store.write("reserved-target-stage", {"state": "reserved", "posts": 4})
        sessions: dict[str, str] = {}
        exchanges: dict[str, Any] = {}
        trace_ids: set[str] = set()
        try:
            if (
                self.store.mode == "live"
                and not (self.store.path / "bounded-target-client.json").exists()
            ):
                raise CanaryError("Live target requires the bounded metadata client")
            with httpx.Client(
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(connect=5, read=600, write=10, pool=5),
            ) as client:

                def request(method: str, path: str, body: Any = None) -> Any:
                    self.store.guard()
                    reply = client.send(
                        httpx.Request(method, str(url).rstrip("/") + path, json=body),
                        auth=None,
                        follow_redirects=False,
                    )
                    reply.raise_for_status()
                    return reply.json()

                if request("GET", "/health") != {"status": "ok"}:
                    raise CanaryError("Canary health check failed")
                schema = request("GET", "/openapi.json")
                if (
                    "post" not in schema["paths"]["/api/v1/chat"]
                    or "get" not in schema["paths"]["/api/v1/traces/{trace_id}"]
                ):
                    raise CanaryError("Canary schema check failed")
                for turn in TARGET_TURNS:
                    body = {"message": turn.message}
                    if turn.conversation in sessions:
                        body["session_id"] = sessions[turn.conversation]
                    self.store.write(
                        "reserved-chat-" + turn.slot,
                        {"slot": turn.slot, "state": "reserved"},
                    )
                    chat = Chat.model_validate(
                        request("POST", "/api/v1/chat", body)
                    ).model_dump(mode="json")
                    if chat["pricing"] is not None:
                        chat["pricing"]["base_price"] = chat["pricing"].pop(
                            "original_price"
                        )
                    session, trace_id = chat["session_id"], chat["trace_id"]
                    if (
                        (
                            turn.conversation in sessions
                            and sessions[turn.conversation] != session
                        )
                        or (
                            turn.conversation not in sessions
                            and session in sessions.values()
                        )
                        or trace_id in trace_ids
                        or trace_id in {".", ".."}
                    ):
                        raise CanaryError("Canary session or trace identity differs")
                    sessions[turn.conversation] = session
                    trace_ids.add(trace_id)
                    self.store.write("chat-" + turn.slot, chat)
                    path = "/api/v1/traces/" + quote(trace_id, safe="")
                    trace = _trace(request("GET", path))
                    if (
                        trace["trace_id"] != trace_id
                        or trace["session_id"] != session
                        or trace["user_message"] != turn.message
                        or trace["turn_index"] != int(turn.slot[1])
                        or [c["sequence"] for c in trace["tool_calls"]]
                        != list(range(1, len(trace["tool_calls"]) + 1))
                    ):
                        raise CanaryError("Canary trace correlation differs")
                    self.store.write("trace-" + turn.slot, trace)
                    if _trace(request("GET", path)) != trace:
                        raise CanaryError("Canary trace reread differs")
                    _observations(turn.slot, chat, trace)
                    if self.store.mode == "live" and not any(
                        value.get("kind") == "provider_attempt"
                        and value.get("role") == "target"
                        and value.get("slot") == turn.slot
                        for path in self.store.path.glob("event-*.json")
                        for value in [json.loads(path.read_text())]
                    ):
                        raise CanaryError("Target provider telemetry is missing")
                    exchanges[turn.slot] = {"chat": chat, "trace": trace}
            result = replay_target(exchanges)
            self.store.guard()
            self.store.write(
                "target-completed",
                {"slots": list(exchanges), "adapter_replay": "passed"},
            )
            return result
        except BaseException:  # noqa: BLE001 - cancellation must also stop paid dispatch
            self.store.stop("target_failure")
            raise CanaryError("Canary target stopped; no replacement calls") from None

    def run_judge(
        self,
        transport: httpx.BaseTransport,
        *,
        api_key: str = "offline-canary-placeholder",
    ) -> dict[str, Any]:
        self.store.guard()
        try:
            _ratings(
                self.store
            )  # Before client construction, reservation or provider work.
            if self.store.mode == "offline" and api_key != "offline-canary-placeholder":
                raise CanaryError("Offline canary must not use provider credentials")
            provider = ProviderTransport(self.store, transport, role="judge")
            self.store.write(
                "reserved-judge-stage", {"state": "reserved", "requests": 16}
            )
            judge = OpenAIJudge(
                api_key=api_key,
                model=JUDGE_MODEL,
                max_output_tokens=8192,
                connect_timeout=5,
                read_timeout=300,
                write_timeout=10,
                pool_timeout=5,
                transport=provider,
            )
            try:
                prepared = judge_inputs()
                for index, identifier in enumerate(JUDGE_ORDER):
                    self.store.guard()
                    _ratings(self.store)
                    slot = f"{identifier}-{index // 8 + 1}"
                    with provider.logical(slot):
                        reply = judge(prepared[identifier].prompt)
                        value, reason = scorer().parse_judgement(reply.text)
                        self.store.write(
                            "judge-" + slot,
                            {
                                "example": identifier,
                                "repetition": index // 8 + 1,
                                "prompt_hash": prepared[identifier].prompt_hash,
                                "score": value,
                                "reason": reason,
                                "observation": reply.observation.model_dump(
                                    mode="json"
                                ),
                            },
                        )
                self.store.guard()
                self.store.write("judge-completed", {"requests": 16})
            finally:
                judge.close()
            return self.store.accounting()
        except BaseException:  # noqa: BLE001 - cancellation must also stop paid dispatch
            self.store.stop("judge_failure")
            raise CanaryError("Canary judging stopped; no replacement calls") from None


def reveal_judgments(store: CanaryStore) -> list[dict[str, Any]]:
    _ratings(store)
    return [
        json.loads(
            (store.path / f"judge-{identifier}-{index // 8 + 1}.json").read_text()
        )
        for index, identifier in enumerate(JUDGE_ORDER)
    ]


def load_target_replay(directory: Path) -> dict[str, TargetResponse]:
    """Pure public-evidence replay; neither constructs nor accepts network I/O."""
    exchanges = {
        turn.slot: {
            kind: json.loads((directory / f"{kind}-{turn.slot}.json").read_text())
            for kind in ("chat", "trace")
        }
        for turn in TARGET_TURNS
    }
    return replay_target(exchanges)
