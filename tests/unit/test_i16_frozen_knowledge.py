from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pd_agent.benchmark import BenchmarkConfig
from pd_agent.brain import (
    EXPECTED_FROZEN_SOURCE_IDS,
    FabricConceptPatternKnowledgeSource,
    FrozenKnowledgePackSource,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgePack,
    KnowledgePackIndex,
    KnowledgePackIntegrityError,
    KnowledgePackManifest,
    KnowledgePackState,
    KnowledgePackStore,
    KnowledgePolicy,
    KnowledgeProvenance,
    KnowledgeRecord,
    KnowledgeService,
    KnowledgeType,
    SourceAuthority,
    compose_frozen_knowledge_pack,
    materialize_frozen_knowledge_pack,
)
from pd_agent.core import ExecutionLimits


ENVIRONMENT = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    loom_version="1.13.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)


def _source_pack(source_id: str, source_kind: str, kind: KnowledgeType, query: str, *, verified: bool = True) -> KnowledgePack:
    content = {"source": source_id, "qualified_name": query, "capability": query}
    checksum = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    provenance = KnowledgeProvenance(
        source_id=source_id,
        source_kind=source_kind,
        locator=f"fixture://{source_id}",
        revision="fixture-1",
        checksum_algorithm="sha256",
        checksum=checksum,
        license_id_or_policy="REDISTRIBUTABLE",
    )
    record = KnowledgeRecord(
        record_id=f"{source_id}:record",
        kind=kind,
        content=content,
        environment=ENVIRONMENT,
        provenance=provenance,
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
        license_policy=KnowledgePolicy.REDISTRIBUTABLE,
        integrity={"algorithm": "sha256", "value": checksum},
        source_revision="fixture-1",
    )
    inventory = ({"record_id": record.record_id, "record_identity": record.identity()},)
    manifest = KnowledgePackManifest(
        environment=ENVIRONMENT,
        source_set=({"source_id": source_id, "source_kind": source_kind, "revision": "fixture-1"},),
        record_inventory=inventory,
        license_policy=KnowledgePolicy.REDISTRIBUTABLE,
    )
    pack = KnowledgePack(manifest, (record,))
    return pack.transition_to(KnowledgePackState.VERIFIED) if verified else pack


def _packs() -> tuple[KnowledgePack, ...]:
    return (
        _source_pack("net.fabricmc:yarn", "yarn-mappings", KnowledgeType.SYMBOL, "net.minecraft.item.Item"),
        _source_pack("net.fabricmc.fabric-api:fabric-api", "fabric-api-artifact", KnowledgeType.API, "FabricItemGroupEntries"),
        _source_pack("fabric-docs:concept-pattern", "fabric-official-reference", KnowledgeType.CONCEPT, "data_components"),
    )


def _need(kind: KnowledgeType, query: str) -> KnowledgeNeed:
    return KnowledgeNeed(f"need-{kind.value}", kind, query, ENVIRONMENT)


def _load_runner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "benchmark" / "run_v0_4.py"
    spec = importlib.util.spec_from_file_location("i16_test_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _config(*, brain_enabled: bool, knowledge_config: dict[str, object]) -> BenchmarkConfig:
    return BenchmarkConfig(
        config_id=f"i16-{'on' if brain_enabled else 'off'}",
        provider="openai",
        model="gpt-test",
        brain_enabled=brain_enabled,
        model_config={},
        provider_config={},
        execution_limits=ExecutionLimits(max_agent_steps=25, max_tool_calls=50),
        knowledge_config=knowledge_config,
        target_repetition_count=1,
    )


def test_composite_pack_is_deterministic_and_reopens_with_same_identity(tmp_path: Path) -> None:
    first = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    second = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    assert first.manifest.state == KnowledgePackState.FROZEN
    assert first.manifest.pack_id == second.manifest.pack_id
    assert {item["source_id"] for item in first.manifest.source_set} == EXPECTED_FROZEN_SOURCE_IDS

    destination = tmp_path / "frozen-pack"
    KnowledgePackStore.write(first, destination)
    reopened = KnowledgePackStore.read(destination)
    assert reopened.manifest.pack_id == first.manifest.pack_id
    assert reopened.manifest.state == KnowledgePackState.FROZEN


def test_frozen_source_retrieves_all_families_and_index_is_identity_bound(tmp_path: Path) -> None:
    pack = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    source = FrozenKnowledgePackSource(pack)
    service = KnowledgeService((source,))
    for kind, query in (
        (KnowledgeType.MAPPING, "net.minecraft.item.Item"),
        (KnowledgeType.API, "FabricItemGroupEntries"),
        (KnowledgeType.CONCEPT, "data_components"),
    ):
        result = service.resolve(_need(kind, query), offline=True)
        assert result.status.value == "SUCCESS"
        assert result.items
        assert result.items[0].metadata["pack_id"] == pack.manifest.pack_id

    index = KnowledgePackIndex.build(pack, tmp_path / "knowledge.sqlite")
    try:
        assert index.metadata.pack_identity == pack.manifest.pack_id
        assert index.verify()
        index.close()
    finally:
        if index.path.exists():
            index.path.unlink()
    rebuilt = KnowledgePackIndex.build(pack, tmp_path / "knowledge.sqlite")
    assert rebuilt.metadata.pack_identity == pack.manifest.pack_id
    rebuilt.close()


def test_corrupt_or_wrong_identity_pack_is_rejected(tmp_path: Path) -> None:
    pack = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    destination = tmp_path / "frozen-pack"
    KnowledgePackStore.write(pack, destination)
    manifest = destination / "manifest.json"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(pack.manifest.pack_id, "0" * 64), encoding="utf-8")
    with pytest.raises(KnowledgePackIntegrityError):
        KnowledgePackStore.read(destination)


def test_draft_source_pack_is_rejected_but_materializer_finalizes_each_source() -> None:
    drafts = tuple(
        _source_pack(source_id, source_kind, kind, query, verified=False)
        for source_id, source_kind, kind, query in (
            ("net.fabricmc:yarn", "yarn-mappings", KnowledgeType.SYMBOL, "net.minecraft.item.Item"),
            ("net.fabricmc.fabric-api:fabric-api", "fabric-api-artifact", KnowledgeType.API, "FabricItemGroupEntries"),
            ("fabric-docs:concept-pattern", "fabric-official-reference", KnowledgeType.CONCEPT, "data_components"),
        )
    )
    with pytest.raises(ValueError, match="verified or frozen"):
        compose_frozen_knowledge_pack(drafts, environment=ENVIRONMENT)

    class Source:
        def __init__(self, pack: KnowledgePack) -> None:
            self.pack = pack

        def materialize_pack(self, environment: KnowledgeEnvironment) -> KnowledgePack:
            assert environment == ENVIRONMENT
            return self.pack

    finalized = materialize_frozen_knowledge_pack(
        tuple(Source(pack) for pack in drafts), environment=ENVIRONMENT
    )
    assert finalized.manifest.state == KnowledgePackState.FROZEN


def test_launcher_rejects_wrong_expected_pack_identity(tmp_path: Path) -> None:
    runner = _load_runner()
    pack = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    pack_root = tmp_path / "pack"
    KnowledgePackStore.write(pack, pack_root)
    config = _config(brain_enabled=True, knowledge_config={"frozen_pack_required": True, "frozen_pack_id": "0" * 64})
    with pytest.raises(ValueError, match="identity mismatch"):
        runner._build_knowledge_source((config,), frozen_pack_path=pack_root)


def test_launcher_frozen_mode_is_fail_closed_and_brain_off_has_no_source(tmp_path: Path) -> None:
    runner = _load_runner()
    on = _config(brain_enabled=True, knowledge_config={"frozen_pack_required": True})
    with pytest.raises(ValueError, match="frozen knowledge pack is required"):
        runner._build_knowledge_source((on,))

    pack = compose_frozen_knowledge_pack(_packs(), environment=ENVIRONMENT)
    pack_root = tmp_path / "pack"
    KnowledgePackStore.write(pack, pack_root)
    source = runner._build_knowledge_source(
        (_config(brain_enabled=True, knowledge_config={"frozen_pack_required": True, "frozen_pack_id": pack.manifest.pack_id}),),
        frozen_pack_path=pack_root,
    )
    assert isinstance(source, FrozenKnowledgePackSource)
    off = _config(brain_enabled=False, knowledge_config={})
    assert runner._build_knowledge_source((off,)) is None


def test_legacy_concept_source_remains_available_outside_frozen_mode() -> None:
    source = FabricConceptPatternKnowledgeSource()
    assert source.source_id == "fabric-docs:concept-pattern"
