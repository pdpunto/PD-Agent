from __future__ import annotations

import json
from pathlib import Path

import pytest

from pd_agent.core import (
    ArtifactIdentity,
    BuildAttemptIdentity,
    EvidenceBinding,
    FabricRequirement,
    FabricTaskContract,
    FabricValidationRequirement,
    RunState,
    RuntimeAttemptIdentity,
    compute_source_revision,
    validation_contract_revision,
)


def _contract() -> FabricTaskContract:
    return FabricTaskContract(
        task_id="fabric-task",
        revision="1",
        goal="make the feature",
        requirements=(FabricRequirement(requirement_id="r1", description="feature exists"),),
        validation_requirements=(FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("r1",), kind="runtime", spec={"expected": "pass"}),),
    )


def test_source_revision_is_deterministic_and_ignores_derived_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
    first = compute_source_revision(tmp_path)
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "output.jar").write_bytes(b"derived")
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "run.json").write_text("evidence", encoding="utf-8")
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp" / "transient").write_text("temporary", encoding="utf-8")
    assert compute_source_revision(tmp_path) == first
    assert compute_source_revision(tmp_path).file_count == 1


def test_source_mutation_changes_revision(tmp_path: Path) -> None:
    file_path = tmp_path / "README.md"
    file_path.write_text("one", encoding="utf-8")
    first = compute_source_revision(tmp_path)
    file_path.write_text("two", encoding="utf-8")
    assert compute_source_revision(tmp_path).revision != first.revision


def test_source_hash_does_not_follow_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-i3.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "outside-link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = compute_source_revision(tmp_path)
    assert result.file_count == 0
    outside.unlink()


def test_contract_and_validation_fingerprints_are_stable_and_material() -> None:
    contract = _contract()
    assert contract.identity()[2] == contract.fingerprint
    requirement = contract.validation_requirements[0]
    assert validation_contract_revision(requirement) == validation_contract_revision(requirement.to_dict())
    changed = FabricValidationRequirement(validation_requirement_id="v1", requirement_ids=("r1",), kind="runtime", spec={"expected": "different"})
    assert validation_contract_revision(changed) != validation_contract_revision(requirement)


def test_build_artifact_and_runtime_bindings_require_current_identities() -> None:
    contract = _contract()
    identity = BuildAttemptIdentity(build_attempt_id="b1", source_revision="a" * 64, contract_identity=contract.identity(), toolchain_identity="java-21", success=True)
    assert identity.is_current(source_revision="a" * 64, contract_identity=contract.identity(), toolchain_identity="java-21")
    assert not identity.is_current(source_revision="b" * 64, contract_identity=contract.identity())
    artifact = ArtifactIdentity(artifact_identity="c" * 64, sha256="c" * 64, producing_build_attempt_id="b1", source_revision="a" * 64, contract_identity=contract.identity())
    assert artifact.is_current(identity, source_revision="a" * 64, contract_identity=contract.identity())
    runtime = RuntimeAttemptIdentity(runtime_attempt_id="r1", artifact_identity=artifact.artifact_identity, validation_revision="v" * 64, requirement_ids=("r1",))
    assert runtime.is_current(artifact_identity=artifact.artifact_identity, validation_revision="v" * 64)
    assert not runtime.is_current(artifact_identity="d" * 64, validation_revision="v" * 64)


def test_evidence_stale_reason_is_deterministic_without_deleting_history() -> None:
    binding = EvidenceBinding(evidence_id="e1", evidence_kind="runtime", source_revision="a" * 64, artifact_identity="b" * 64, validation_revision="c" * 64)
    stale = binding.evaluate_currentness(source_revision="d" * 64, artifact_identity="b" * 64, validation_revision="c" * 64)
    assert stale.stale_for_completion is True
    assert stale.stale_reason == "source_revision_changed"
    assert stale.superseding_identity == "d" * 64
    assert binding.stale_for_completion is False


def test_currentness_facts_roundtrip_and_legacy_run_state_readback() -> None:
    contract = _contract()
    binding = EvidenceBinding(evidence_id="e1", evidence_kind="build", source_revision="a" * 64)
    state = RunState(task="legacy", source_revision=None, evidence_bindings=(binding,))
    restored = RunState.from_dict(state.to_dict())
    assert restored.evidence_bindings == (binding,)
    legacy = RunState.from_dict(json.loads(json.dumps({"run_id": state.run_id, "task": "old"})))
    assert legacy.task == "old"
    assert contract.identity()[0] == "fabric-task"
