from __future__ import annotations

from datetime import datetime, timezone

from pd_agent.build import BuildFailureCategory, BuildFailureNormalizer, FailureClassification
from pd_agent.core import BuildResult


def _failure(stderr: str, *, exit_code: int = 1) -> BuildResult:
    return BuildResult(attempt=1, command_display="./gradlew build", cwd=None, started_at=datetime.now(timezone.utc), duration_seconds=1.0, exit_code=exit_code, stdout_log="", stderr_log=stderr)


def test_success_has_no_normalized_failure() -> None:
    assert BuildFailureNormalizer().normalize(_failure("", exit_code=0)) is None


def test_missing_symbol_is_repairable_and_bounded() -> None:
    result = BuildFailureNormalizer().normalize(_failure("src/Main.java:12: error: cannot find symbol\n  symbol: class MarbleLantern\n"), source_revision="a" * 64, build_attempt_id="b1", evidence_refs=("builds/1.stderr",), requirement_ids=("r1",))
    assert result is not None
    assert result.category is BuildFailureCategory.MISSING_SYMBOL
    assert result.classification is FailureClassification.REPAIRABLE_FAIL
    assert result.symbol_hints == ("MarbleLantern",)
    assert result.file_hints == ("src/Main.java",)
    assert "cannot find symbol" not in result.fingerprint
    assert "builds/1.stderr" in result.evidence_refs
    assert len(result.to_dict()["concise_diagnostic"]) < len("src/Main.java:12: error: cannot find symbol\n  symbol: class MarbleLantern\n")


def test_compilation_and_signature_patterns() -> None:
    normalizer = BuildFailureNormalizer()
    generic = normalizer.normalize(_failure("Execution failed: compilation failed"))
    signature = normalizer.normalize(_failure("method add cannot be applied to given types"))
    api = normalizer.normalize(_failure("Fabric API method does not override"))
    assert generic and generic.category is BuildFailureCategory.COMPILATION_ERROR
    assert signature and signature.category is BuildFailureCategory.SIGNATURE_OR_API_MISMATCH
    assert api and api.category is BuildFailureCategory.SIGNATURE_OR_API_MISMATCH


def test_dependency_timeout_environment_and_unknown_are_blocked() -> None:
    normalizer = BuildFailureNormalizer()
    dependency = normalizer.normalize(_failure("Could not resolve dependency net.fabricmc:fabric-api"))
    timeout = normalizer.normalize(_failure("process timed out"))
    environment = normalizer.normalize(_failure("Access is denied: file lock"))
    unknown = normalizer.normalize(_failure("unexpected non-zero exit"))
    assert dependency and dependency.category is BuildFailureCategory.DEPENDENCY_ERROR and dependency.classification is FailureClassification.BLOCKED
    assert timeout and timeout.category is BuildFailureCategory.TIMEOUT
    assert environment and environment.category is BuildFailureCategory.ENVIRONMENT_OR_INFRASTRUCTURE
    assert unknown and unknown.category is BuildFailureCategory.UNKNOWN


def test_fingerprint_ignores_noise_but_changes_material_diagnostics() -> None:
    normalizer = BuildFailureNormalizer()
    first = normalizer.normalize(_failure("2026-08-27T10:00:00Z src/Main.java:12: cannot find symbol symbol: class Foo"))
    noisy = normalizer.normalize(_failure("2027-01-01T20:30:00Z src/Main.java:12: cannot find symbol symbol: class Foo"))
    changed = normalizer.normalize(_failure("2026-08-27T10:00:00Z src/Main.java:12: cannot find symbol symbol: class Bar"))
    assert first and noisy and changed
    assert first.fingerprint == noisy.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_requirement_correlation_is_explicit_only_and_serializable() -> None:
    result = BuildFailureNormalizer().normalize(_failure("cannot find symbol"), requirement_ids=(), source_revision="a" * 64, build_attempt_id="b1")
    assert result and result.requirement_ids == ()
    restored = result.to_violation().to_dict()
    assert restored["phase"] == "BUILD"
    assert "stderr" not in restored
    assert result.to_failure_fact(failure_id="f1").requirement_ids == ()
