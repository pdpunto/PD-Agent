from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pd_agent.brain import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalStatus,
    KnowledgeService,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)


ENVIRONMENT = KnowledgeEnvironment(minecraft_version="1.21.11")
NEED = KnowledgeNeed("need-1", KnowledgeType.API, "Registry", ENVIRONMENT)


def _item(item_id: str, *, identity: str | None = None, text: str = "value") -> KnowledgeItem:
    return KnowledgeItem(
        id=item_id,
        content={"text": text},
        environment=ENVIRONMENT,
        authority=SourceAuthority.AUTHORITATIVE_SOURCE,
        provenance=KnowledgeProvenance("source", "fixture", f"fixture://{item_id}", license_id_or_policy="ok"),
        metadata={"record_identity": identity} if identity else {},
    )


@dataclass
class FakeSource:
    source_id: str
    result: KnowledgeSourceResult | None = None
    compatibility_value: CompatibilityStatus = CompatibilityStatus.COMPATIBLE
    supports_value: bool = True
    calls: list[str] = field(default_factory=list)
    source_kind: str = "fixture"
    artifact_version: str = "1"

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        self.calls.append("compatibility")
        return self.compatibility_value

    def supports(self, need: KnowledgeNeed) -> bool:
        self.calls.append("supports")
        return self.supports_value

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        self.calls.append("resolve")
        assert self.result is not None
        return self.result

    def make_result(self, status=KnowledgeRetrievalStatus.SUCCESS, items=(), error=None):
        self.result = KnowledgeSourceResult(status, self.source_id, self.source_kind, NEED, tuple(items), error=error)
        return self


def test_zero_sources_degrades_safely() -> None:
    result = KnowledgeService().resolve(NEED)
    assert result.status == KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE
    assert result.source_results == ()


def test_sources_are_sorted_and_partial_failures_preserve_attempts_and_items() -> None:
    first = FakeSource("z").make_result(items=(_item("z-item"),))
    failed = FakeSource("b").make_result(KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE, error="offline")
    last = FakeSource("a").make_result(items=(_item("a-item"),))
    result = KnowledgeService((first, failed, last)).resolve(NEED)

    assert [attempt.source_id for attempt in result.source_results] == ["a", "b", "z"]
    assert [item.id for item in result.items] == ["a-item", "z-item"]
    assert result.status == KnowledgeRetrievalStatus.SUCCESS
    assert failed.calls == ["compatibility", "supports", "resolve"]


@pytest.mark.parametrize(
    "compatibility,supports,expected_calls,expected_status",
    [
        (CompatibilityStatus.COMPATIBLE, False, ["compatibility", "supports"], KnowledgeRetrievalStatus.UNSUPPORTED_NEED),
        (CompatibilityStatus.INCOMPATIBLE, True, ["compatibility"], KnowledgeRetrievalStatus.VERSION_MISMATCH),
        (CompatibilityStatus.UNKNOWN, True, ["compatibility"], KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE),
    ],
)
def test_eligibility_gate_precedes_resolve(compatibility, supports, expected_calls, expected_status) -> None:
    source = FakeSource("source", compatibility_value=compatibility, supports_value=supports).make_result()
    result = KnowledgeService((source,)).resolve(NEED)
    assert source.calls == expected_calls
    assert result.source_results[0].status == expected_status
    assert result.source_results[0].eligible is False


def test_compatible_supported_source_resolves() -> None:
    source = FakeSource("source").make_result(items=(_item("item"),))
    result = KnowledgeService((source,)).resolve(NEED)
    assert source.calls == ["compatibility", "supports", "resolve"]
    assert result.source_results[0].eligible is True
    assert result.source_results[0].supported is True


def test_cross_source_duplicate_identity_is_deduplicated_but_attempt_provenance_remains() -> None:
    left = FakeSource("left").make_result(items=(_item("left", identity="same"),))
    right = FakeSource("right").make_result(items=(_item("right", identity="same"),))
    result = KnowledgeService((right, left)).resolve(NEED)
    assert [item.id for item in result.items] == ["left"]
    assert [attempt.source_id for attempt in result.source_results] == ["left", "right"]
    assert result.source_results[1].items[0].provenance.source_id == "source"


def test_different_identities_are_not_deduplicated_by_similar_text() -> None:
    first = FakeSource("a").make_result(items=(_item("a", identity="one", text="same"),))
    second = FakeSource("b").make_result(items=(_item("b", identity="two", text="same"),))
    assert len(KnowledgeService((first, second)).resolve(NEED).items) == 2


def test_unknown_non_version_sensitive_need_may_resolve() -> None:
    need = KnowledgeNeed("need-2", KnowledgeType.API, "Registry", ENVIRONMENT, version_sensitive=False)
    source = FakeSource("source", compatibility_value=CompatibilityStatus.UNKNOWN).make_result(items=(_item("item"),))
    assert KnowledgeService((source,)).resolve(need).status == KnowledgeRetrievalStatus.SUCCESS
