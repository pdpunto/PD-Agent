"""Minimal build backend for PD Agent L0.

This backend keeps the project self-contained while the environment has no
packaging backend installed. It builds a simple pure-Python wheel and a basic
sdist from the source tree.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from dataclasses import dataclass
import csv
import hashlib
from io import StringIO
from pathlib import Path
import tarfile
import zipfile
from typing import Iterable


NAME = "pd-agent"
VERSION = "0.1.0"
DIST_NAME = NAME.replace("-", "_")
WHEEL_TAG = "py3-none-any"
DIST_INFO = f"{DIST_NAME}-{VERSION}.dist-info"
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"


@dataclass(frozen=True)
class FileEntry:
    source: Path
    archive: str


def _metadata() -> str:
    return "\n".join(
        [
            "Metadata-Version: 2.1",
            f"Name: {NAME}",
            f"Version: {VERSION}",
            "Summary: PD Agent foundation package",
            "",
        ]
    )


def _wheel() -> str:
    return "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: pd-agent-build-backend",
            "Root-Is-Purelib: true",
            f"Tag: {WHEEL_TAG}",
            "",
        ]
    )


def _entry_points() -> str:
    return "\n".join(
        [
            "[console_scripts]",
            "pd-agent = pd_agent.cli:main",
            "",
        ]
    )


def _hash_bytes(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _iter_package_files() -> Iterable[FileEntry]:
    package_root = SRC_ROOT / "pd_agent"
    for path in sorted(package_root.rglob("*")):
        if path.is_file():
            yield FileEntry(path, f"pd_agent/{path.relative_to(package_root).as_posix()}")


def _record_rows(entries: list[tuple[str, bytes]]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for name, data in entries:
        writer.writerow([name, _hash_bytes(data), str(len(data))])
    writer.writerow([f"{DIST_INFO}/RECORD", "", ""])
    return buffer.getvalue()


def _write_zip_with_records(target: Path, files: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
        zf.writestr(f"{DIST_INFO}/RECORD", _record_rows(files).encode("utf-8"))


def get_requires_for_build_wheel(config_settings=None):  # noqa: D401
    return []


def get_requires_for_build_sdist(config_settings=None):  # noqa: D401
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    dist_info = Path(metadata_directory) / DIST_INFO
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel(), encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(_entry_points(), encoding="utf-8")
    return DIST_INFO


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    wheel_path = Path(wheel_directory) / f"{DIST_NAME}-{VERSION}-{WHEEL_TAG}.whl"
    files: list[tuple[str, bytes]] = []
    for entry in _iter_package_files():
        files.append((entry.archive, entry.source.read_bytes()))
    files.append((f"{DIST_INFO}/METADATA", _metadata().encode("utf-8")))
    files.append((f"{DIST_INFO}/WHEEL", _wheel().encode("utf-8")))
    files.append((f"{DIST_INFO}/entry_points.txt", _entry_points().encode("utf-8")))
    _write_zip_with_records(wheel_path, files)
    return wheel_path.name


def build_sdist(sdist_directory, config_settings=None):
    sdist_path = Path(sdist_directory) / f"{DIST_NAME}-{VERSION}.tar.gz"
    root = f"{DIST_NAME}-{VERSION}"
    with tarfile.open(sdist_path, "w:gz") as tf:
        for rel in [
            "pyproject.toml",
            "README.md",
            "pd_agent_build_backend.py",
            "pytest.py",
            "sitecustomize.py",
        ]:
            path = PROJECT_ROOT / rel
            if path.exists():
                tf.add(path, arcname=f"{root}/{rel}")
        for rel in [
            "pd_agent/__init__.py",
            "pd_agent/__main__.py",
        ]:
            path = PROJECT_ROOT / rel
            if path.exists():
                tf.add(path, arcname=f"{root}/{rel}")
        for entry in _iter_package_files():
            tf.add(entry.source, arcname=f"{root}/src/{entry.archive}")
        for path in sorted((PROJECT_ROOT / "tests").rglob("*")):
            if path.is_file():
                tf.add(path, arcname=f"{root}/{path.relative_to(PROJECT_ROOT).as_posix()}")
    return sdist_path.name
