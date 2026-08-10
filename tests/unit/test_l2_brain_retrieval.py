from __future__ import annotations

import hashlib
import io
import urllib.error
import zipfile
from pathlib import Path

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    FileKnowledgeCache,
    KnowledgeEnvironment,
    KnowledgeEnvironmentResolver,
    KnowledgeNeed,
    KnowledgeRetrievalStatus,
    KnowledgeType,
    MinecraftBrain,
    SourceAuthority,
    YarnKnowledgeSource,
)
from pd_agent.brain.yarn import YarnMappingsDocument


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


def _need(query: str, *, need_type: KnowledgeType = KnowledgeType.SYMBOL) -> KnowledgeNeed:
    return KnowledgeNeed(
        id="need-1",
        type=need_type,
        query=query,
        environment=_environment(),
    )


def test_yarn_source_supports_symbol_and_mapping() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())

    assert source.supports(_need("Identifier", need_type=KnowledgeType.SYMBOL))
    assert source.supports(_need("Identifier", need_type=KnowledgeType.MAPPING))


def test_yarn_source_rejects_unsupported_types() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    need = _need("Registry", need_type=KnowledgeType.BUILD)

    result = source.resolve(need)

    assert result.status == KnowledgeRetrievalStatus.UNSUPPORTED_NEED
    assert result.items == ()


def test_yarn_source_exposes_exact_coordinate_and_url() -> None:
    source = YarnKnowledgeSource()

    assert source.artifact_coordinate == "net.fabricmc:yarn:1.21.11+build.6:v2"
    assert source.artifact_url == (
        "https://maven.fabricmc.net/net/fabricmc/yarn/1.21.11+build.6/"
        "yarn-1.21.11+build.6-v2.jar"
    )


def test_tiny_parser_and_checksum_use_real_fixture() -> None:
    zip_bytes = _artifact_bytes()
    document = YarnMappingsDocument.from_bytes(
        zip_bytes,
        source_name="net.fabricmc:yarn",
        version="1.21.11+build.6",
    )

    assert document.records
    assert document.checksum == hashlib.sha256(zip_bytes).hexdigest()
    assert any(record.named.endswith("Identifier") for record in document.records)


def test_source_returns_knowledge_items_with_complete_provenance() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    result = source.resolve(_need("Identifier"))

    assert result.status == KnowledgeRetrievalStatus.SUCCESS
    assert result.items
    item = result.items[0]

    assert item.authority == SourceAuthority.AUTHORITATIVE_ARTIFACT
    assert item.provenance.source_id == "net.fabricmc:yarn"
    assert item.provenance.source_kind == "yarn-mappings"
    assert item.provenance.locator == source.artifact_url
    assert item.provenance.artifact_or_document_version == "1.21.11+build.6"
    assert item.provenance.checksum_algorithm == "sha256"
    assert item.provenance.checksum
    assert item.provenance.license_id_or_policy == "CC0-1.0"
    assert item.environment == _environment()


def test_exact_compatibility_pass_and_mismatch_fail() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())

    assert source.compatibility(_environment()) == CompatibilityStatus.COMPATIBLE
    assert source.compatibility(
        KnowledgeEnvironment(
            minecraft_version="1.20.1",
            mappings_namespace="yarn",
            mappings_version="1.21.11+build.6",
        )
    ) == CompatibilityStatus.INCOMPATIBLE
    assert source.compatibility(
        KnowledgeEnvironment(
            minecraft_version="1.21.11",
            mappings_namespace="intermediary",
            mappings_version="1.21.11+build.6",
        )
    ) == CompatibilityStatus.INCOMPATIBLE


def test_other_mappings_version_is_incompatible() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    env = KnowledgeEnvironment(
        minecraft_version="1.21.11",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.1",
    )

    assert source.compatibility(env) == CompatibilityStatus.INCOMPATIBLE


def test_other_minecraft_version_is_incompatible() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    env = KnowledgeEnvironment(
        minecraft_version="1.20.1",
        mappings_namespace="yarn",
        mappings_version="1.21.11+build.6",
    )

    assert source.compatibility(env) == CompatibilityStatus.INCOMPATIBLE


def test_source_queries_identifier_registries_and_block_lookup() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())

    identifier_result = source.resolve(_need("Identifier"))
    registries_result = source.resolve(_need("Registries", need_type=KnowledgeType.MAPPING))
    block_lookup_result = source.resolve(_need("block registry lookup"))

    assert identifier_result.items
    assert registries_result.items
    assert block_lookup_result.items
    assert "Identifier" in identifier_result.items[0].content["symbol"]["named"]
    assert "Registry" in registries_result.items[0].content["symbol"]["named"] or "Registries" in registries_result.items[0].content["symbol"]["doc"]
    assert "registry" in block_lookup_result.items[0].content["symbol"]["doc"].casefold()


def test_source_does_not_hardcode_acceptance_response() -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    identifier_items = source.resolve(_need("Identifier")).items
    registries_items = source.resolve(_need("Registries", need_type=KnowledgeType.MAPPING)).items

    assert identifier_items[0].id != registries_items[0].id
    assert identifier_items[0].content != registries_items[0].content


def test_cache_exact_hit_and_version_isolation(tmp_path: Path) -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    cache = FileKnowledgeCache(tmp_path / "brain-cache")
    brain = MinecraftBrain(source=source, cache=cache)

    need = _need("Identifier")
    first = brain.retrieve(need)
    second = brain.retrieve(need)

    assert first.status == KnowledgeRetrievalStatus.SUCCESS
    assert second.cache_hit is True
    assert second.items[0].id == first.items[0].id
    assert cache.get(
        source_id=source.source_id,
        artifact_version=source.artifact_version,
        checksum=source.artifact_checksum,
        need=need,
    ) is not None

    other_need = KnowledgeNeed(
        id="need-2",
        type=KnowledgeType.SYMBOL,
        query="Identifier",
        environment=KnowledgeEnvironment(
            minecraft_version="1.20.1",
            mappings_namespace="yarn",
            mappings_version="1.21.11+build.6",
        ),
    )
    assert cache.get(
        source_id=source.source_id,
        artifact_version=source.artifact_version,
        checksum=source.artifact_checksum,
        need=other_need,
    ) is None


def test_offline_hit_and_offline_miss(tmp_path: Path) -> None:
    source = YarnKnowledgeSource(artifact_bytes=_artifact_bytes())
    cache = FileKnowledgeCache(tmp_path / "brain-cache")
    brain = MinecraftBrain(source=source, cache=cache)
    need = _need("Identifier")

    online = brain.retrieve(need)
    offline_hit = brain.retrieve(need, offline=True)

    assert online.status == KnowledgeRetrievalStatus.SUCCESS
    assert offline_hit.status == KnowledgeRetrievalStatus.SUCCESS
    assert offline_hit.cache_hit is True
    assert offline_hit.offline is True


def test_offline_miss_explicit_and_no_http(monkeypatch) -> None:
    source = YarnKnowledgeSource()
    called = {"value": False}

    def boom(*args, **kwargs):
        called["value"] = True
        raise AssertionError("network should not be touched in offline mode")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    result = source.resolve(_need("Identifier"), offline=True)

    assert result.status == KnowledgeRetrievalStatus.OFFLINE_MISS
    assert called["value"] is False


def test_network_failure_is_explicit(monkeypatch) -> None:
    source = YarnKnowledgeSource()

    def fail(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", fail)

    result = source.resolve(_need("Identifier"), offline=False)

    assert result.status == KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE


def test_live_fixture_regression_l1(tmp_path: Path) -> None:
    resolution = KnowledgeEnvironmentResolver().resolve(L11_FIXTURE)

    assert resolution.status.name == "DETECTED"
    assert resolution.environment.minecraft_version == "1.21.11"
    assert resolution.environment.loader_version == "0.19.3"
    assert resolution.environment.loom_version == "1.13.3"
    assert resolution.environment.mappings_namespace == "yarn"
    assert resolution.environment.mappings_version == "1.21.11+build.6"
