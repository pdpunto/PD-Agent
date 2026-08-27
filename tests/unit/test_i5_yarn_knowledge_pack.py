from __future__ import annotations

import hashlib

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeType,
    KnowledgePackState,
    YarnKnowledgeSource,
)


TINY = (
    "tiny\t2\t0\tofficial\tintermediary\tnamed\n"
    "c\tExample\texample\tExample\n"
    "\tm\t()V\tmethod_1\tm_1\tmethodOne\n"
    "\tf\tI\tfield_1\tf_1\tfieldOne\n"
).encode()


TARGET = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
)


def _source() -> YarnKnowledgeSource:
    return YarnKnowledgeSource(artifact_bytes=TINY)


def test_yarn_legacy_resolution_and_service_integration() -> None:
    source = _source()
    need = KnowledgeNeed("yarn-need", KnowledgeType.SYMBOL, "Example", TARGET)
    legacy = source.resolve(need, offline=True)
    assert legacy.status == KnowledgeRetrievalStatus.SUCCESS
    result = KnowledgeService((source,)).resolve(need, offline=True)
    assert result.status == KnowledgeRetrievalStatus.SUCCESS
    assert result.source_results[0].source_id == "net.fabricmc:yarn"
    assert result.source_results[0].eligible is True
    assert result.items[0].provenance.source_kind == "yarn-mappings"


def test_yarn_materializes_deterministic_symbol_records_and_pack() -> None:
    first = _source().materialize_pack(TARGET)
    second = _source().materialize_pack(TARGET)
    assert first.manifest.state == KnowledgePackState.DRAFT
    assert first.manifest.pack_id == second.manifest.pack_id
    assert [record.identity() for record in first.records] == [record.identity() for record in second.records]
    assert all(record.kind == KnowledgeType.SYMBOL for record in first.records)
    assert all(record.version_sensitive for record in first.records)
    assert all(record.authority.value == "AUTHORITATIVE_ARTIFACT" for record in first.records)
    assert first.manifest.source_set[0]["checksum"] == hashlib.sha256(TINY).hexdigest()
    assert first.verify().valid


def test_yarn_pack_freeze_reopen_is_reproducible(tmp_path) -> None:
    pack = _source().materialize_pack(TARGET).transition_to(KnowledgePackState.VERIFIED).freeze()
    from pd_agent.brain import KnowledgePackStore

    path = KnowledgePackStore.write(pack, tmp_path / "yarn-pack")
    reopened = KnowledgePackStore.read(path)
    assert reopened.manifest.pack_id == pack.manifest.pack_id
    assert reopened.manifest.state == KnowledgePackState.FROZEN


@pytest.mark.parametrize(
    "environment,expected",
    [
        (KnowledgeEnvironment(minecraft_version="1.20.1", mappings_namespace="yarn", mappings_version="1.21.11+build.6"), CompatibilityStatus.INCOMPATIBLE),
        (KnowledgeEnvironment(minecraft_version="1.21.11"), CompatibilityStatus.UNKNOWN),
    ],
)
def test_yarn_incompatible_and_unknown_environments_are_not_servable(environment, expected) -> None:
    source = _source()
    assert source.compatibility(environment) == expected
    with pytest.raises(ValueError):
        source.materialize_records(environment)


def test_changed_artifact_changes_materialized_identity() -> None:
    changed = TINY.replace(b"Example", b"Changed")
    first = _source().materialize_pack(TARGET)
    second = YarnKnowledgeSource(artifact_bytes=changed).materialize_pack(TARGET)
    assert first.manifest.pack_id != second.manifest.pack_id
