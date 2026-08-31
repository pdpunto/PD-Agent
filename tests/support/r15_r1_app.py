"""Deterministic test composition for the v0.9 integrated browser gate."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import zipfile

from pd_agent.brain import (
    KnowledgeEnvironment,
    KnowledgePack,
    KnowledgePackManifest,
    KnowledgePackState,
    KnowledgePackStore,
    KnowledgePolicy,
    KnowledgeProvenance,
    KnowledgeRecord,
    KnowledgeService,
    KnowledgeType,
    SourceAuthority,
    FrozenKnowledgePackSource,
    compose_frozen_knowledge_pack,
)
from pd_agent.config import AppConfig
from pd_agent.context import ContextManager
from pd_agent.core import AgentResponse, BuildResult, ToolCall
from pd_agent.minecraft import (
    MinecraftEvidenceKind,
    MinecraftEvidenceReference,
    MinecraftObservationStatus,
    MinecraftObservationType,
    MinecraftTestStatus,
    ObservationResult,
)
from pd_agent.product import build_product_application
from pd_agent.reporting import RunStorage


ENVIRONMENT = KnowledgeEnvironment(
    minecraft_version="1.21.11", loader_version="0.19.3", loom_version="1.13.3",
    mappings_namespace="yarn", mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11", java_version="21",
)


def _pack(root: Path) -> Path:
    packs = []
    for source_id, source_kind, kind, query in (
        ("net.fabricmc:yarn", "yarn-mappings", KnowledgeType.SYMBOL, "net.minecraft.block.Block"),
        ("net.fabricmc.fabric-api:fabric-api", "fabric-api-artifact", KnowledgeType.API, "Registry.register"),
        ("fabric-docs:concept-pattern", "fabric-official-reference", KnowledgeType.CONCEPT, "craftable utility block recipe"),
    ):
        content = {"source": source_id, "qualified_name": query, "guidance": "preserve entrypoints and register Server Core"}
        checksum = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = KnowledgeRecord(
            record_id=f"{source_id}:r15-r1",
            kind=kind,
            content=content,
            environment=ENVIRONMENT,
            provenance=KnowledgeProvenance(
                source_id=source_id, source_kind=source_kind, locator=f"fixture://{source_id}",
                revision="r15-r1", checksum_algorithm="sha256", checksum=checksum,
                license_id_or_policy="REDISTRIBUTABLE",
            ),
            authority=SourceAuthority.AUTHORITATIVE_SOURCE,
            license_policy=KnowledgePolicy.REDISTRIBUTABLE,
            integrity={"algorithm": "sha256", "value": checksum},
            source_revision="r15-r1",
        )
        manifest = KnowledgePackManifest(
            environment=ENVIRONMENT,
            source_set=({"source_id": source_id, "source_kind": source_kind, "revision": "r15-r1"},),
            record_inventory=({"record_id": record.record_id, "record_identity": record.identity()},),
            license_policy=KnowledgePolicy.REDISTRIBUTABLE,
        )
        packs.append(KnowledgePack(manifest, (record,)).transition_to(KnowledgePackState.VERIFIED))
    result = compose_frozen_knowledge_pack(packs, environment=ENVIRONMENT)
    destination = root / "frozen-pack"
    if destination.exists():
        shutil.rmtree(destination)
    KnowledgePackStore.write(result, destination)
    return destination


class FakeProvider:
    """Provider seam: records provider-visible knowledge and emits safe tools."""

    def __init__(self) -> None:
        self.calls = 0
        self.context_seen = False

    def execute(self, request):  # noqa: ANN001
        self.calls += 1
        self.context_seen = self.context_seen or any("knowledge_item_id" in message.content for message in request.messages)
        if self.calls == 1:
            return AgentResponse(
                assistant_message="Plan: add Server Core resources using the injected knowledge.",
                tool_calls=(
                    ToolCall("source", "write_file", {"path": "src/main/java/com/example/examplemod/ExampleMod.java", "content": "// R15-R1 source mutation\n"}),
                    ToolCall("lang", "create_file", {"path": "src/main/resources/assets/examplemod/lang/en_us.json", "content": '{"block.examplemod.server_core":"Server Core"}\n'}),
                    ToolCall("recipe", "create_file", {"path": "src/main/resources/data/examplemod/recipe/server_core.json", "content": '{"type":"minecraft:crafting_shaped","pattern":["###"],"key":{"#":{"item":"minecraft:iron_ingot"}},"result":{"id":"examplemod:server_core"}}\n'}),
                ),
            )
        return AgentResponse(
            assistant_message="Repair applied with the same provider-visible knowledge context." if self.calls == 2 else "Complete.",
            tool_calls=(
                (ToolCall("repair", "write_file", {"path": "src/main/java/com/example/examplemod/ExampleMod.java", "content": f"// R15-R1 repair {self.calls}\n"}),)
                if self.calls == 2 else ()
            ),
        )


class FakeBuildRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, project_snapshot, run_state, limits):  # noqa: ANN001
        del limits
        self.calls += 1
        run_state.record_build_attempt()
        path = project_snapshot.project_root / "build" / "libs" / "examplemod.jar"
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as jar:
            jar.writestr("fabric.mod.json", '{"id":"examplemod","version":"1.0.0"}')
            jar.writestr("assets/examplemod/lang/en_us.json", "{}")
        result = BuildResult(
            attempt=self.calls, command_display="fake-build --offline", cwd=project_snapshot.project_root,
            started_at=datetime.now(timezone.utc), duration_seconds=0.001, exit_code=0,
            stdout_log="BUILD SUCCESSFUL\n", stderr_log="",
        )
        run_state.record_build_result(result)
        return result


class FakeMinecraftRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, spec, **kwargs):  # noqa: ANN001
        self.calls += 1
        status = MinecraftObservationStatus.FAIL if self.calls == 1 else MinecraftObservationStatus.PASS
        evidence = MinecraftEvidenceReference(kind=MinecraftEvidenceKind.OBSERVATION, ref=f"runtime/r15-r1-{self.calls}.json")
        return SimpleNamespace(
            status=MinecraftTestStatus.PASS,
            observations=(ObservationResult(
                observation_id="server-core-registry",
                observation_type=MinecraftObservationType.REGISTRY_ENTRY_PRESENT,
                status=status,
                expected={"present": True}, actual={"present": status is MinecraftObservationStatus.PASS},
                evidence_refs=(evidence,),
            ),),
            metadata={"target_mod_id": spec.target_mod_id},
        )


def make_application(root: Path):
    fixture = Path(__file__).resolve().parents[2] / "benchmarks" / "projects" / "v0_5_fabric_base"
    workspace = root / "workspace"
    for generated in (root / "product-data", root / "runs"):
        if generated.exists():
            shutil.rmtree(generated)
    shutil.copytree(fixture, workspace, ignore=shutil.ignore_patterns(".gradle", "build", "bin"), dirs_exist_ok=True)
    pack_path = _pack(root)
    storage = RunStorage(root / "runs")
    provider = FakeProvider()
    config = AppConfig(provider="openai", model="gpt-5.6-luna", runs_dir=root / "runs")
    application = build_product_application(
        config,
        storage=storage,
        provider_factory=lambda _config: provider,
        build_runner=FakeBuildRunner(),
        artifact_validator=None,
        context_manager=ContextManager(),
        product_data_root=root / "product-data",
        minecraft_runner_factory=lambda _root: FakeMinecraftRunner(),
        knowledge_pack_path=pack_path,
        knowledge_pack_id=None,
    )
    return application, workspace, provider, root


def create_test_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="pd-agent-r15-r1-", dir=tempfile.gettempdir()))
