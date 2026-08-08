"""Local pytest-compatible runner for L0.

This keeps the repo self-contained while the environment has no external
pytest installation. It supports the small test surface needed by L0.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import importlib.util
import inspect
import hashlib
import sys
from pathlib import Path
import traceback
from types import ModuleType
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"


@dataclass(frozen=True)
class TestCaseResult:
    name: str
    passed: bool
    error: str | None = None


def _prepare_sys_path() -> None:
    for candidate in (str(SRC_ROOT), str(PROJECT_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


def _load_module(path: Path) -> ModuleType:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    module_name = f"_pd_agent_test_{path.stem}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discover_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for base in paths:
        if base.is_file() and base.name.startswith("test_") and base.suffix == ".py":
            files.append(base)
            continue
        if base.is_dir():
            files.extend(sorted(p for p in base.rglob("test_*.py") if p.is_file()))
    return files


def _run_functions(module: ModuleType, file_path: Path) -> list[TestCaseResult]:
    results: list[TestCaseResult] = []
    for name, value in sorted(vars(module).items()):
        if name.startswith("test_") and callable(value):
            qualified = f"{file_path.name}::{name}"
            try:
                signature = inspect.signature(value)
                if signature.parameters:
                    raise TypeError(
                        f"{qualified} uses unsupported fixtures; keep L0 tests zero-arg"
                    )
                value()
            except Exception:
                results.append(
                    TestCaseResult(
                        name=qualified,
                        passed=False,
                        error=traceback.format_exc(),
                    )
                )
            else:
                results.append(TestCaseResult(name=qualified, passed=True))
    return results


def run(paths: list[str] | None = None) -> int:
    _prepare_sys_path()
    args = [Path(p) for p in (paths or ["tests"])]
    files = _discover_files(args)
    results: list[TestCaseResult] = []
    for file_path in files:
        module = _load_module(file_path)
        results.extend(_run_functions(module, file_path))

    if not results:
        print("no tests collected")
        return 0

    passed = 0
    failed = 0
    for result in results:
        if result.passed:
            passed += 1
            print(f". {result.name}")
        else:
            failed += 1
            print(f"F {result.name}")
            if result.error:
                print(result.error.rstrip())

    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pytest", add_help=True)
    parser.add_argument("paths", nargs="*", help="Test paths or files")
    parser.add_argument("-q", "--quiet", action="store_true", help="Ignored")
    parser.add_argument("--version", action="store_true", help="Show version")
    args = parser.parse_args(argv)

    if args.version:
        print("pytest 0.1-local")
        return 0

    return run(args.paths)


if __name__ == "__main__":
    raise SystemExit(main())
