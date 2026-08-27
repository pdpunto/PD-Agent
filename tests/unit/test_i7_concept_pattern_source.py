from __future__ import annotations

import io
import zipfile

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    FabricApiKnowledgeSource,
    FabricConceptPatternKnowledgeSource,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgePackState,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeType,
    KnowledgePackStore,
    YarnKnowledgeSource,
)


TARGET = KnowledgeEnvironment(
    minecraft_version="1.21.11", loader_version="0.19.3",
    mappings_namespace="yarn", mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
)


def _fabric_artifact() -> bytes:
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as jar:
        jar.writestr("net/fabricmc/fabric/api/registry/v1/Registry.class", b"class")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as jar:
        jar.writestr("META-INF/jars/fabric-api-base.jar", nested.getvalue())
    return outer.getvalue()


def _yarn() -> YarnKnowledgeSource:
    tiny = "tiny\t2\t0\tofficial\tintermediary\tnamed\nc\tamo\tnet/minecraft/class_1\tIdentifier\n"
    return YarnKnowledgeSource(artifact_bytes=tiny.encode())


def test_curated_source_has_pinned_revision_and_deterministic_records() -> None:
    first = FabricConceptPatternKnowledgeSource()
    second = FabricConceptPatternKnowledgeSource()
    records = first.materialize_records(TARGET)
    assert first.artifact_version == "1.21.11-curated-1"
    assert first.artifact_checksum == second.artifact_checksum
    assert {record.kind for record in records} == {KnowledgeType.CONCEPT, KnowledgeType.PATTERN}
    assert {record.content["capability"] for record in records} == {
        "registries", "blocks", "data_components", "block_entities", "inventories",
        "persistence", "commands", "events", "tags", "recipes", "loot",
    }
    assert all(record.authority.value == "OFFICIAL_DOCUMENTATION" for record in records)
    assert all(record.provenance.revision == first.artifact_version for record in records)
    assert [record.identity() for record in records] == [record.identity() for record in second.materialize_records(TARGET)]


def test_curated_pack_freezes_reopens_and_preserves_relations(tmp_path) -> None:
    source = FabricConceptPatternKnowledgeSource()
    pack = source.materialize_pack(TARGET)
    assert pack.verify().valid
    assert pack.records[0].content["related_api"]
    frozen = pack.transition_to(KnowledgePackState.VERIFIED).freeze()
    reopened = KnowledgePackStore.read(KnowledgePackStore.write(frozen, tmp_path / "concepts"))
    assert reopened.manifest.pack_id == frozen.manifest.pack_id


def test_compatibility_unknown_and_incompatible_are_fail_closed() -> None:
    source = FabricConceptPatternKnowledgeSource()
    unknown = KnowledgeEnvironment(minecraft_version="1.21.11")
    incompatible = KnowledgeEnvironment(
        minecraft_version="1.20.1", loader_version="0.19.3", mappings_namespace="yarn",
        mappings_version="1.21.11+build.6", fabric_api_version="0.141.6+1.21.11",
    )
    assert source.compatibility(unknown) == CompatibilityStatus.UNKNOWN
    assert source.compatibility(incompatible) == CompatibilityStatus.INCOMPATIBLE
    with pytest.raises(ValueError):
        source.materialize_records(unknown)


def test_three_source_service_preserves_order_and_provenance() -> None:
    sources = (_yarn(), FabricApiKnowledgeSource(artifact_bytes=_fabric_artifact()), FabricConceptPatternKnowledgeSource())
    need = KnowledgeNeed("concept", KnowledgeType.CONCEPT, "registry item", TARGET)
    result = KnowledgeService(sources).resolve(need, offline=True)
    assert result.status == KnowledgeRetrievalStatus.SUCCESS
    assert [item.source_id for item in result.source_results] == [
        "fabric-docs:concept-pattern", "net.fabricmc.fabric-api:fabric-api", "net.fabricmc:yarn"
    ]
    assert result.source_results[0].items[0].provenance.source_id == "fabric-docs:concept-pattern"
    assert result.source_results[1].status == KnowledgeRetrievalStatus.UNSUPPORTED_NEED
    assert result.source_results[2].status == KnowledgeRetrievalStatus.UNSUPPORTED_NEED


def test_no_answer_key_or_harness_leakage_and_partial_failure() -> None:
    source = FabricConceptPatternKnowledgeSource()
    result = source.resolve(KnowledgeNeed("need", KnowledgeType.PATTERN, "loot", TARGET), offline=True)
    text = str(result.items[0].content).casefold()
    assert "answer key" not in text
    assert "harness" not in text
    assert "expected fixture" not in text
