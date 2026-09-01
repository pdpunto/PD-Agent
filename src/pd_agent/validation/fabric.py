"""Small deterministic guards for known Fabric source invariants."""

from __future__ import annotations

import re
from pathlib import Path

from pd_agent.core import ValidationResult, ValidationStage, ValidationStatus, ValidationViolation


_INLINE_BLOCK_PATTERN = re.compile(
    r"new\s+Block\s*\(\s*AbstractBlock\.Settings\.create\(\)(?P<settings>[^;)]*)\)",
    re.DOTALL,
)


class FabricBlockIdentityValidator:
    """Detect the unsafe inline Block construction used by the R23 failure.

    This intentionally checks one stable source shape rather than attempting to
    parse Java. Indirect settings objects remain valid because their identity
    cannot be established reliably without a Java parser.
    """

    def validate(self, project_root: Path, contract: object | None = None) -> ValidationResult:
        del contract
        root = Path(project_root).resolve(strict=True)
        violations: list[ValidationViolation] = []
        for path in sorted(root.glob("src/main/java/**/*.java")):
            text = path.read_text(encoding="utf-8")
            for match in _INLINE_BLOCK_PATTERN.finditer(text):
                if ".registryKey(" in match.group("settings"):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                relative = path.relative_to(root).as_posix()
                snippet = " ".join(match.group(0).split())
                violations.append(
                    ValidationViolation(
                        code="FABRIC_BLOCK_IDENTITY_MISSING",
                        requirement=relative,
                        observed={"path": relative, "line": line, "pattern": snippet},
                        expected="AbstractBlock.Settings.registryKey(...) before Block construction",
                        actual="inline Block construction without registryKey",
                        message=(
                            "Block construction lacks registry identity; configure "
                            "AbstractBlock.Settings.registryKey(...) before registration"
                        ),
                        phase="PRE_BUILD",
                        evidence_refs=(relative,),
                    )
                )
        return ValidationResult(
            stage=ValidationStage.PRE_BUILD,
            status=ValidationStatus.PASS if not violations else ValidationStatus.REPAIRABLE_FAIL,
            summary="Fabric block identity validation passed" if not violations else "Fabric block identity validation failed",
            violations=tuple(violations),
            evidence_refs=tuple(dict.fromkeys(ref for v in violations for ref in v.evidence_refs)),
        )


__all__ = ["FabricBlockIdentityValidator"]
