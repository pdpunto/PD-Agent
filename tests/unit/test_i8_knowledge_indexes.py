from __future__ import annotations

import io
import sqlite3
import zipfile
from dataclasses import replace

import pytest

from pd_agent.brain import (
    FabricApiKnowledgeSource,
    FabricConceptPatternKnowledgeSource,
    KnowledgeEnvironment,
    KnowledgeIndexError,
    KnowledgePackIndex,
    KnowledgePackState,
    KnowledgeService,
    KnowledgeType,
    YarnKnowledgeSource,
    CuratedConcept,
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


def _pack():
    return FabricConceptPatternKnowledgeSource().materialize_pack(TARGET).transition_to(KnowledgePackState.VERIFIED).freeze()


def test_fts5_available_and_frozen_pack_builds_structured_and_lexical_index(tmp_path) -> None:
    assert KnowledgePackIndex.fts5_available()
    pack = _pack()
    index = KnowledgePackIndex.build(pack, tmp_path / "index.sqlite")
    assert index.metadata.schema_version == "i8-1"
    assert index.metadata.pack_identity == pack.manifest.pack_id
    assert index.lookup_by_type(KnowledgeType.PATTERN)
    assert index.lookup_by_capability("registries")
    assert index.lexical_search("registry")
    record = pack.records[0]
    assert index.lookup_record(record.record_id) == record
    index.close()


def test_index_rebuild_delete_and_pack_identity_are_stable(tmp_path) -> None:
    pack = _pack()
    path = tmp_path / "index.sqlite"
    first = KnowledgePackIndex.build(pack, path)
    first_ids = [record.record_id for record in first.lexical_search("registry")]
    first.delete()
    assert not path.exists()
    second = KnowledgePackIndex.build(pack, path)
    assert [record.record_id for record in second.lexical_search("registry")] == first_ids
    assert second.pack.manifest.pack_id == pack.manifest.pack_id
    second.close()


def test_stale_corrupt_missing_and_partial_indexes_fail_closed(tmp_path) -> None:
    pack = _pack()
    source = FabricConceptPatternKnowledgeSource()
    changed_catalog = (replace(source.catalog[0], summary="different"),) + source.catalog[1:]
    stale = FabricConceptPatternKnowledgeSource(catalog=changed_catalog).materialize_pack(TARGET).transition_to(KnowledgePackState.VERIFIED).freeze()
    path = tmp_path / "index.sqlite"
    KnowledgePackIndex.build(pack, path).close()
    with pytest.raises(KnowledgeIndexError, match="pack identity"):
        KnowledgePackIndex.open(stale, path)
    path.write_bytes(b"not sqlite")
    with pytest.raises(KnowledgeIndexError):
        KnowledgePackIndex.open(pack, path)
    path.unlink()
    with pytest.raises(KnowledgeIndexError, match="missing"):
        KnowledgePackIndex.open(pack, path)

    partial = tmp_path / "partial.sqlite"
    connection = sqlite3.connect(partial)
    connection.execute("CREATE TABLE index_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.commit()
    connection.close()
    with pytest.raises(KnowledgeIndexError):
        KnowledgePackIndex.open(pack, partial)


def test_draft_pack_is_not_indexable_and_malformed_fts_is_safe(tmp_path) -> None:
    draft = FabricConceptPatternKnowledgeSource().materialize_pack(TARGET)
    with pytest.raises(KnowledgeIndexError):
        KnowledgePackIndex.build(draft, tmp_path / "draft.sqlite")
    index = KnowledgePackIndex.build(_pack(), tmp_path / "safe.sqlite")
    assert index.lexical_search('" OR DROP TABLE records; --') == ()
    assert index.lexical_search("") == ()
    assert index.lexical_search("registry", 0) == ()
    index.close()


def test_three_source_canonical_packs_can_be_indexed_without_identity_changes(tmp_path) -> None:
    yarn_text = "tiny\t2\t0\tofficial\tintermediary\tnamed\nc\tamo\tnet/minecraft/class_1\tIdentifier\n"
    yarn_pack = YarnKnowledgeSource(artifact_bytes=yarn_text.encode()).materialize_pack(TARGET)
    fabric_pack = FabricApiKnowledgeSource(artifact_bytes=_fabric_artifact()).materialize_pack(TARGET)
    concept_pack = FabricConceptPatternKnowledgeSource().materialize_pack(TARGET)
    for name, pack in (("yarn", yarn_pack), ("fabric", fabric_pack), ("concept", concept_pack)):
        frozen = pack.transition_to(KnowledgePackState.VERIFIED).freeze()
        index = KnowledgePackIndex.build(frozen, tmp_path / f"{name}.sqlite")
        assert index.metadata.pack_identity == frozen.manifest.pack_id
        assert index.verify()
        index.close()
    assert KnowledgeService
