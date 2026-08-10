from __future__ import annotations

import io
import json
import tempfile
import textwrap
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pd_agent import (
    AgentRuntime,
    ArtifactValidator,
    ContextBundle,
    ContextItem,
    ContextManager,
    ContextRequest,
    FileKnowledgeCache,
    GradleBuildRunner,
    KnowledgeContextSource,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRejection,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeSelector,
    KnowledgeSourceAttempt,
    KnowledgeTrace,
    KnowledgeType,
    MinecraftBrain,
    ProjectContextSource,
    ProjectInspector,
    RunController,
    RunContextSource,
    SelectedKnowledge,
    SourceAuthority,
    YarnKnowledgeSource,
)
from pd_agent.core import AgentMessage, AgentResponse, ExecutionLimits, RunState, RunStatus, ToolCall, ToolResultStatus, ContextSource
from pd_agent.project import ProjectInspectionStatus
from pd_agent.reporting import RunStorage
from pd_agent.tools import ToolExecutor, create_filesystem_tools
from tests.fixtures.fabric_projects import make_dirty_git_project


ROOT = Path(__file__).resolve().parents[2]
YARN_SAMPLE = ROOT / "tests" / "fixtures" / "brain" / "yarn_sample.tiny"
L11_FIXTURE = ROOT / "tests" / "fixtures" / "l11_fabric_fixture"


def _artifact_bytes() -> bytes:
    tiny_text = YARN_SAMPLE.read_text(encoding="utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mappings/mappings.tiny", tiny_text)
    return buffer.getvalue()


def _environment() -> KnowledgeEnvironment:
    return KnowledgeEnvironment(
        minecraft_version="1.21.11",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
    )


def _need(query: str = "Identifier") -> KnowledgeNeed:
    return KnowledgeNeed(
        id="need-1",
        type=KnowledgeType.SYMBOL,
        query=query,
        environment=_environment(),
    )


def _retrieval(query: str = "Identifier") -> KnowledgeRetrievalResult:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    cache_root = Path(tempfile.gettempdir()) / "pdagent-l3-brain-cache"
    brain = MinecraftBrain(source=source, cache=FileKnowledgeCache(cache_root))
    return brain.retrieve(_need(query))


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _runtime_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "settings.gradle.kts", 'rootProject.name = "runtime"\n')
    _write(root / "build.gradle.kts", 'plugins { id("fabric-loom") version "1.8-SNAPSHOT" }\n')
    _write(
        root / "gradle.properties",
        "\n".join(
            [
                "minecraft_version=1.20.1",
                "mappings=1.20.1+build.10",
                "fabric_version=0.92.1+1.20.1",
                "loader_version=0.15.11",
                "loom_version=1.8-SNAPSHOT",
            ]
        )
        + "\n",
    )
    _write(
        root / "src" / "main" / "resources" / "fabric.mod.json",
        textwrap.dedent(
            """
            {
              "schemaVersion": 1,
              "id": "runtime-example",
              "version": "1.0.0",
              "environment": "*",
              "entrypoints": {
                "main": ["com.example.ExampleMod"]
              }
            }
            """
        ).strip()
        + "\n",
    )
    _write(root / "src" / "main" / "java" / "com" / "example" / "ExampleMod.java", "package com.example; class ExampleMod {}\n")
    _write(root / "build-state.txt", "pass\n")
    script = root / "fake_gradle.py"
    _write(
        script,
        textwrap.dedent(
            """
            from __future__ import annotations

            import json
            import sys
            import zipfile
            from pathlib import Path

            root = Path(__file__).resolve().parent
            jar_path = root / "build" / "libs" / "runtime-example-1.0.0.jar"
            jar_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_DEFLATED) as jar:
                jar.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": "runtime-example", "version": "1.0.0", "environment": "*"}))
                jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\\n")
            print("BUILD SUCCESSFUL")
            raise SystemExit(0)
            """
        ).strip()
        + "\n",
    )
    _write(root / "gradlew.bat", f'@echo off\n"{ROOT / ".venv-l0fix" / "Scripts" / "python.exe"}" "{script}" %*\nexit /b %ERRORLEVEL%\n')
    _write(root / "gradlew", "#!/bin/sh\n")
    return root


class ScriptedProvider:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[object] = []

    def execute(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _controller(root: Path, provider: ScriptedProvider, *, context_manager: ContextManager | None = None, limits: ExecutionLimits | None = None):
    storage = RunStorage(root / "runs")
    controller = RunController(
        provider=provider,
        storage=storage,
        build_runner=GradleBuildRunner(reporting=storage),
        artifact_validator=ArtifactValidator(reporting=storage),
        context_manager=context_manager or ContextManager(),
        tool_executor=ToolExecutor(tools=create_filesystem_tools()),
        limits=limits or ExecutionLimits(),
    )
    return controller, storage


def test_selector_accepts_compatible() -> None:
    selector = KnowledgeSelector()
    result = _retrieval("Identifier")

    selected = selector.select(result, budget_bytes=4096)

    assert selected.selected_items
    assert selected.trace.misses == ()
    assert selected.trace.selected_item_ids


def test_selector_rejects_incompatible() -> None:
    selector = KnowledgeSelector()
    need = _need("Identifier")
    result = KnowledgeRetrievalResult(
        status=KnowledgeRetrievalStatus.VERSION_MISMATCH,
        need=need,
        items=(),
        source_results=(),
        error="version mismatch",
    )

    selected = selector.select(result, budget_bytes=4096)

    assert selected.selected_items == ()
    assert "VERSION_MISMATCH" in selected.trace.misses


def test_selector_rejects_unknown_when_corresponds() -> None:
    selector = KnowledgeSelector()
    result = KnowledgeRetrievalResult(
        status=KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE,
        need=_need("Identifier"),
        items=(),
        source_results=(),
        error="unknown compatibility",
    )

    selected = selector.select(result, budget_bytes=4096)

    assert selected.selected_items == ()
    assert "UNKNOWN_COMPATIBILITY" in selected.trace.misses


def test_selector_authority_wins_duplicate() -> None:
    selector = KnowledgeSelector()
    need = _need("Identifier")
    provenance = KnowledgeProvenance(
        source_id="source",
        source_kind="artifact",
        locator="https://example.invalid/a",
        artifact_or_document_version="1",
        revision="1",
        retrieved_at=datetime.now(timezone.utc),
        checksum_algorithm="sha256",
        checksum="abc",
        license_id_or_policy="CC0-1.0",
    )
    authoritative = KnowledgeItem(
        id="a",
        content={"symbol": {"kind": "class", "named": "Identifier"}},
        environment=need.environment,
        authority=SourceAuthority.AUTHORITATIVE_ARTIFACT,
        provenance=provenance,
        metadata={"match_score": 10},
    )
    secondary = KnowledgeItem(
        id="b",
        content={"symbol": {"kind": "class", "named": "Identifier"}},
        environment=need.environment,
        authority=SourceAuthority.SECONDARY,
        provenance=provenance,
        metadata={"match_score": 99},
    )
    result = KnowledgeRetrievalResult(
        status=KnowledgeRetrievalStatus.SUCCESS,
        need=need,
        items=(secondary, authoritative),
        source_results=(),
    )

    selected = selector.select(result, budget_bytes=4096)

    assert [item.id for item in selected.selected_items] == ["a"]
    assert any(rejection.reason == "LOWER_AUTHORITY_DUPLICATE" for rejection in selected.rejected_items)


def test_selector_is_deterministic() -> None:
    selector = KnowledgeSelector()
    result = _retrieval("Registries")

    first = selector.select(result, budget_bytes=4096)
    second = selector.select(result, budget_bytes=4096)

    assert [item.id for item in first.selected_items] == [item.id for item in second.selected_items]
    assert [item.reason for item in first.rejected_items] == [item.reason for item in second.rejected_items]
    assert first.trace.selected_item_ids == second.trace.selected_item_ids


def test_selector_budget_limits_results() -> None:
    selector = KnowledgeSelector()
    result = _retrieval("Registry")

    selected = selector.select(result, budget_bytes=250)

    assert len(selected.selected_items) <= len(result.items)
    assert any(rejection.reason == "CONTEXT_BUDGET" for rejection in selected.rejected_items) or not result.items


def test_trace_records_context_budget() -> None:
    selector = KnowledgeSelector()
    result = _retrieval("Registry")

    selected = selector.select(result, budget_bytes=250)

    assert "CONTEXT_BUDGET" in {rejection.reason for rejection in selected.rejected_items} or not selected.selected_items


def test_context_source_implements_existing_contract() -> None:
    assert isinstance(KnowledgeContextSource(), ContextSource)


def test_metadata_preserves_provenance_and_id() -> None:
    knowledge = _retrieval("Identifier")
    manager = ContextManager()

    bundle = manager.build_context(external_context=(knowledge,))

    item = next(item for item in bundle.items if item.source == "knowledge")
    assert item.metadata["knowledge_item_id"]
    assert item.metadata["source_id"] == "net.fabricmc:yarn"
    assert item.metadata["locator"].startswith("https://maven.fabricmc.net/")
    assert "Identifier" in item.content


def test_content_identifies_retrieved_knowledge() -> None:
    knowledge = _retrieval("Identifier")
    manager = ContextManager()
    bundle = manager.build_context(external_context=(knowledge,))

    item = next(item for item in bundle.items if item.source == "knowledge")
    assert "retrieved external knowledge" in item.content
    assert "Identifier" in item.content


def test_context_manager_accepts_knowledge_source() -> None:
    source = KnowledgeContextSource()
    manager = ContextManager(sources=(("knowledge", source),))

    bundle = manager.build_context(external_context=(_retrieval("Identifier"),))

    assert any(item.source == "knowledge" for item in bundle.items)
    assert manager.last_knowledge_traces


def test_context_reaches_provider_fake(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "provider-proof")
    provider = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    controller, storage = _controller(root, provider, context_manager=ContextManager())
    knowledge = _retrieval("Identifier")

    run_state, report = controller.run(root, "use knowledge", external_context=(knowledge,))

    assert run_state.state.value == "COMPLETED"
    assert "retrieved external knowledge" in provider.requests[0].messages[0].content
    assert "Identifier" in provider.requests[0].messages[0].content
    assert report.evidence_refs
    trace_path = storage.paths_for(run_state.run_id).root / report.evidence_refs[0]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["retrieved_item_ids"]
    assert trace["selected_item_ids"] == trace["context_item_ids"]


def test_provider_receives_yarn_concrete_knowledge(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "yarn-provider")
    provider = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    controller, _storage = _controller(root, provider, context_manager=ContextManager())
    knowledge = _retrieval("Registries")

    run_state, _report = controller.run(root, "use yarn", external_context=(knowledge,))

    assert run_state.state.value == "COMPLETED"
    content = provider.requests[0].messages[0].content
    assert "net.fabricmc:yarn" in content
    assert "Registries" in content or "registry" in content.casefold()


def test_trace_relates_retrieved_selected_and_context(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "trace")
    provider = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    manager = ContextManager()
    controller, _storage = _controller(root, provider, context_manager=manager)
    knowledge = _retrieval("Identifier")

    controller.run(root, "trace", external_context=(knowledge,))

    trace = manager.last_knowledge_traces[0]
    assert trace.retrieved_item_ids
    assert trace.selected_item_ids
    assert trace.context_item_ids == trace.selected_item_ids


def test_brain_disabled_keeps_previous_flow(tmp_path: Path) -> None:
    root = _runtime_project(tmp_path / "brain-off")
    provider = ScriptedProvider([AgentResponse(assistant_message="plan", tool_calls=())])
    controller, _storage = _controller(root, provider, context_manager=ContextManager())

    run_state, _report = controller.run(root, "no brain")

    assert run_state.state.value == "COMPLETED"
    assert "retrieved external knowledge" not in provider.requests[0].messages[0].content


def test_regression_l1_environment_still_detects_fixture() -> None:
    resolution = __import__("pd_agent.brain", fromlist=["KnowledgeEnvironmentResolver"]).KnowledgeEnvironmentResolver().resolve(L11_FIXTURE)

    assert resolution.status.value == "DETECTED"
    assert resolution.environment.minecraft_version == "1.21.11"
    assert resolution.environment.loader_version == "0.19.3"


def test_regression_l2_yarn_retrieval_still_works() -> None:
    knowledge = _retrieval("Identifier")

    assert knowledge.status == KnowledgeRetrievalStatus.SUCCESS
    assert knowledge.items
    assert knowledge.items[0].provenance.source_id == "net.fabricmc:yarn"
