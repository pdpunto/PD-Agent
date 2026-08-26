from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pd_agent.core import SecurityViolation
from pd_agent.minecraft import MinecraftEvidenceKind, MinecraftEvidenceReference, PersistencePhase, PersistenceScenario


SHA = "a" * 64


def _phase_one(**overrides: object) -> PersistenceScenario:
    values: dict[str, object] = {
        "scenario_id": "scenario-001",
        "world_id": "world-001",
        "world_root": "runtime/world",
        "target_artifact_sha256": SHA,
        "test_id": "persistence-b",
        "phase": PersistencePhase.PHASE_1,
        "expected_observation_id": "inventory-before-save",
        "process_id": "phase1-process",
        "evidence_refs": (),
    }
    values.update(overrides)
    return PersistenceScenario(**values)


def test_phase_one_round_trip_and_confined_resolution(tmp_path: Path) -> None:
    scenario = _phase_one(
        evidence_refs=(
            MinecraftEvidenceReference(
                kind=MinecraftEvidenceKind.SCENARIO,
                ref="scenario.json",
                phase="PHASE_1",
                scenario_id="scenario-001",
            ),
        )
    )
    assert PersistenceScenario.from_dict(json.loads(scenario.to_json())) == scenario
    authorized = tmp_path / "execution"
    authorized.mkdir()
    assert scenario.resolve_world_root(authorized) == (authorized / "runtime/world").resolve()


def test_phase_two_requires_reopen_and_distinct_process() -> None:
    scenario = PersistenceScenario(
        scenario_id="scenario-001",
        world_id="world-001",
        world_root="runtime/world",
        target_artifact_sha256=SHA,
        test_id="persistence-b",
        phase=PersistencePhase.PHASE_2,
        expected_observation_id="inventory-after-reopen",
        process_id="phase2-process",
        predecessor_process_id="phase1-process",
        same_world_required=True,
        reopen_only=True,
        setup_allowed=False,
        mutation_allowed_before_observation=False,
        world_root_must_exist=True,
        world_fingerprint={"level_name": "world", "dimension": "minecraft:overworld"},
    )
    assert PersistenceScenario.from_dict(scenario.to_dict()) == scenario


@pytest.mark.parametrize(
    "overrides",
    [
        {"world_root": "C:/outside"},
        {"world_root": "runtime/../outside"},
        {"target_artifact_sha256": "not-a-sha"},
        {"phase": "UNKNOWN"},
        {"phase": PersistencePhase.PHASE_2},
    ],
)
def test_scenario_rejects_invalid_phase_or_identity(overrides: dict[str, object]) -> None:
    with pytest.raises((ValueError, SecurityViolation)):
        _phase_one(**overrides)


def test_phase_two_rejects_setup_mutation_or_missing_same_world_proof() -> None:
    base = {
        "phase": PersistencePhase.PHASE_2,
        "predecessor_process_id": "phase1-process",
        "same_world_required": True,
        "reopen_only": True,
        "setup_allowed": False,
        "mutation_allowed_before_observation": False,
        "world_fingerprint": {"level_name": "world"},
    }
    for field in ("same_world_required", "reopen_only", "setup_allowed", "mutation_allowed_before_observation"):
        invalid = dict(base)
        invalid[field] = not bool(base[field])
        with pytest.raises(ValueError):
            _phase_one(**invalid)
    with pytest.raises(ValueError):
        _phase_one(**{**base, "predecessor_process_id": "phase2-process"})
    with pytest.raises(ValueError):
        _phase_one(**{**base, "world_fingerprint": None})


def test_deserialization_rejects_non_boolean_phase_flags() -> None:
    payload = _phase_one().to_dict()
    payload["setup_allowed"] = "false"
    with pytest.raises(ValueError):
        PersistenceScenario.from_dict(payload)


def test_world_root_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unsupported")
    authorized = tmp_path / "execution"
    outside = tmp_path / "outside"
    authorized.mkdir()
    outside.mkdir()
    link = authorized / "runtime"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(SecurityViolation):
        _phase_one().resolve_world_root(authorized)


def test_evidence_reference_cannot_escape_or_change_scenario() -> None:
    with pytest.raises(ValueError):
        MinecraftEvidenceReference(kind=MinecraftEvidenceKind.WORLD, ref="../world")
    with pytest.raises(ValueError):
        _phase_one(
            evidence_refs=(
                MinecraftEvidenceReference(
                    kind=MinecraftEvidenceKind.WORLD,
                    ref="world.json",
                    scenario_id="other-scenario",
                ),
            )
        )
