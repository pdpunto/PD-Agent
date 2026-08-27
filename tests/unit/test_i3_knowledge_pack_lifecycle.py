from __future__ import annotations

import hashlib

import pytest

from pd_agent.brain import (
    KnowledgeEnvironment,
    KnowledgePack,
    KnowledgePackIntegrityError,
    KnowledgePackManifest,
    KnowledgePackState,
    KnowledgePackStore,
    KnowledgePolicy,
    KnowledgeProvenance,
    KnowledgeRecord,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.brain.canonical import canonical_json


ENVIRONMENT = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


def _record(record_id: str = "records/symbol") -> KnowledgeRecord:
    content = {"name": "Example", "value": 1}
    checksum = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    return KnowledgeRecord(
        record_id=record_id,
        kind=KnowledgeType.SYMBOL,
        content=content,
        environment=ENVIRONMENT,
        provenance=KnowledgeProvenance(
            source_id="fixture",
            source_kind="fixture",
            locator="fixture://i3",
            revision="r1",
            checksum_algorithm="sha256",
            checksum=checksum,
            license_id_or_policy="REDISTRIBUTABLE",
        ),
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
        license_policy=KnowledgePolicy.REDISTRIBUTABLE,
        integrity={"algorithm": "sha256", "value": checksum},
    )


def _pack(records: tuple[KnowledgeRecord, ...] | None = None) -> KnowledgePack:
    records = records or (_record(),)
    inventory = tuple({"record_id": item.record_id, "record_identity": item.identity()} for item in records)
    return KnowledgePack(
        KnowledgePackManifest(environment=ENVIRONMENT, source_set=({"source_id": "fixture"},), record_inventory=inventory),
        records,
    )


def test_lifecycle_validates_and_freezes_without_mutating_identity() -> None:
    draft = _pack()
    assert draft.verify().valid
    assert not draft.can_serve
    verified = draft.transition_to(KnowledgePackState.VERIFIED)
    frozen = verified.freeze()

    assert verified.can_serve
    assert frozen.can_serve
    assert frozen.manifest.pack_id == draft.manifest.pack_id
    assert frozen.supersede().manifest.state == KnowledgePackState.SUPERSEDED


def test_invalid_transitions_fail_closed() -> None:
    pack = _pack()
    with pytest.raises(KnowledgePackIntegrityError):
        pack.transition_to(KnowledgePackState.FROZEN)
    with pytest.raises(KnowledgePackIntegrityError):
        pack.transition_to(KnowledgePackState.SUPERSEDED)
    frozen = pack.transition_to(KnowledgePackState.VERIFIED).freeze()
    with pytest.raises(KnowledgePackIntegrityError):
        frozen.transition_to(KnowledgePackState.DRAFT)


def test_integrity_detects_checksum_missing_duplicate_and_environment_errors() -> None:
    record = _record()
    bad = KnowledgeRecord(
        record_id=record.record_id,
        kind=record.kind,
        content={"name": "changed"},
        environment=record.environment,
        provenance=record.provenance,
        authority=record.authority,
        license_policy=record.license_policy,
        integrity=record.integrity,
    )
    assert not _pack((bad,)).verify().valid
    assert not _pack((record, record)).verify().valid
    foreign = KnowledgeRecord(
        record_id="foreign",
        kind=record.kind,
        content=record.content,
        environment=KnowledgeEnvironment(minecraft_version="other"),
        provenance=record.provenance,
        authority=record.authority,
        license_policy=record.license_policy,
        integrity=record.integrity,
    )
    assert not _pack((foreign,)).verify().valid


def test_atomic_write_reopen_detects_external_mutation_and_collision(tmp_path) -> None:
    pack = _pack().transition_to(KnowledgePackState.VERIFIED).freeze()
    destination = tmp_path / "pack"
    KnowledgePackStore.write(pack, destination)
    reopened = KnowledgePackStore.read(destination)
    assert reopened.manifest.pack_id == pack.manifest.pack_id
    with pytest.raises(FileExistsError):
        KnowledgePackStore.write(pack, destination)

    record_file = next((destination / "records").glob("*.json"))
    record_file.write_text(record_file.read_text(encoding="utf-8").replace("Example", "Tampered"), encoding="utf-8")
    with pytest.raises(KnowledgePackIntegrityError):
        KnowledgePackStore.read(destination)


def test_derived_index_metadata_does_not_change_identity() -> None:
    pack = _pack()
    changed = KnowledgePackManifest.from_dict(
        {**pack.manifest.to_dict(), "derived_index_metadata": {"path": "broken.sqlite"}}
    )
    assert changed.pack_id == pack.manifest.pack_id
