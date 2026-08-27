"""Execution planning and durable requirement progress facts for v0.8 I2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping


SCHEMA_VERSION = 1


def _text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _ids(values: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a sequence of IDs")
    result = tuple(_text(value, field_name=field_name) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return result


def _refs(values: Any, *, field_name: str) -> tuple[str, ...]:
    result = _ids(values, field_name=field_name)
    if any(len(ref.encode("utf-8")) > 512 for ref in result):
        raise ValueError(f"{field_name} contains an oversized evidence reference")
    return result


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class PlanStepStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionPlanStep:
    step_id: str
    intent: str
    requirement_ids: tuple[str, ...] = ()
    status: PlanStepStatus = PlanStepStatus.PENDING

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _text(self.step_id, field_name="step_id"))
        object.__setattr__(self, "intent", _text(self.intent, field_name="intent"))
        object.__setattr__(self, "requirement_ids", _ids(self.requirement_ids, field_name="requirement_ids"))
        if not isinstance(self.status, PlanStepStatus):
            try:
                object.__setattr__(self, "status", PlanStepStatus(str(self.status)))
            except ValueError as exc:
                raise ValueError("status is not a valid plan step status") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "intent": self.intent,
            "requirement_ids": list(self.requirement_ids),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionPlanStep":
        return cls(
            step_id=data["step_id"],
            intent=data["intent"],
            requirement_ids=tuple(data.get("requirement_ids", ())),
            status=data.get("status", PlanStepStatus.PENDING.value),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionPlan:
    """Ordered, lightweight intent guidance; never a completion authority."""

    plan_id: str
    revision: str
    steps: tuple[ExecutionPlanStep, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text(self.plan_id, field_name="plan_id"))
        object.__setattr__(self, "revision", _text(self.revision, field_name="revision"))
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        steps = tuple(self.steps)
        if not all(isinstance(step, ExecutionPlanStep) for step in steps):
            raise ValueError("steps must contain ExecutionPlanStep values")
        if len({step.step_id for step in steps}) != len(steps):
            raise ValueError("steps must not contain duplicate step IDs")
        object.__setattr__(self, "steps", steps)

    def validate_against(self, requirement_ids: Any) -> None:
        known = set(_ids(requirement_ids, field_name="requirement_ids"))
        dangling = {
            requirement_id
            for step in self.steps
            for requirement_id in step.requirement_ids
            if requirement_id not in known
        }
        if dangling:
            raise ValueError(f"plan references unknown requirements: {sorted(dangling)!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "revision": self.revision,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionPlan":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            plan_id=data["plan_id"],
            revision=data["revision"],
            steps=tuple(ExecutionPlanStep.from_dict(item) for item in data.get("steps", ())),
        )


class FailureFactStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True, kw_only=True)
class FailureFact:
    """Append-only, lightweight failure fact with an objective resolution link."""

    failure_id: str
    status: FailureFactStatus
    requirement_ids: tuple[str, ...]
    code: str
    category: str
    evidence_refs: tuple[str, ...] = ()
    resolution_evidence_refs: tuple[str, ...] = ()
    fingerprint: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("failure_id", "code", "category"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name=field_name))
        if not isinstance(self.status, FailureFactStatus):
            try:
                object.__setattr__(self, "status", FailureFactStatus(str(self.status)))
            except ValueError as exc:
                raise ValueError("status is not a valid failure fact status") from exc
        object.__setattr__(self, "requirement_ids", _ids(self.requirement_ids, field_name="requirement_ids"))
        object.__setattr__(self, "evidence_refs", _refs(self.evidence_refs, field_name="evidence_refs"))
        object.__setattr__(self, "resolution_evidence_refs", _refs(self.resolution_evidence_refs, field_name="resolution_evidence_refs"))
        if self.status is FailureFactStatus.RESOLVED and not self.resolution_evidence_refs:
            raise ValueError("resolved failure requires resolution evidence references")
        payload = self._identity_payload()
        expected = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        if self.fingerprint is not None and self.fingerprint != expected:
            raise ValueError("failure fingerprint does not match its content")
        object.__setattr__(self, "fingerprint", expected)

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "status": self.status.value,
            "requirement_ids": list(self.requirement_ids),
            "code": self.code,
            "category": self.category,
            "evidence_refs": list(self.evidence_refs),
            "resolution_evidence_refs": list(self.resolution_evidence_refs),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._identity_payload(), "fingerprint": self.fingerprint}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailureFact":
        return cls(
            failure_id=data["failure_id"],
            status=data["status"],
            requirement_ids=tuple(data.get("requirement_ids", ())),
            code=data["code"],
            category=data["category"],
            evidence_refs=tuple(data.get("evidence_refs", ())),
            resolution_evidence_refs=tuple(data.get("resolution_evidence_refs", ())),
            fingerprint=data.get("fingerprint"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskProgressLedger:
    """Durable requirement facts associated with RunState, not a state machine."""

    contract_identity: tuple[str, str, str]
    satisfied_requirement_ids: tuple[str, ...] = ()
    evidence_by_requirement: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    failures: tuple[FailureFact, ...] = ()
    validation_evidence_refs: tuple[str, ...] = ()
    knowledge_correlation: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    next_safe_disposition: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.contract_identity, (tuple, list)) or len(self.contract_identity) != 3:
            raise ValueError("contract_identity must contain task_id, revision and fingerprint")
        object.__setattr__(self, "contract_identity", tuple(_text(item, field_name="contract_identity") for item in self.contract_identity))
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
        object.__setattr__(self, "satisfied_requirement_ids", _ids(self.satisfied_requirement_ids, field_name="satisfied_requirement_ids"))
        object.__setattr__(self, "validation_evidence_refs", _refs(self.validation_evidence_refs, field_name="validation_evidence_refs"))
        if not isinstance(self.evidence_by_requirement, Mapping):
            raise ValueError("evidence_by_requirement must be a mapping")
        evidence = {key: _refs(value, field_name=f"evidence_by_requirement[{key}]") for key, value in self.evidence_by_requirement.items()}
        if any(not isinstance(key, str) or not key.strip() for key in evidence):
            raise ValueError("evidence_by_requirement keys must be non-empty strings")
        object.__setattr__(self, "evidence_by_requirement", evidence)
        failures = tuple(self.failures)
        if not all(isinstance(item, FailureFact) for item in failures):
            raise ValueError("failures must contain FailureFact values")
        if len({(item.failure_id, item.status) for item in failures}) != len(failures):
            raise ValueError("failures must not contain duplicate failure states")
        object.__setattr__(self, "failures", failures)
        if not isinstance(self.knowledge_correlation, Mapping):
            raise ValueError("knowledge_correlation must be a mapping")
        correlation = {key: _refs(value, field_name=f"knowledge_correlation[{key}]") for key, value in self.knowledge_correlation.items()}
        object.__setattr__(self, "knowledge_correlation", correlation)
        if self.next_safe_disposition is not None:
            object.__setattr__(self, "next_safe_disposition", _text(self.next_safe_disposition, field_name="next_safe_disposition"))

    def validate_against(self, requirement_ids: Any) -> None:
        known = set(_ids(requirement_ids, field_name="requirement_ids"))
        satisfied = set(self.satisfied_requirement_ids)
        unknown = satisfied - known
        evidence_unknown = set(self.evidence_by_requirement) - known
        failure_unknown = {item for failure in self.failures for item in failure.requirement_ids if item not in known}
        if unknown:
            raise ValueError(f"satisfied requirements are unknown: {sorted(unknown)!r}")
        if evidence_unknown:
            raise ValueError(f"evidence references unknown requirements: {sorted(evidence_unknown)!r}")
        if failure_unknown:
            raise ValueError(f"failure references unknown requirements: {sorted(failure_unknown)!r}")
        if satisfied.intersection(set(self.evidence_by_requirement) - satisfied):
            raise ValueError("ledger contains contradictory requirement progress")

    def pending_requirement_ids(self, requirement_ids: Any) -> tuple[str, ...]:
        known = _ids(requirement_ids, field_name="requirement_ids")
        self.validate_against(known)
        satisfied = set(self.satisfied_requirement_ids)
        return tuple(item for item in known if item not in satisfied)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_identity": list(self.contract_identity),
            "satisfied_requirement_ids": list(self.satisfied_requirement_ids),
            "evidence_by_requirement": {key: list(value) for key, value in sorted(self.evidence_by_requirement.items())},
            "failures": [item.to_dict() for item in self.failures],
            "validation_evidence_refs": list(self.validation_evidence_refs),
            "knowledge_correlation": {key: list(value) for key, value in sorted(self.knowledge_correlation.items())},
            "next_safe_disposition": self.next_safe_disposition,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskProgressLedger":
        return cls(
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            contract_identity=tuple(data["contract_identity"]),
            satisfied_requirement_ids=tuple(data.get("satisfied_requirement_ids", ())),
            evidence_by_requirement={key: tuple(value) for key, value in data.get("evidence_by_requirement", {}).items()},
            failures=tuple(FailureFact.from_dict(item) for item in data.get("failures", ())),
            validation_evidence_refs=tuple(data.get("validation_evidence_refs", ())),
            knowledge_correlation={key: tuple(value) for key, value in data.get("knowledge_correlation", {}).items()},
            next_safe_disposition=data.get("next_safe_disposition"),
        )


__all__ = [
    "ExecutionPlan",
    "ExecutionPlanStep",
    "FailureFact",
    "FailureFactStatus",
    "PlanStepStatus",
    "TaskProgressLedger",
]
