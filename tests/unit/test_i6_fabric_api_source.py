from __future__ import annotations

import io
import zipfile

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    FabricApiKnowledgeSource,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgePackState,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeType,
    YarnKnowledgeSource,
)


ENVIRONMENT = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
)


def _artifact(*entries: str) -> bytes:
    nested_buffer = io.BytesIO()
    with zipfile.ZipFile(nested_buffer, "w", zipfile.ZIP_DEFLATED) as nested:
        for entry in entries:
            nested.writestr(entry, b"class bytes")
    outer_buffer = io.BytesIO()
    with zipfile.ZipFile(outer_buffer, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr("META-INF/jars/fabric-api-base.jar", nested_buffer.getvalue())
        outer.writestr("fabric.mod.json", b"{}")
    return outer_buffer.getvalue()


def _source(*entries: str) -> FabricApiKnowledgeSource:
    return FabricApiKnowledgeSource(artifact_bytes=_artifact(*entries))


def test_fabric_api_materializes_public_api_records_deterministically() -> None:
    artifact = _artifact(
        "net/fabricmc/fabric/api/registry/v1/Registry.java.class",
        "net/fabricmc/fabric/api/item/v1/ItemApi.class",
        "net/fabricmc/fabric/api/impl/Hidden.class",
        "net/fabricmc/fabric/api/client/ClientOnly.class",
        "com/example/Other.class",
    )
    source = FabricApiKnowledgeSource(artifact_bytes=artifact)
    records = source.materialize_records(ENVIRONMENT)
    assert len(records) == 2
    assert all(record.kind == KnowledgeType.API for record in records)
    assert all(record.content["public_api"] is True for record in records)
    assert all(record.version_sensitive for record in records)
    assert source.materialize_pack(ENVIRONMENT).verify().valid
    assert [record.identity() for record in records] == [record.identity() for record in source.materialize_records(ENVIRONMENT)]


def test_fabric_api_identity_and_checksum_are_persisted() -> None:
    artifact = _artifact("net/fabricmc/fabric/api/registry/v1/Registry.class")
    source = FabricApiKnowledgeSource(artifact_bytes=artifact)
    pack = source.materialize_pack(ENVIRONMENT)
    assert source.artifact_checksum
    assert pack.manifest.source_set[0]["checksum"] == source.artifact_checksum
    assert pack.manifest.source_set[0]["coordinate"] == "net.fabricmc.fabric-api:fabric-api:0.141.6+1.21.11"
    assert pack.manifest.source_set[0]["license_policy"] == "FETCH_CACHE_REFERENCE_ONLY"


def test_fabric_api_compatibility_is_fail_closed() -> None:
    source = _source("net/fabricmc/fabric/api/Registry.class")
    incompatible = KnowledgeEnvironment(minecraft_version="1.20.1", loader_version="0.19.3", fabric_api_version=source.version)
    unknown = KnowledgeEnvironment(minecraft_version="1.21.11")
    assert source.compatibility(incompatible) == CompatibilityStatus.INCOMPATIBLE
    assert source.compatibility(unknown) == CompatibilityStatus.UNKNOWN
    with pytest.raises(ValueError):
        source.materialize_records(incompatible)


def test_fabric_api_corruption_and_checksum_mismatch_fail_closed() -> None:
    with pytest.raises(ValueError):
        FabricApiKnowledgeSource(artifact_bytes=b"not a zip").materialize_records(ENVIRONMENT)
    source = FabricApiKnowledgeSource(artifact_bytes=_artifact("net/fabricmc/fabric/api/Registry.class"), artifact_checksum="0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        source.materialize_records(ENVIRONMENT)


def test_yarn_and_fabric_api_coexist_in_ordered_service() -> None:
    yarn_text = "tiny\t2\t0\tofficial\tintermediary\tnamed\nc\tamo\tnet/minecraft/class_1\tIdentifier\n"
    yarn = YarnKnowledgeSource(artifact_bytes=yarn_text.encode())
    fabric = _source("net/fabricmc/fabric/api/registry/v1/Registry.class")
    need = KnowledgeNeed("need", KnowledgeType.SYMBOL, "Identifier", ENVIRONMENT)
    result = KnowledgeService((fabric, yarn)).resolve(need, offline=True)
    assert [item.source_id for item in result.source_results] == ["net.fabricmc.fabric-api:fabric-api", "net.fabricmc:yarn"]
    assert result.status == KnowledgeRetrievalStatus.SUCCESS
    assert result.source_results[1].provenance[0].source_id == "net.fabricmc:yarn"


def test_fabric_api_pack_freeze_and_reopen(tmp_path) -> None:
    from pd_agent.brain import KnowledgePackStore

    pack = _source("net/fabricmc/fabric/api/registry/v1/Registry.class").materialize_pack(ENVIRONMENT)
    frozen = pack.transition_to(KnowledgePackState.VERIFIED).freeze()
    reopened = KnowledgePackStore.read(KnowledgePackStore.write(frozen, tmp_path / "fabric"))
    assert reopened.manifest.pack_id == frozen.manifest.pack_id
