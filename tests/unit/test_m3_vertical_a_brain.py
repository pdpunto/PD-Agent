from __future__ import annotations

from pd_agent.brain import (
    CompatibilityStatus,
    FabricVerticalAKnowledgeSource,
    FabricBrainOrchestrator,
    KnowledgeEnvironment,
    KnowledgeNeed,
    KnowledgeService,
    KnowledgeType,
    PreCodeKnowledgeNeedDeriver,
    select_knowledge_sources_for_environment,
    YarnKnowledgeSource,
)
from pd_agent.core import FabricTaskContract


LEGACY = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    loom_version="1.13.3",
    mappings_namespace="yarn",
    mappings_version="1.21.11+build.6",
    fabric_api_version="0.141.6+1.21.11",
    java_version="21",
)
MODERN = KnowledgeEnvironment(
    minecraft_version="26.2",
    loader_version="0.19.3",
    loom_version="1.17-SNAPSHOT",
    fabric_api_version="0.158.0+26.2",
    java_version="25",
)
VERTICAL_A_REQUEST = (
    "compose a block with an associated block item, blockstate, block model, "
    "item model, texture asset and craftable recipe"
)


def test_vertical_a_needs_are_bounded_complete_and_deterministic() -> None:
    deriver = PreCodeKnowledgeNeedDeriver()
    first = deriver.derive(VERTICAL_A_REQUEST, LEGACY)
    second = deriver.derive(VERTICAL_A_REQUEST, LEGACY)

    assert deriver.max_needs == 8
    assert first == second
    assert len(first.needs) == 8
    assert [need.query for need in first.needs] == [
        "vertical_a_composition", "block_registration", "block_item",
        "blockstate_asset", "block_model_asset", "item_model_asset",
        "texture_reference", "recipe_resource",
    ]
    assert all(need.environment == LEGACY and need.version_sensitive for need in first.needs)


def test_vertical_a_need_dedup_is_not_truncated_by_repeated_signals() -> None:
    deriver = PreCodeKnowledgeNeedDeriver()
    result = deriver.derive(
        VERTICAL_A_REQUEST,
        LEGACY,
        capability_signals=("block", "block item", "assets", "recipe", "composition"),
    )
    assert len(result.needs) == 8
    assert len({need.id for need in result.needs}) == 8
    assert {need.query for need in result.needs} >= {"recipe_resource", "texture_reference", "block_item"}


def test_vertical_a_source_serves_both_exact_platform_environments() -> None:
    source = FabricVerticalAKnowledgeSource()
    for environment in (LEGACY, MODERN):
        needs = PreCodeKnowledgeNeedDeriver().derive(VERTICAL_A_REQUEST, environment).needs
        results = [source.resolve(need, offline=True) for need in needs]
        assert all(result.status.value == "SUCCESS" for result in results)
        assert all(result.items[0].environment == environment for result in results)
        assert all(result.items[0].provenance.source_id == source.source_id for result in results)
        assert all(result.items[0].version_sensitive for result in results)


def test_26_2_selects_vertical_a_and_rejects_yarn_without_leakage() -> None:
    source = FabricVerticalAKnowledgeSource()
    yarn = YarnKnowledgeSource()
    selection = select_knowledge_sources_for_environment(MODERN, (source, yarn))

    assert [item.source_id for item in selection.selected] == [source.source_id]
    assert selection.rejected == (("net.fabricmc:yarn", CompatibilityStatus.INCOMPATIBLE, "source environment incompatible"),)


def test_incompatible_vertical_a_environment_fails_closed() -> None:
    source = FabricVerticalAKnowledgeSource()
    need = KnowledgeNeed(
        id="vertical-a-rejected",
        type=KnowledgeType.PATTERN,
        query="recipe_resource",
        environment=KnowledgeEnvironment(minecraft_version="26.1.2"),
    )
    result = KnowledgeService((source,)).resolve(need, offline=True)
    assert result.status.value == "VERSION_MISMATCH"
    assert result.items == ()


def test_vertical_a_brain_preparation_preserves_selection_and_trace() -> None:
    result = FabricBrainOrchestrator(
        knowledge_service=KnowledgeService((FabricVerticalAKnowledgeSource(),))
    ).prepare(
        contract=FabricTaskContract(task_id="vertical-a", revision="1", goal=VERTICAL_A_REQUEST, requirements=()),
        environment=LEGACY,
    )

    assert len(result.needs) == 8
    assert result.retrieved_count == 8
    assert result.selected_count > 0
    assert result.injected_context_item_ids
    assert len(result.traces) == 8
    assert all(trace.environment == LEGACY for trace in result.traces)
