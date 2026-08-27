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
_SENSITIVE = re.compile(r"(?:api[_ -]?key|secret|token|password|authorization|bearer)", re.I)


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
        if "persistence" in lowered or "persisted_state" in lowered or "runtime" in lowered:
            mapping = (("persistence", (KnowledgeType.PATTERN, KnowledgeType.CONCEPT,
                                         KnowledgeType.DIAGNOSTIC, KnowledgeType.CAPABILITY)),)
        elif any(marker in lowered for marker in ("signature", "method", "overload", "fabric api")):
            mapping = (("api", (KnowledgeType.API, KnowledgeType.SYMBOL, KnowledgeType.PATTERN)),)
        elif any(marker in lowered for marker in ("mapping", "changed", "removed")):
            mapping = (("mapping", (KnowledgeType.SYMBOL, KnowledgeType.API, KnowledgeType.VERSION_CHANGE)),)
        elif "symbol" in lowered or "class" in lowered or "cannot find" in lowered:
            mapping = (("symbol", (KnowledgeType.SYMBOL, KnowledgeType.API, KnowledgeType.VERSION_CHANGE)),)
        elif any(marker in lowered for marker in ("build", "diagnostic", "error", "failure")):
            mapping = (("diagnostic", (KnowledgeType.DIAGNOSTIC, KnowledgeType.API)),)
        else:
            return SemanticRepairDerivation(())

        needs: list[KnowledgeNeed] = []
        reasons: list[str] = []
        symbols = tuple(dict.fromkeys(_SYMBOL.findall(signal)))
        for label, types in mapping:
            for kind in types:
                query = symbols[0] if symbols and kind in {KnowledgeType.SYMBOL, KnowledgeType.API} else label
                needs.append(KnowledgeNeed(
                    id=f"semantic-repair:{violation.code}:{kind.value.casefold()}:{query.casefold()}",
                    type=kind, query=query, environment=environment,
                    hints=(violation.code,), version_sensitive=True,
                ))
                reasons.append(f"{violation.code}: {label}")
                if len(needs) >= self.max_needs:
                    return SemanticRepairDerivation(tuple(needs), tuple(reasons))
        return SemanticRepairDerivation(tuple(needs), tuple(reasons))

    @staticmethod
    def _safe_signal(violation: ValidationViolation) -> str:
        parts = [violation.code, violation.requirement, violation.message]
        parts.extend(str(value) for value in (violation.observed, violation.expected, violation.actual))
        text = " ".join(parts)
        text = _SENSITIVE.sub("redacted", text)
        return re.sub(r"[\r\n\t]+", " ", text)[:2000]
