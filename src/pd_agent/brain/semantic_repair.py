"""Deterministic knowledge need derivation from semantic repair evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from pd_agent.core import ValidationViolation

from .models import KnowledgeEnvironment, KnowledgeNeed, KnowledgeType


@dataclass(frozen=True, slots=True)
class SemanticRepairDerivation:
    needs: tuple[KnowledgeNeed, ...]
    reasons: tuple[str, ...] = ()
    stage: str = "SEMANTIC_REPAIR"


_SYMBOL = re.compile(r"\b(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*\b")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_$]*")
_SENSITIVE = re.compile(r"(?:api[_ -]?key|secret|token|password|authorization|bearer)", re.I)
_STRUCTURAL_TERMS = frozenset({
    "actual", "before", "category", "changed", "class", "code", "error", "expected",
    "failure", "failed", "line", "missing", "observed", "path", "phase", "requirement",
    "source", "status", "value", "validation", "without",
    "src", "main", "java", "example",
})


@dataclass(frozen=True, slots=True)
class SemanticRepairKnowledgeNeedDeriver:
    max_needs: int = 4

    def __post_init__(self) -> None:
        if not 1 <= self.max_needs <= 4:
            raise ValueError("max_needs must be between 1 and 4")

    def derive(self, violation: ValidationViolation, environment: KnowledgeEnvironment) -> SemanticRepairDerivation:
        if not isinstance(violation, ValidationViolation):
            raise TypeError("violation must be ValidationViolation")
        signal = self._safe_signal(violation)
        lowered = signal.casefold()
        if not signal:
            return SemanticRepairDerivation(())
        if "persistence" in lowered or "persisted_state" in lowered:
            mapping = (("persistence", (KnowledgeType.PATTERN, KnowledgeType.CONCEPT,
                                         KnowledgeType.DIAGNOSTIC, KnowledgeType.CAPABILITY)),)
        elif "runtime_target_startup_failure" in lowered or "block id not set" in lowered:
            mapping = (("runtime", (KnowledgeType.DIAGNOSTIC, KnowledgeType.PATTERN,
                                     KnowledgeType.SYMBOL, KnowledgeType.API)),)
        elif any(marker in lowered for marker in ("signature", "method", "overload", "fabric api")):
            mapping = (("api", (KnowledgeType.API, KnowledgeType.SYMBOL, KnowledgeType.PATTERN)),)
        elif any(marker in lowered for marker in ("mapping", "changed", "removed")):
            mapping = (("mapping", (KnowledgeType.SYMBOL, KnowledgeType.API, KnowledgeType.VERSION_CHANGE)),)
        elif "symbol" in lowered or "class" in lowered or "cannot find" in lowered:
            mapping = (("symbol", (KnowledgeType.SYMBOL, KnowledgeType.API, KnowledgeType.VERSION_CHANGE)),)
        elif any(marker in lowered for marker in ("registry", "registration", "block")):
            mapping = (("domain", (KnowledgeType.DIAGNOSTIC, KnowledgeType.PATTERN,
                                     KnowledgeType.SYMBOL, KnowledgeType.API)),)
        elif any(marker in lowered for marker in ("build", "diagnostic", "error", "failure")):
            mapping = (("diagnostic", (KnowledgeType.DIAGNOSTIC, KnowledgeType.API)),)
        else:
            return SemanticRepairDerivation(())

        needs: list[KnowledgeNeed] = []
        reasons: list[str] = []
        symbols = tuple(dict.fromkeys(_SYMBOL.findall(signal)))
        failure_terms = self._failure_terms(violation)
        failure_query = failure_terms[0] if failure_terms else "diagnostic"
        failure_hints = self._failure_hints(violation, failure_terms)
        for label, types in mapping:
            for kind in types:
                query = symbols[0] if symbols and kind in {KnowledgeType.SYMBOL, KnowledgeType.API} else label
                if kind not in {KnowledgeType.SYMBOL, KnowledgeType.API}:
                    query = failure_query
                needs.append(KnowledgeNeed(
                    id=f"semantic-repair:{violation.code}:{kind.value.casefold()}:{query.casefold()}",
                    type=kind, query=query, environment=environment,
                    hints=(violation.code, *failure_hints), version_sensitive=True,
                ))
                reasons.append(f"{violation.code}: {label}")
                if len(needs) >= self.max_needs:
                    return SemanticRepairDerivation(tuple(needs), tuple(reasons))
        return SemanticRepairDerivation(tuple(needs), tuple(reasons))

    @staticmethod
    def _safe_signal(violation: ValidationViolation) -> str:
        parts = [violation.code, violation.phase or "", violation.requirement, violation.message]
        parts.extend(str(value) for value in (violation.observed, violation.expected, violation.actual))
        text = " ".join(parts)
        text = _SENSITIVE.sub("redacted", text)
        return re.sub(r"[\r\n\t]+", " ", text)[:2000]

    @staticmethod
    def _failure_terms(violation: ValidationViolation) -> tuple[str, ...]:
        """Extract stable domain anchors without encoding a provider-specific rule."""
        parts = (str(violation.actual), str(violation.expected), violation.message,
                 str(violation.observed), violation.requirement, violation.code)
        counts: dict[str, int] = {}
        domain_counts: dict[str, int] = {}
        order: dict[str, int] = {}
        for position, token in enumerate(_TOKEN.findall(" ".join(parts))):
            normalized = token.casefold()
            if normalized in _STRUCTURAL_TERMS or len(normalized) < 3:
                continue
            normalized = _SENSITIVE.sub("redacted", normalized)
            if normalized == "redacted":
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
            if token[:1].isupper():
                domain_counts[normalized] = domain_counts.get(normalized, 0) + 1
            order.setdefault(normalized, position)
        return tuple(sorted(
            counts,
            key=lambda token: (-domain_counts.get(token, 0), -counts[token], order[token], token),
        )[:8])

    @staticmethod
    def _failure_hints(violation: ValidationViolation, terms: tuple[str, ...]) -> tuple[str, ...]:
        """Keep the structured failure identity attached to every derived need."""
        refs = ",".join(violation.evidence_refs) or "none"
        phase = violation.phase or "unknown"
        return (
            f"failure_code={violation.code}",
            f"phase={phase}",
            f"requirement={violation.requirement}",
            f"message={SemanticRepairKnowledgeNeedDeriver._safe_fragment(violation.message)}",
            f"observed={SemanticRepairKnowledgeNeedDeriver._safe_fragment(violation.observed)}",
            f"expected={SemanticRepairKnowledgeNeedDeriver._safe_fragment(violation.expected)}",
            f"actual={SemanticRepairKnowledgeNeedDeriver._safe_fragment(violation.actual)}",
            f"evidence_refs={refs}",
            f"failure_terms={','.join(terms) or 'none'}",
        )

    @staticmethod
    def _safe_fragment(value: Any) -> str:
        text = _SENSITIVE.sub("redacted", str(value))
        return re.sub(r"[\r\n\t]+", " ", text)[:500]
