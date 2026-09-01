from __future__ import annotations

from pathlib import Path

from pd_agent.brain import (
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalResult,
    KnowledgeRetrievalStatus,
    KnowledgeType,
    SourceAuthority,
)
from pd_agent.context import KnowledgeContextSource
from pd_agent.context.models import ContextRequest
from pd_agent.validation import FabricBlockIdentityValidator, PreBuildWorkspaceValidator


ENV = KnowledgeEnvironment(
    minecraft_version="1.21.11",
    loader_version="0.19.3",
    fabric_api_version="0.141.6+1.21.11",
    mappings_version="1.21.11+build.6",
    java_version="21",
)


def _result(need_id: str, content: object) -> KnowledgeRetrievalResult:
    need = KnowledgeNeed(need_id, KnowledgeType.PATTERN, "blocks", ENV)
    item = KnowledgeItem(
        f"item-{need_id}", content, ENV, SourceAuthority.AUTHORITATIVE_ARTIFACT,
        KnowledgeProvenance("fixture", "test", f"fixture:{need_id}"),
    )
    return KnowledgeRetrievalResult(KnowledgeRetrievalStatus.SUCCESS, need, (item,))


def test_repair_specific_context_wins_under_the_single_8192_byte_budget() -> None:
    generic = _result("pre-code:blocks:pattern", {"text": "g" * 4000})
    repair = _result("semantic-repair:RUNTIME_TARGET_STARTUP_FAILURE:symbol:runtime", {"text": "r" * 4000})
    source = KnowledgeContextSource(max_context_bytes=8192)

    context = source.get(ContextRequest(external_context=(generic, repair)))

    ids = [item.metadata["knowledge_item_id"] for item in context]
    assert ids == ["item-semantic-repair:RUNTIME_TARGET_STARTUP_FAILURE:symbol:runtime"]
    assert source.last_traces[0].context_item_ids == tuple(ids)
    assert source.last_traces[1].context_item_ids == ()
    assert any(item.reason == "CONTEXT_BUDGET" for item in source.last_traces[1].rejected_items)
    assert sum(len(item.render().encode("utf-8")) for item in context) <= 8192


def test_brain_off_does_not_inject_external_knowledge() -> None:
    source = KnowledgeContextSource()
    assert source.get(ContextRequest(external_context=())) == ()


def test_invalid_inline_block_identity_is_detected_with_actionable_feedback(tmp_path: Path) -> None:
    source = tmp_path / "src/main/java/example/ExampleMod.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "public class ExampleMod {\n"
        "  Block block = new Block(AbstractBlock.Settings.create().strength(4.0f));\n"
        "}\n",
        encoding="utf-8",
    )

    result = FabricBlockIdentityValidator().validate(tmp_path)

    assert result.status.value == "REPAIRABLE_FAIL"
    assert result.violations[0].code == "FABRIC_BLOCK_IDENTITY_MISSING"
    assert result.violations[0].observed["line"] == 2
    assert "registryKey" in result.violations[0].message


def test_valid_inline_block_identity_is_accepted(tmp_path: Path) -> None:
    source = tmp_path / "src/main/java/example/ExampleMod.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "public class ExampleMod {\n"
        "  Block block = new Block(AbstractBlock.Settings.create().registryKey(key).strength(4.0f));\n"
        "}\n",
        encoding="utf-8",
    )

    result = PreBuildWorkspaceValidator().validate(tmp_path, {"required_resources": []})

    assert result.status.value == "PASS"


def test_invalid_fabric_pattern_integrates_with_prebuild_repair_feedback(tmp_path: Path) -> None:
    source = tmp_path / "src/main/java/example/ExampleMod.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "Block block = new Block(AbstractBlock.Settings.create().strength(4.0f));\n",
        encoding="utf-8",
    )

    result = PreBuildWorkspaceValidator().validate(tmp_path, {"required_resources": []})

    assert result.status.value == "REPAIRABLE_FAIL"
    violation = result.violations[0]
    assert violation.code == "FABRIC_BLOCK_IDENTITY_MISSING"
    assert violation.phase == "PRE_BUILD"
    assert violation.evidence_refs == ("src/main/java/example/ExampleMod.java",)
