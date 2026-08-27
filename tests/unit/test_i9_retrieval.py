from __future__ import annotations

from dataclasses import dataclass

from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeService,
    KnowledgeSourceResult,
    KnowledgeRetrievalStatus,
    FabricConceptPatternKnowledgeSource,
    KnowledgePackIndex,
    KnowledgePackState,
    KnowledgeType,
    RetrievalMatchClass,
    SourceAuthority,
)


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")
NEED = KnowledgeNeed("n", KnowledgeType.API, "registry", ENV)


def _item(item_id: str, content: object, *, authority=SourceAuthority.SECONDARY,
          env=ENV, metadata=None, version_sensitive=True) -> KnowledgeItem:
    provenance = KnowledgeProvenance("source-" + item_id, "test", "fixture:" + item_id)
    return KnowledgeItem(item_id, content, env, authority, provenance, metadata or {}, version_sensitive)


@dataclass
class Source:
    source_id: str
    items: tuple[KnowledgeItem, ...]
    status: CompatibilityStatus = CompatibilityStatus.COMPATIBLE

    source_kind: str = "test"
    artifact_version: str = "1"

    def supports(self, need):
        return True

    def compatibility(self, environment):
        return self.status

    def resolve(self, need, offline=False):
        return KnowledgeSourceResult(
            status=KnowledgeRetrievalStatus.SUCCESS, source_id=self.source_id, source_kind=self.source_kind,
            need=need, items=self.items,
        )


def test_exact_precedes_structured_and_lexical_with_stable_order() -> None:
    source = Source("source", (
        _item("registry", {"title": "unrelated"}),
        _item("structured", {"title": "registry"}, metadata={"record_kind": "API"}),
        _item("lexical", {"title": "registry details"}),
    ))
    result = KnowledgeService((source,)).retrieve_ranked(NEED)
    assert [candidate.record_id for candidate in result.candidates] == ["registry", "structured", "lexical"]
    assert result.candidates[0].match_class == RetrievalMatchClass.EXACT
    assert result.candidates[1].match_class == RetrievalMatchClass.STRUCTURED


def test_incompatible_and_unknown_version_sensitive_are_hard_rejected() -> None:
    incompatible_env = KnowledgeEnvironment(minecraft_version="1.20.1", loader_version="0.19.3")
    unknown_env = KnowledgeEnvironment(loader_version="0.19.3")
    source = Source("source", (
        _item("wrong", {"title": "registry"}, env=incompatible_env),
        _item("unknown", {"title": "registry"}, env=unknown_env),
    ))
    result = KnowledgeService((source,)).retrieve_ranked(NEED)
    assert result.candidates == ()
    assert ("wrong", "INCOMPATIBLE") in result.rejected
    assert ("unknown", "UNKNOWN") in result.rejected


def test_authority_and_specificity_are_deterministic_tiebreakers() -> None:
    source = Source("source", (
        _item("z", {"title": "registry"}, authority=SourceAuthority.SECONDARY,
              metadata={"record_kind": "API", "specificity": 1}),
        _item("a", {"title": "registry"}, authority=SourceAuthority.AUTHORITATIVE_ARTIFACT,
              metadata={"record_kind": "API", "specificity": 1}),
    ))
    result = KnowledgeService((source,)).retrieve_ranked(NEED)
    assert [candidate.record_id for candidate in result.candidates] == ["a", "z"]


def test_same_identity_deduplicates_but_same_text_different_identity_conflicts() -> None:
    duplicate = _item("duplicate", {"title": "registry"}, metadata={"record_identity": "same"})
    first = _item("one", {"capability": "registry", "value": "a"}, metadata={"capability": "registry"})
    second = _item("two", {"capability": "registry", "value": "b"}, metadata={"capability": "registry"})
    result = KnowledgeService((Source("source", (duplicate, duplicate, first, second)),)).retrieve_ranked(NEED)
    assert [candidate.record_id for candidate in result.candidates].count("duplicate") == 1
    assert result.conflict_status.value == "unresolved"
    assert result.conflicts[0].candidate_ids == ("one", "two")
    assert len(result.conflicts[0].provenance) == 2


def test_partial_source_failure_degrades_without_losing_valid_candidates() -> None:
    class Failing(Source):
        def resolve(self, need, offline=False):
            raise RuntimeError("offline source failed")

    result = KnowledgeService((Failing("failed", ()), Source("good", (_item("registry", {"x": "registry"}),)))).retrieve_ranked(NEED)
    assert result.items
    assert result.degraded


def test_bounds_and_malformed_lexical_query_are_safe() -> None:
    items = tuple(_item(str(index), {"title": "registry"}) for index in range(20))
    result = KnowledgeService((Source("source", items),)).retrieve_ranked(
        KnowledgeNeed("n", KnowledgeType.API, '" OR DROP TABLE records; --', ENV), max_candidates=3
    )
    assert len(result.candidates) <= 3


def test_unknown_version_insensitive_remains_allowed() -> None:
    unknown = KnowledgeEnvironment(loader_version="0.19.3")
    need = KnowledgeNeed("n", KnowledgeType.CONCEPT, "registry", ENV, version_sensitive=False)
    result = KnowledgeService((Source("source", (_item("concept", {"title": "registry"}, env=unknown, version_sensitive=False),)),)).retrieve_ranked(need)
    assert result.items


def test_frozen_canonical_pack_and_i8_index_feed_the_same_bounded_pipeline(tmp_path) -> None:
    target = KnowledgeEnvironment(
        minecraft_version="1.21.11", loader_version="0.19.3",
        mappings_namespace="yarn", mappings_version="1.21.11+build.6",
        fabric_api_version="0.141.6+1.21.11",
    )
    pack = FabricConceptPatternKnowledgeSource().materialize_pack(target).transition_to(
        KnowledgePackState.VERIFIED
    ).freeze()
    index = KnowledgePackIndex.build(pack, tmp_path / "knowledge.sqlite")
    need = KnowledgeNeed("concept", KnowledgeType.CONCEPT, "registry", target)
    result = KnowledgeService().retrieve_ranked(need, indexes=(index,), packs=(pack,))
    assert result.candidates
    assert all(candidate.compatibility == CompatibilityStatus.COMPATIBLE for candidate in result.candidates)
    assert all(candidate.item.metadata["record_identity"] for candidate in result.candidates)
    index.close()
