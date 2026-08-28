from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

import pytest

from pd_agent.brain import (
    KnowledgeEnvironment,
    KnowledgePackManifest,
    KnowledgePackState,
    KnowledgePolicy,
    KnowledgeProvenance,
    KnowledgeRecord,
    KnowledgeType,
    SourceAuthority,
    normalize_logical_path,
)


ENVIRONMENT = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    loom_version="1.13.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)


def _provenance(
    locator: str = "file://knowledge.json",
    *,
    retrieved_at: datetime | None = None,
) -> KnowledgeProvenance:
    return KnowledgeProvenance(
        source_id="test-source",
        source_kind="fixture",
        locator=locator,
        artifact_or_document_version="1.0",
        revision="rev-1",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        license_id_or_policy="REDISTRIBUTABLE",
        retrieved_at=retrieved_at,
    )


def _record(kind: KnowledgeType = KnowledgeType.SYMBOL, *, content: object = None, **kwargs) -> KnowledgeRecord:
    return KnowledgeRecord(
        record_id=f"record-{kind.value.lower()}",
        kind=kind,
        content=content if content is not None else {"symbol": "Example", "entries": ["a", "b"]},
        environment=ENVIRONMENT,
        provenance=_provenance(),
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
        **kwargs,
    )


def test_all_normative_knowledge_record_kinds_round_trip() -> None:
    kinds = (
        KnowledgeType.SYMBOL,
        KnowledgeType.API,
        KnowledgeType.CONCEPT,
        KnowledgeType.PATTERN,
        KnowledgeType.EXAMPLE,
        KnowledgeType.VERSION_CHANGE,
        KnowledgeType.CAPABILITY,
        KnowledgeType.DIAGNOSTIC,
    )

    records = [_record(kind) for kind in kinds]

    assert [KnowledgeRecord.from_dict(item.to_dict()).kind for item in records] == list(kinds)


def test_record_identity_is_deterministic_and_excludes_mutable_locator() -> None:
    first = _record()
    second = KnowledgeRecord.from_dict(
        {**first.to_dict(), "provenance": {**first.to_dict()["provenance"], "locator": "https://new"}}
    )

    assert first.identity() == second.identity()
    assert first.to_dict()["record_identity"] == first.identity()


def test_record_identity_excludes_retrieved_at_but_preserves_observable_provenance() -> None:
    first = _record()
    second = KnowledgeRecord(
        record_id=first.record_id,
        kind=first.kind,
        content=first.content,
        environment=first.environment,
        provenance=_provenance(retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        authority=first.authority,
    )

    assert first.identity() == second.identity()
    assert second.to_dict()["provenance"]["retrieved_at"] == "2026-01-01T00:00:00+00:00"


def test_record_identity_changes_for_semantic_content_change() -> None:
    first = _record()
    changed = KnowledgeRecord(
        record_id=first.record_id,
        kind=first.kind,
        content={"symbol": "Different"},
        environment=first.environment,
        provenance=_provenance(retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        authority=first.authority,
    )

    assert first.identity() != changed.identity()


def test_pack_identity_ignores_retrieved_at_only_changes() -> None:
    first_record = KnowledgeRecord(
        record_id="stable-record",
        kind=KnowledgeType.SYMBOL,
        content={"symbol": "Example"},
        environment=ENVIRONMENT,
        provenance=_provenance(retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
    )
    second_record = KnowledgeRecord(
        record_id=first_record.record_id,
        kind=first_record.kind,
        content=first_record.content,
        environment=first_record.environment,
        provenance=_provenance(
            locator="https://other.example/knowledge.json",
            retrieved_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
        authority=first_record.authority,
    )
    first_inventory = ({"record_id": first_record.record_id, "record_identity": first_record.identity()},)
    second_inventory = ({"record_id": second_record.record_id, "record_identity": second_record.identity()},)
    first_manifest = KnowledgePackManifest(ENVIRONMENT, ({"source_id": "test"},), first_inventory)
    second_manifest = KnowledgePackManifest(ENVIRONMENT, ({"source_id": "test"},), second_inventory)

    assert first_record.to_dict()["provenance"]["retrieved_at"] != second_record.to_dict()["provenance"]["retrieved_at"]
    assert first_manifest.pack_id == second_manifest.pack_id


def test_record_identity_changes_when_content_changes() -> None:
    first = _record()
    changed = _record()
    changed = KnowledgeRecord(
        record_id=changed.record_id,
        kind=changed.kind,
        content={"symbol": "Other"},
        environment=changed.environment,
        provenance=changed.provenance,
        authority=changed.authority,
    )

    assert first.identity() != changed.identity()


def test_record_field_order_does_not_change_identity() -> None:
    record = _record(relations=({"kind": "uses", "target": "b"}, {"target": "a", "kind": "uses"}))
    data = OrderedDict(reversed(list(record.to_dict().items())))

    assert KnowledgeRecord.from_dict(data).identity() == record.identity()


def test_record_rejects_legacy_or_unknown_kind_and_non_json_content() -> None:
    with pytest.raises(ValueError):
        _record(KnowledgeType.MAPPING)
    with pytest.raises(ValueError):
        KnowledgeRecord.from_dict({**_record().to_dict(), "kind": "NOPE"})
    with pytest.raises(TypeError):
        _record(content=object())


def test_record_metadata_round_trip_including_policy_and_environment() -> None:
    record = _record(
        version_sensitive=False,
        capability="registries",
        related_symbols=("B", "A"),
        license_policy=KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY,
        source_revision="source-rev",
        integrity={"algorithm": "sha256", "value": "b" * 64},
    )

    restored = KnowledgeRecord.from_dict(record.to_dict())

    assert restored.identity() == record.identity()
    assert restored.related_symbols == ("A", "B")
    assert restored.environment == ENVIRONMENT
    assert restored.license_policy == KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY


def test_pack_identity_ignores_derived_and_generated_metadata() -> None:
    records = (_record(), _record(KnowledgeType.API))
    inventory = tuple({"record_id": item.record_id, "record_identity": item.identity()} for item in records)
    pack = KnowledgePackManifest(
        environment=ENVIRONMENT,
        source_set=({"source_id": "b", "revision": "2"}, {"source_id": "a", "revision": "1"}),
        record_inventory=inventory,
        generated_metadata={"created_at": "now"},
        derived_index_metadata={"path": "index.sqlite", "sha256": "different"},
    )
    changed = KnowledgePackManifest.from_dict(
        {**pack.to_dict(), "generated_metadata": {"created_at": "later"}, "derived_index_metadata": {"path": "other"}}
    )

    assert changed.pack_id == pack.pack_id
    assert changed.identity() == pack.identity()
    assert pack.state == KnowledgePackState.DRAFT


def test_pack_identity_is_order_independent_and_round_trips() -> None:
    record = _record()
    inventory = (("record_id", record.record_id), ("record_identity", record.identity()))
    first = KnowledgePackManifest(
        environment=ENVIRONMENT,
        source_set=({"source_id": "z"}, {"source_id": "a"}),
        record_inventory=(dict(inventory),),
    )
    second = KnowledgePackManifest.from_dict(
        {
            **first.to_dict(),
            "source_set": [{"source_id": "a"}, {"source_id": "z"}],
            "record_inventory": [{"record_identity": record.identity(), "record_id": record.record_id}],
        }
    )

    assert second.pack_id == first.pack_id
    assert second.source_set == ({"source_id": "a"}, {"source_id": "z"})
    restored = KnowledgePackManifest.from_dict(first.to_dict())
    assert restored.pack_id == first.pack_id
    assert restored.identity() == first.identity()


def test_pack_rejects_invalid_state_or_identity() -> None:
    pack = KnowledgePackManifest(environment=ENVIRONMENT, source_set=(), record_inventory=())

    with pytest.raises(ValueError):
        KnowledgePackManifest.from_dict({**pack.to_dict(), "state": "BROKEN"})
    with pytest.raises(ValueError):
        KnowledgePackManifest.from_dict({**pack.to_dict(), "pack_id": "0" * 64})


def test_windows_logical_paths_are_normalized_without_changing_urls() -> None:
    assert normalize_logical_path("records\\a.json") == "records/a.json"
    assert normalize_logical_path("https://example.test/a\\b") == "https://example.test/a\\b"
