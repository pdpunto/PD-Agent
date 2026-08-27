from __future__ import annotations

from pd_agent.brain import (
    KnowledgeEnvironment,
    KnowledgeType,
    PreCodeKnowledgeNeedDeriver,
    PreCodePhase,
    FirstEditTracker,
)


ENV = KnowledgeEnvironment(minecraft_version="1.21.11", loader_version="0.19.3")


def test_capability_mapping_is_bounded_relevant_and_version_sensitive() -> None:
    needs = PreCodeKnowledgeNeedDeriver().derive("Implement a block entity with inventory persistence", ENV).needs
    assert len(needs) <= 8
    assert {need.query for need in needs} >= {"block_entities", "inventories"}
    assert all(need.environment == ENV and need.version_sensitive for need in needs)
    assert all(need.type in {KnowledgeType.API, KnowledgeType.PATTERN, KnowledgeType.CAPABILITY} for need in needs)


def test_all_supported_capabilities_have_deterministic_needs() -> None:
    text = "registries items blocks data components block entities inventories persistence commands events tags recipes loot"
    deriver = PreCodeKnowledgeNeedDeriver(max_needs=8)
    first = deriver.derive(text, ENV)
    second = deriver.derive(text, ENV)
    assert first == second
    assert len(first.needs) == 8
    assert first.phase == PreCodePhase.PRE_FIRST_EDIT


def test_symbol_signal_is_exact_and_zero_signal_is_valid() -> None:
    deriver = PreCodeKnowledgeNeedDeriver()
    empty = deriver.derive("Implement the feature", ENV)
    symbol = deriver.derive("Use Registries.BLOCK in the implementation", ENV)
    assert empty.needs == ()
    assert any(need.type == KnowledgeType.SYMBOL and need.query == "Registries.BLOCK" for need in symbol.needs)


def test_first_edit_tracker_ignores_reads_and_noops() -> None:
    tracker = FirstEditTracker()
    tracker.observe(changed=False, mutation=False)
    tracker.observe(changed=False, mutation=True)
    assert tracker.phase == PreCodePhase.PRE_FIRST_EDIT
    tracker.observe(changed=True, mutation=True)
    assert tracker.first_edit_seen


def test_first_edit_tracker_is_tool_name_agnostic() -> None:
    tracker = FirstEditTracker()
    assert tracker.observe(changed=True, mutation=True) == PreCodePhase.FIRST_EDIT
