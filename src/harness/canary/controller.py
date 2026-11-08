"""Opt-in, single-worker target controller. Importing it performs no I/O.

No judge stage, credential discovery, subprocess launcher, retry or resume API.
Live readiness is an operator attestation, never permission inferred by this code.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import platform
import re
import socket
import subprocess
import sys
import threading
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Self

import httpx

from harness.canary.inputs import TARGET_REVISION, roster_hash
from harness.canary.recording import (
    BoundedResponsesClient,
    CanaryError,
    CanaryStore,
    ProviderTransport,
)
from harness.core.dataset import load_dataset

HARNESS_REVISION = "d43a568168363d2dc4073636a7c8127752afc2c1"
DATASET_HASH = "4a0e40d6dce4b78cc194352bf23d69dabcc8fe3c0f440d50f2cce2bd6a956028"
FIXTURES = {
    "products.json": "70960848556e1e63c1bd3337203ab057a9fae1e7f6d343fb383f85a838c541ab",
    "discounts.json": "3147b6863b9458c928459cbb824d01b0e3b73aa2c5da2979debb78de4e1caf0c",
}
OFFLINE_KEY = "offline-canary-placeholder"
C3A_FILES = frozenset(
    {
        "src/harness/canary/controller.py",
        "src/harness/canary/human.py",
        "src/harness/canary/driver.py",
        "src/harness/canary/recording.py",
        "tests/test_canary_controller.py",
        "tests/test_canary_preparation.py",
        "docs/plans/study-v1-c3a-canary-preparation.md",
        "docs/study-v1-c3a-canary-preparation.md",
    }
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, text=True
    ).strip()


def _harness_revision(root: Path) -> str:
    """Permit the scoped C3a commit without weakening the approved base pin."""
    _git(root, "merge-base", "--is-ancestor", HARNESS_REVISION, "HEAD")
    changed = set(_git(root, "diff", HARNESS_REVISION, "--name-only").splitlines())
    untracked = set(
        _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    )
    if (changed | untracked) - C3A_FILES:
        raise CanaryError("Harness source differs outside the approved C3a inventory")
    return _git(root, "rev-parse", "HEAD")


def verify_runtime(harness_root: Path, application_root: Path) -> dict[str, Any]:
    """Read-only checks, before SDK/app construction. Never loads credentials."""
    try:
        harness_root, application_root = (
            harness_root.resolve(),
            application_root.resolve(),
        )
        revision = _harness_revision(harness_root)
        if (
            Path(__file__).resolve().parents[3] != harness_root
            or _git(application_root, "rev-parse", "HEAD") != TARGET_REVISION
            or _git(application_root, "status", "--porcelain", "--untracked-files=all")
        ):
            raise ValueError
        dataset = load_dataset(
            harness_root / "datasets/salesagent/study-v1/dataset.json"
        )
        if len(dataset.cases) != 50 or dataset.full_dataset_hash != DATASET_HASH:
            raise ValueError
        fixtures = {
            name: sha256((application_root / "data" / name).read_bytes()).hexdigest()
            for name in FIXTURES
        }
        if fixtures != FIXTURES:
            raise ValueError
        if any(name.startswith(("OPENAI_", "SALESAGENT_")) for name in os.environ):
            # salesagent.main has an import-time default app; prevent its
            # Settings.from_environment() from consuming ambient configuration.
            raise CanaryError(
                "Unset ambient OPENAI_/SALESAGENT_ settings before startup"
            )
        application = importlib.import_module("salesagent")
        if application.__file__ is None or (
            Path(application.__file__).resolve()
            != application_root / "src/salesagent/__init__.py"
        ):
            raise ValueError
        for name, module in tuple(sys.modules.items()):
            source = getattr(module, "__file__", None)
            if (
                name.startswith("harness.")
                and source
                and not Path(source)
                .resolve()
                .is_relative_to(harness_root / "src/harness")
            ):
                raise ValueError
            if (
                name.startswith("salesagent.")
                and source
                and not Path(source)
                .resolve()
                .is_relative_to(application_root / "src/salesagent")
            ):
                raise ValueError
        lock = tomllib.loads((application_root / "uv.lock").read_text())
        versions = {}
        for package in lock["package"]:
            if "registry" not in package.get("source", {}):
                continue
            name = package["name"]
            if name in {"colorama", "httpx2-jsfetch"}:
                continue  # Not part of the supported POSIX worker environment.
            versions[name] = importlib.metadata.version(name)
            if versions[name] != package["version"]:
                raise ValueError
        if sys.version_info[:2] != (3, 13):
            raise ValueError
        return {
            "harness_revision": revision,
            "harness_base_revision": HARNESS_REVISION,
            "application_revision": TARGET_REVISION,
            "harness_root": str(harness_root),
            "application_root": str(application_root),
            "dataset_cases": len(dataset.cases),
            "dataset_turns": sum(
                len(case.input["turns"])
                for case in dataset.cases
                if isinstance(case.input, dict)
            ),
            "dataset_fingerprint": dataset.full_dataset_hash,
            "fixtures": fixtures,
            "roster_hash": roster_hash(),
            "python": platform.python_version(),
            "executable": sys.executable,
            "pid": os.getpid(),
            "packages": versions,
            "lockfiles": {
                name: sha256((root / "uv.lock").read_bytes()).hexdigest()
                for name, root in (
                    ("harness", harness_root),
                    ("application", application_root),
                )
            },
            "controller_sources": {
                p.name: sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
            "live_authority": False,
        }
    except CanaryError:
        raise
    except Exception:  # noqa: BLE001 - never expose external runtime diagnostics
        raise CanaryError(
            "Runtime pin, fixture, dataset, import or lock check failed"
        ) from None


@dataclass(frozen=True)
class LiveReadiness:
    """Manually verified facts and separate target-only authorisation.

    Never populate this from defaults, synthetic evidence or inferred approval.
    No credential value, key fragment or key hash belongs in the attestation.
    """

    authorization_reference: str
    project_id: str
    organization_id: str
    checked_at: str
    evidence_sha256: str
    dedicated_project: bool
    credential_project_verified: bool
    enforced_limit_10_usd_verified: bool
    alerts_verified: bool
    target_model_available: bool
    current_prices_match_c1: bool
    private_storage_verified: bool

    def verify(self) -> None:
        try:
            age = (
                datetime.now(UTC) - datetime.fromisoformat(self.checked_at)
            ).total_seconds()
            flags = [v for v in asdict(self).values() if type(v) is bool]
            if (
                not 0 <= age <= 3600
                or not self.authorization_reference.strip()
                or not re.fullmatch(r"proj_[A-Za-z0-9_-]+", self.project_id)
                or not re.fullmatch(r"org[-_][A-Za-z0-9_-]+", self.organization_id)
                or not re.fullmatch(r"[a-f0-9]{64}", self.evidence_sha256)
                or len(flags) != 7
                or not all(flags)
            ):
                raise ValueError
        except Exception:  # noqa: BLE001 - safe attestation diagnostic only
            raise CanaryError(
                "Fresh verified project controls and separate target approval required"
            ) from None


class LoopbackTransport(httpx.BaseTransport):
    """Explicit local worker I/O; no proxy, redirects, DNS names or retries."""

    def __init__(self, worker: TargetCanaryController):
        if (
            worker.thread is None
            or not worker.thread.is_alive()
            or not worker.server.started
        ):
            raise CanaryError(
                "Local transport requires the running controller-owned worker"
            )
        if worker.store.mode == "offline" and not isinstance(
            worker.provider_transport, httpx.MockTransport
        ):
            raise CanaryError("Offline local worker requires a synthetic provider")
        self.port = worker.port
        self.store = worker.store
        self.delegate = httpx.HTTPTransport(retries=0, trust_env=False)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.store.guard()
        if (
            request.url.scheme != "http"
            or request.url.host != "127.0.0.1"
            or request.url.port != self.port
            or request.url.userinfo
        ):
            raise CanaryError(
                "Worker transport permits its literal loopback endpoint only"
            )
        return self.delegate.handle_request(request)

    def close(self) -> None:
        self.delegate.close()


class TargetCanaryController:
    """One application, SDK and worker, used once. No automatic target execution.

    A context starts/stops the server; only an explicit run_target() sends the
    fixed C1 shopper roster. Use operator-pause.json/operator-stop.json to stop
    subsequent dispatch. A pause is terminal for this run, pending human review.
    """

    def __init__(
        self,
        store: CanaryStore,
        *,
        harness_root: Path,
        application_root: Path,
        provider_transport: httpx.BaseTransport,
        api_key: str = OFFLINE_KEY,
        readiness: LiveReadiness | None = None,
    ):
        store.guard()
        if store.mode == "offline":
            if (
                not isinstance(provider_transport, httpx.MockTransport)
                or api_key != OFFLINE_KEY
                or readiness is not None
            ):
                raise CanaryError(
                    "Synthetic startup requires mock provider and dummy credential only"
                )
        else:
            if readiness is None or not api_key or api_key == OFFLINE_KEY:
                raise CanaryError(
                    "Live startup requires separate approval and supplied credential"
                )
            readiness.verify()
        self.identity = verify_runtime(harness_root, application_root)
        self.harness_root, self.application_root = harness_root, application_root
        self.readiness = readiness
        self.store = store
        self.sdk: Any = None
        self.server: Any = None
        self.thread: threading.Thread | None = None
        self.listener: socket.socket | None = None
        self.port = 0
        self.used = False
        self.thread_failed = False
        self.provider_transport = provider_transport
        # Secret remains in the SDK only; never in the store or identity record.
        openai = importlib.import_module("openai")
        OpenAIResponsesClient = importlib.import_module(
            "salesagent.agent.responses_client"
        ).OpenAIResponsesClient
        Settings = importlib.import_module("salesagent.config").Settings
        create_app = importlib.import_module("salesagent.main").create_app

        provider = ProviderTransport(store, provider_transport, role="target")
        self.provider = provider
        try:
            store.write("reserved-controller", {"state": "reserved", "workers": 1})
            store.write("runtime-identity", self.identity)
            if readiness is not None:
                store.write("target-live-readiness", asdict(readiness))
            self.sdk = openai.OpenAI(
                api_key=api_key,
                organization=readiness.organization_id
                if readiness
                else "offline-organization",
                project=readiness.project_id if readiness else "offline-project",
                max_retries=2,
                timeout=30,
                http_client=httpx.Client(
                    transport=provider, trust_env=False, follow_redirects=False
                ),
            )
            delegate = OpenAIResponsesClient(
                api_key=None, timeout_seconds=30, max_retries=2, sdk_client=self.sdk
            )
            self.app = create_app(
                Settings(openai_api_key=None),
                responses_client=BoundedResponsesClient(delegate, provider),
            )
        except BaseException:  # noqa: BLE001 - interruptions must release resources
            self._stop()
            try:
                if self.sdk is not None:
                    self.sdk.close()
                else:
                    provider.close()
            except Exception:  # noqa: BLE001, S110 - never echo delegate close errors
                pass
            raise CanaryError(
                "Controller assembly failed; no replacement requests"
            ) from None

    def __enter__(self) -> Self:
        uvicorn = importlib.import_module("uvicorn")

        if self.used:
            raise CanaryError("Controller cannot be restarted")
        self.used = True
        try:
            self.store.guard()
            if self.readiness is not None:
                self.readiness.verify()
            if (
                verify_runtime(self.harness_root, self.application_root)
                != self.identity
            ):
                raise CanaryError("Runtime changed between preparation and startup")
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(8)
            self.port = self.listener.getsockname()[1]
            self.server = uvicorn.Server(
                uvicorn.Config(
                    self.app,
                    host="127.0.0.1",
                    port=self.port,
                    workers=1,
                    reload=False,
                    access_log=False,
                    log_config=None,
                    log_level="critical",
                    lifespan="on",
                    timeout_graceful_shutdown=35,
                )
            )

            def serve() -> None:
                try:
                    self.server.run(sockets=[self.listener])
                except BaseException:  # noqa: BLE001 - no thread exception/provider text
                    self.thread_failed = True

            self.thread = threading.Thread(
                target=serve, name="canary-single-worker", daemon=True
            )
            self.thread.start()
            deadline = time.monotonic() + 10
            while not self.server.started:
                self.store.guard()
                if not self.thread.is_alive() or time.monotonic() >= deadline:
                    raise CanaryError("Worker startup did not complete")
                time.sleep(0.01)
            self.store.write(
                "worker-started",
                {
                    "host": "127.0.0.1",
                    "port": self.port,
                    "workers": 1,
                    "pid": os.getpid(),
                    "provider_mode": self.store.mode,
                    "started_at": datetime.now(UTC).isoformat(),
                },
            )
            return self
        except BaseException:  # noqa: BLE001 - interrupted startup must shut down
            self._stop()
            self.close()
            raise CanaryError(
                "Worker startup failed; no target requests authorised"
            ) from None

    def run_target(self) -> dict[str, Any]:
        from harness.canary.driver import CanaryDriver

        if self.thread is None or not self.thread.is_alive() or not self.server.started:
            raise CanaryError("Worker is not running")
        self.store.guard()
        if self.readiness is not None:
            self.readiness.verify()
        return CanaryDriver(self.store).run_target(
            LoopbackTransport(self), base_url=f"http://127.0.0.1:{self.port}"
        )

    def close(self) -> None:
        sdk_closed = False
        try:
            if (
                self.provider.active is not None
                or not (self.store.path / "target-completed.json").exists()
            ):
                self._stop()
            if self.server is not None:
                self.server.should_exit = True
            if self.thread is not None:
                self.thread.join(timeout=40)
                if self.thread.is_alive() or self.provider.active is not None:
                    self._stop()
                    raise CanaryError(
                        "Worker shutdown incomplete; preserve run and inspect process"
                    )
            if self.listener is not None:
                self.listener.close()
            if self.sdk is not None:
                self.sdk.close()
            sdk_closed = True
            if not (self.store.path / "worker-shutdown.json").exists():
                self.store.write(
                    "worker-shutdown",
                    {
                        "worker_stopped": True,
                        "sdk_closed": True,
                        "thread_failed": self.thread_failed,
                        "accounting": self.store.accounting(),
                        "automatic_resume": False,
                    },
                )
        except BaseException:  # noqa: BLE001 - shutdown errors must be safe and terminal
            self._stop()
            raise CanaryError(
                "Worker shutdown incomplete; preserve run and inspect process"
            ) from None
        finally:
            if sdk_closed:
                self.sdk = None

    def _stop(self) -> None:
        try:
            self.store.stop()
        except CanaryError:
            # A failed disk cannot prevent resource cleanup. Exclusive claims
            # remain authoritative; the in-memory gate also remains closed.
            self.store.stopped = True

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None:
            self._stop()
        self.close()
