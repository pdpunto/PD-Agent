"""Controlled Gradle Wrapper build runner."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
from typing import Any, Mapping

from pd_agent.core import BuildError, BuildResult, ExecutionLimits, LimitReachedError, RunState
from pd_agent.project import ProjectInspectionStatus, ProjectSnapshot
from pd_agent.reporting import RunStorage, RunEvent, RunEventType


BUILD_TASK = "build"
@dataclass(frozen=True, slots=True)
class BuildInvocation:
    """Closed build invocation metadata."""

    project_root: Path
    cwd: Path
    executable: Path
    argv: tuple[str, ...]
    command_display: str
    shell: bool = False
    target_subproject: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "cwd": str(self.cwd),
            "executable": str(self.executable),
            "argv": list(self.argv),
            "command_display": self.command_display,
            "shell": self.shell,
            "target_subproject": str(self.target_subproject)
            if self.target_subproject is not None
            else None,
        }


@dataclass(frozen=True, slots=True)
class BuildLogPaths:
    """Persisted build logs."""

    stdout: Path
    stderr: Path


class _WindowsJobController:
    """Terminate process tree through a Windows job object."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectExtendedLimitInformation = 9

    def __init__(self) -> None:
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.job = self.kernel32.CreateJobObjectW(None, None)
        if not self.job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        self._configure_job()

    def _configure_job(self) -> None:
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        size = ctypes.sizeof(info)
        result = self.kernel32.SetInformationJobObject(
            self.job,
            self.JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            size,
        )
        if not result:
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, process: subprocess.Popen[str]) -> None:
        if not self.kernel32.AssignProcessToJobObject(self.job, wintypes.HANDLE(process._handle)):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def close(self) -> None:
        if self.job:
            self.kernel32.CloseHandle(self.job)
            self.job = None

    def __enter__(self) -> "_WindowsJobController":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class GradleBuildRunner:
    """Execute controlled Gradle Wrapper builds."""

    def __init__(
        self,
        reporting: RunStorage | None = None,
        platform_override: str | None = None,
    ) -> None:
        self.reporting = reporting
        self.platform_override = platform_override

    def build_invocation(
        self,
        project_snapshot: ProjectSnapshot,
    ) -> BuildInvocation:
        self._validate_snapshot(project_snapshot)
        wrapper = self._resolve_wrapper(project_snapshot)
        target_task = self._target_task(project_snapshot)
        cwd = project_snapshot.project_root.resolve(strict=True)
        wrapper_arg = self._wrapper_arg(wrapper)
        argv = (wrapper_arg, target_task)
        display = " ".join(shlex.quote(part) for part in argv)
        return BuildInvocation(
            project_root=project_snapshot.project_root,
            cwd=cwd,
            executable=wrapper,
            argv=argv,
            command_display=display,
            shell=False,
            target_subproject=project_snapshot.target_subproject,
        )

    def run(
        self,
        project_snapshot: ProjectSnapshot,
        run_state: RunState,
        limits: ExecutionLimits,
    ) -> BuildResult:
        self._validate_snapshot(project_snapshot)
        self._validate_attempt(run_state, limits)
        invocation = self.build_invocation(project_snapshot)
        attempt = run_state.build_attempt_count + 1
        run_state.record_build_attempt()
        self._emit(
            run_state.run_id,
            RunEventType.BUILD_STARTED,
            {
                "attempt": attempt,
                "cwd": self._relative_cwd(invocation.cwd, project_snapshot.project_root),
                "command_display": invocation.command_display,
                "shell": invocation.shell,
                "target_subproject": str(project_snapshot.target_subproject)
                if project_snapshot.target_subproject is not None
                else None,
            },
        )
        started_at = datetime.now(timezone.utc)
        stdout_text, stderr_text, exit_code, timed_out = self._run_process(invocation, limits)
        duration_seconds = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0.0)
        result = BuildResult(
            attempt=attempt,
            command_display=invocation.command_display,
            cwd=invocation.cwd,
            started_at=started_at,
            duration_seconds=duration_seconds,
            exit_code=exit_code,
            stdout_log=stdout_text,
            stderr_log=stderr_text,
        )
        run_state.record_build_result(result)
        if timed_out:
            run_state.last_error = f"build timeout after {limits.process_timeout_seconds}s"
            run_state.termination_reason = "build timeout"
        elif result.success:
            run_state.last_error = None
        else:
            run_state.last_error = stderr_text or stdout_text or f"build failed with exit_code {exit_code}"

        log_paths = self._persist_logs(run_state.run_id, attempt, stdout_text, stderr_text)
        self._emit(
            run_state.run_id,
            RunEventType.BUILD_FINISHED,
            {
                "attempt": attempt,
                "cwd": self._relative_cwd(invocation.cwd, project_snapshot.project_root),
                "command_display": invocation.command_display,
                "exit_code": exit_code,
                "success": result.success,
                "duration_seconds": duration_seconds,
                "timeout": timed_out,
                "stdout_log_path": str(log_paths.stdout),
                "stderr_log_path": str(log_paths.stderr),
                "stdout_bytes": len(stdout_text.encode("utf-8")),
                "stderr_bytes": len(stderr_text.encode("utf-8")),
            },
        )
        return result

    def _validate_snapshot(self, project_snapshot: ProjectSnapshot) -> None:
        if project_snapshot.status == ProjectInspectionStatus.BLOCKED:
            raise BuildError("project inspection blocked")
        if not project_snapshot.wrapper.present:
            raise BuildError("Gradle Wrapper absent")
        if not project_snapshot.project_root.exists():
            raise BuildError("project_root missing")

    def _validate_attempt(self, run_state: RunState, limits: ExecutionLimits) -> None:
        if run_state.build_attempt_count >= limits.max_build_attempts:
            raise LimitReachedError("max_build_attempts reached")

    def _target_task(self, project_snapshot: ProjectSnapshot) -> str:
        target = project_snapshot.target_subproject
        if target is None or target == project_snapshot.project_root:
            return BUILD_TASK
        relative = target.relative_to(project_snapshot.project_root).as_posix()
        return f":{relative}:{BUILD_TASK}"

    def _resolve_wrapper(self, project_snapshot: ProjectSnapshot) -> Path:
        if self._is_windows():
            candidates = [path for path in project_snapshot.wrapper.scripts if path.name.lower() == "gradlew.bat"]
        else:
            candidates = [path for path in project_snapshot.wrapper.scripts if path.name == "gradlew"]
        if not candidates:
            raise BuildError("Gradle Wrapper absent for current platform")
        wrapper = candidates[0].resolve(strict=True)
        return wrapper

    def _wrapper_arg(self, wrapper: Path) -> str:
        if self._is_windows():
            return wrapper.name
        return f"./{wrapper.name}"

    def _run_process(
        self,
        invocation: BuildInvocation,
        limits: ExecutionLimits,
    ) -> tuple[str, str, int, bool]:
        env = os.environ.copy()
        env.setdefault("CI", "true")
        creationflags = 0
        preexec_fn = None
        job: _WindowsJobController | None = None

        if self._is_windows():
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            preexec_fn = os.setsid

        proc = subprocess.Popen(
            list(invocation.argv),
            executable=str(invocation.executable),
            cwd=str(invocation.cwd),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
        )

        try:
            if self._is_windows():
                with _WindowsJobController() as job:
                    job.assign(proc)
                    stdout_text, stderr_text = proc.communicate(timeout=limits.process_timeout_seconds)
            else:
                stdout_text, stderr_text = proc.communicate(timeout=limits.process_timeout_seconds)
            return stdout_text or "", stderr_text or "", int(proc.returncode or 0), False
        except subprocess.TimeoutExpired:
            self._terminate_tree(proc)
            stdout_text, stderr_text = proc.communicate()
            return stdout_text or "", stderr_text or "", -1, True
        finally:
            if job is not None:
                job.close()

    def _terminate_tree(self, proc: subprocess.Popen[str]) -> None:
        if self._is_windows():
            try:
                proc.terminate()
            finally:
                time.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            deadline = time.time() + 1.0
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def _persist_logs(self, run_id: str, attempt: int, stdout_text: str, stderr_text: str) -> BuildLogPaths:
        if self.reporting is None:
            stdout_path = Path("builds") / f"{attempt:03d}.stdout.log"
            stderr_path = Path("builds") / f"{attempt:03d}.stderr.log"
            return BuildLogPaths(stdout=stdout_path, stderr=stderr_path)
        paths = self.reporting.paths_for(run_id)
        stdout_path = paths.builds_dir / f"{attempt:03d}.stdout.log"
        stderr_path = paths.builds_dir / f"{attempt:03d}.stderr.log"
        stdout_path.write_text(stdout_text, encoding="utf-8", newline="\n")
        stderr_path.write_text(stderr_text, encoding="utf-8", newline="\n")
        return BuildLogPaths(stdout=stdout_path, stderr=stderr_path)

    def _emit(self, run_id: str, event_type: RunEventType, payload: Mapping[str, Any]) -> None:
        if self.reporting is None:
            return
        self.reporting.append_event(
            RunEvent(
                run_id=run_id,
                event_type=event_type,
                payload=dict(payload),
            )
        )

    def _relative_cwd(self, cwd: Path, project_root: Path) -> str:
        try:
            return str(cwd.relative_to(project_root))
        except ValueError:
            return str(cwd)

    def _is_windows(self) -> bool:
        if self.platform_override == "windows":
            return True
        if self.platform_override == "posix":
            return False
        return os.name == "nt"
