"""Deterministic, bounded normalization of Gradle build failures for v0.8 I4."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from pd_agent.core import BuildResult, FailureFact, FailureFactStatus, ValidationStatus, ValidationViolation


class BuildFailureCategory(StrEnum):
    COMPILATION_ERROR = "COMPILATION_ERROR"
    MISSING_SYMBOL = "MISSING_SYMBOL"
    SIGNATURE_OR_API_MISMATCH = "SIGNATURE_OR_API_MISMATCH"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    TIMEOUT = "TIMEOUT"
    ENVIRONMENT_OR_INFRASTRUCTURE = "ENVIRONMENT_OR_INFRASTRUCTURE"
    UNKNOWN = "UNKNOWN"


class FailureClassification(StrEnum):
    REPAIRABLE_FAIL = ValidationStatus.REPAIRABLE_FAIL.value
    BLOCKED = ValidationStatus.BLOCKED.value


_PATH_LINE = re.compile(r"(?P<path>(?:[A-Za-z]:)?[^\r\n:()]+\.(?:java|kt)):(?P<line>\d+)")
_SYMBOL = re.compile(r"(?:symbol:\s*(?:class|variable|method)\s+|cannot find symbol[^\r\n]*\b)(?P<symbol>[A-Za-z_$][\w$]*(?:\([^\r\n)]*\))?)", re.IGNORECASE)
_SIGNATURE = re.compile(r"(?:method|constructor)\s+(?P<symbol>[A-Za-z_$][\w$]*)[^\r\n]*(?:cannot be applied|cannot be found|argument|given|required|overload)", re.IGNORECASE)

_DEPENDENCY_MARKERS = ("could not resolve", "could not find", "failed to resolve", "dependency", "unresolved dependency", "plugin portal")
_ENVIRONMENT_MARKERS = ("permission denied", "access is denied", "file lock", "lock timeout", "gradle_user_home", "java_home", "daemon disappeared", "application control", "network is unreachable")
_TIMEOUT_MARKERS = ("timed out", "timeout", "time-out", "process exceeded")
_API_MARKERS = ("fabric api", "yarn", "minecraft", "incompatible types", "no suitable method", "cannot be applied to given types", "does not override")


def _canonical(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _short_fragment(text: str, *, limit: int = 480) -> str:
    normalized = " ".join(text.split())
    return normalized[:limit]


def _redact(text: str) -> str:
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    return text


@dataclass(frozen=True, slots=True)
class NormalizedBuildFailure:
    """Small structured failure fact; the original log remains an evidence ref."""

    code: str
    category: BuildFailureCategory
    classification: FailureClassification
    requirement_ids: tuple[str, ...] = ()
    symbol_hints: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    signature_hints: tuple[str, ...] = ()
    capability_hints: tuple[str, ...] = ()
    concise_diagnostic: str = ""
    evidence_refs: tuple[str, ...] = ()
    source_revision: str | None = None
    build_attempt_id: str | None = None
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.category, BuildFailureCategory):
            object.__setattr__(self, "category", BuildFailureCategory(str(self.category)))
        if not isinstance(self.classification, FailureClassification):
            object.__setattr__(self, "classification", FailureClassification(str(self.classification)))
        object.__setattr__(self, "requirement_ids", tuple(dict.fromkeys(str(item) for item in self.requirement_ids)))
        object.__setattr__(self, "symbol_hints", tuple(dict.fromkeys(str(item) for item in self.symbol_hints)))
        object.__setattr__(self, "file_hints", tuple(dict.fromkeys(str(item) for item in self.file_hints)))
        object.__setattr__(self, "signature_hints", tuple(dict.fromkeys(str(item) for item in self.signature_hints)))
        object.__setattr__(self, "capability_hints", tuple(dict.fromkeys(str(item) for item in self.capability_hints)))
        object.__setattr__(self, "evidence_refs", tuple(dict.fromkeys(str(item) for item in self.evidence_refs)))
        object.__setattr__(self, "concise_diagnostic", _redact(_short_fragment(self.concise_diagnostic)))
        payload = self._fingerprint_payload()
        expected = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("failure fingerprint does not match normalized content")
        object.__setattr__(self, "fingerprint", expected)

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "classification": self.classification.value,
            "requirement_ids": list(self.requirement_ids),
            "symbol_hints": list(self.symbol_hints),
            "file_hints": list(self.file_hints),
            "signature_hints": list(self.signature_hints),
            "capability_hints": list(self.capability_hints),
            "source_revision": self.source_revision,
            "build_attempt_id": self.build_attempt_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._fingerprint_payload(), "concise_diagnostic": self.concise_diagnostic, "evidence_refs": list(self.evidence_refs), "fingerprint": self.fingerprint}

    def to_violation(self, *, requirement: str = "build") -> ValidationViolation:
        return ValidationViolation(code=self.code, requirement=requirement, observed=self.to_dict(), expected="successful build", actual=self.category.value, message=self.concise_diagnostic or self.category.value, evidence_refs=self.evidence_refs, phase="BUILD")

    def to_failure_fact(self, *, failure_id: str) -> FailureFact:
        return FailureFact(failure_id=failure_id, status=FailureFactStatus.ACTIVE, requirement_ids=self.requirement_ids, code=self.code, category=self.category.value, evidence_refs=self.evidence_refs)


class BuildFailureNormalizer:
    """Classify bounded BuildResult output without performing any side effects."""

    def normalize(
        self,
        result: BuildResult,
        *,
        source_revision: str | None = None,
        build_attempt_id: str | None = None,
        evidence_refs: Iterable[str] = (),
        requirement_ids: Iterable[str] = (),
        timed_out: bool = False,
    ) -> NormalizedBuildFailure | None:
        if not isinstance(result, BuildResult):
            raise TypeError("result must be a BuildResult")
        if result.success:
            return None
        raw = f"{result.stdout_log}\n{result.stderr_log}"
        text = raw.casefold()
        category, code, classification = self._classify(text, timed_out=timed_out)
        path_hints = tuple(match.group("path").strip() for match in _PATH_LINE.finditer(raw))[:4]
        symbols = tuple(match.group("symbol") for match in _SYMBOL.finditer(raw))[:4]
        signatures = tuple(match.group("symbol") for match in _SIGNATURE.finditer(raw))[:4]
        capabilities = tuple(marker for marker in ("fabric", "yarn", "minecraft", "gradle") if marker in text)
        diagnostic = self._diagnostic(raw, category)
        return NormalizedBuildFailure(code=code, category=category, classification=classification, requirement_ids=tuple(requirement_ids), symbol_hints=symbols, file_hints=path_hints, signature_hints=signatures, capability_hints=capabilities, concise_diagnostic=diagnostic, evidence_refs=tuple(evidence_refs), source_revision=source_revision, build_attempt_id=build_attempt_id)

    def _classify(self, text: str, *, timed_out: bool) -> tuple[BuildFailureCategory, str, FailureClassification]:
        if timed_out or any(marker in text for marker in _TIMEOUT_MARKERS):
            return BuildFailureCategory.TIMEOUT, "BUILD_TIMEOUT", FailureClassification.BLOCKED
        if any(marker in text for marker in _ENVIRONMENT_MARKERS):
            return BuildFailureCategory.ENVIRONMENT_OR_INFRASTRUCTURE, "BUILD_ENVIRONMENT_FAILURE", FailureClassification.BLOCKED
        if any(marker in text for marker in _DEPENDENCY_MARKERS):
            return BuildFailureCategory.DEPENDENCY_ERROR, "BUILD_DEPENDENCY_FAILURE", FailureClassification.BLOCKED
        if "cannot find symbol" in text or "symbol: class" in text or "symbol: variable" in text:
            return BuildFailureCategory.MISSING_SYMBOL, "BUILD_MISSING_SYMBOL", FailureClassification.REPAIRABLE_FAIL
        if any(marker in text for marker in _SIGNATURE_MARKERS(text)):
            return BuildFailureCategory.SIGNATURE_OR_API_MISMATCH, "BUILD_SIGNATURE_OR_API_MISMATCH", FailureClassification.REPAIRABLE_FAIL
        if any(marker in text for marker in _API_MARKERS):
            return BuildFailureCategory.SIGNATURE_OR_API_MISMATCH, "BUILD_API_MISMATCH", FailureClassification.REPAIRABLE_FAIL
        if "compilation failed" in text or "compilejava" in text or "javac" in text:
            return BuildFailureCategory.COMPILATION_ERROR, "BUILD_COMPILATION_ERROR", FailureClassification.REPAIRABLE_FAIL
        return BuildFailureCategory.UNKNOWN, "BUILD_UNKNOWN_FAILURE", FailureClassification.BLOCKED

    def _diagnostic(self, raw: str, category: BuildFailureCategory) -> str:
        for line in raw.splitlines():
            candidate = line.strip()
            if candidate and (":" in candidate or category.value.casefold() in candidate.casefold()):
                return _redact(_short_fragment(candidate))
        return category.value


def _SIGNATURE_MARKERS(text: str) -> tuple[str, ...]:
    return ("cannot be applied to given types", "no suitable method", "method ", "constructor ", "does not override")


def normalize_build_failure(result: BuildResult, **kwargs: Any) -> NormalizedBuildFailure | None:
    """Functional convenience wrapper around :class:`BuildFailureNormalizer`."""

    return BuildFailureNormalizer().normalize(result, **kwargs)


__all__ = ["BuildFailureCategory", "BuildFailureNormalizer", "FailureClassification", "NormalizedBuildFailure", "normalize_build_failure"]
