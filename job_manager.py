"""job_manager.py — subprocess lifecycle and state machine for Ralph jobs.

Public interface: start(), stop(), force_stop(), status().
Internals use a single job slot; swap for a queue later without changing the interface.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

_RALPH_SH_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "scripts", "ralph.sh"
)


class JobState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


@dataclass
class _Job:
    job_id: str
    workspace: str
    proc: subprocess.Popen
    on_event: Callable[[str, Dict[str, Any]], None]
    current_issue: Optional[Dict[str, str]] = field(default=None)


class JobManager:
    """Owns all subprocess management for Ralph jobs."""

    def __init__(
        self,
        ralph_sh: str = _RALPH_SH_DEFAULT,
        workspace_root: str = "/workspace",
    ) -> None:
        self._ralph_sh = ralph_sh
        self._workspace_root = workspace_root
        self._lock = threading.Lock()
        self._state = JobState.IDLE
        self._job: Optional[_Job] = None
        self._stop_requested = threading.Event()

    # ── public interface ──────────────────────────────────────────────────

    def start(
        self,
        repo: str,
        prd_issue: str | int,
        base_branch: str,
        new_branch: str,
        on_event: Callable[[str, Dict[str, Any]], None],
    ) -> Optional[str]:
        """Start a Ralph job.

        Clones *repo* to /workspace/<uuid>, spawns ralph.sh, reads stdout,
        and fires on_event callbacks on RALPH: lines.

        Returns an error string if called while not IDLE (does not raise).
        Returns None on success.
        """
        with self._lock:
            if self._state != JobState.IDLE:
                return f"Cannot start: job is {self._state.value}"
            job_id = str(uuid.uuid4())

        workspace = os.path.join(self._workspace_root, job_id)

        try:
            os.makedirs(workspace, exist_ok=True)
            clone_url = repo
            github_token = os.environ.get("GITHUB_TOKEN")
            if github_token and clone_url.startswith("https://github.com/"):
                clone_url = clone_url.replace(
                    "https://github.com/",
                    f"https://x-access-token:{github_token}@github.com/",
                )
            subprocess.run(
                ["git", "clone", clone_url, workspace],
                check=True,
                capture_output=True,
            )
        except Exception as exc:
            shutil.rmtree(workspace, ignore_errors=True)
            return str(exc)

        with self._lock:
            if self._state != JobState.IDLE:
                shutil.rmtree(workspace, ignore_errors=True)
                return f"Cannot start: job is {self._state.value}"

            try:
                proc = subprocess.Popen(
                    [self._ralph_sh, str(prd_issue), "20", base_branch, new_branch],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=workspace,
                    text=True,
                    start_new_session=True,
                )
            except Exception as exc:
                shutil.rmtree(workspace, ignore_errors=True)
                return str(exc)

            self._stop_requested.clear()
            self._job = _Job(job_id, workspace, proc, on_event)
            self._state = JobState.RUNNING

        thread = threading.Thread(target=self._reader_loop, daemon=True)
        thread.start()
        return None

    def stop(self) -> None:
        """Graceful stop: RUNNING → STOPPING.

        Sets a flag; the reader loop sends SIGTERM after the current
        ralph-once.sh invocation finishes (between readline() calls).
        """
        with self._lock:
            if self._state != JobState.RUNNING:
                return
            self._state = JobState.STOPPING
        self._stop_requested.set()

    def force_stop(self) -> None:
        """Immediate stop: any → STOPPED.

        Sends SIGTERM to the subprocess tree; escalates to SIGKILL after 5 s.
        """
        with self._lock:
            self._state = JobState.STOPPED
            current_job = self._job

        self._stop_requested.set()

        if current_job is None or current_job.proc.poll() is not None:
            return

        try:
            os.killpg(os.getpgid(current_job.proc.pid), signal.SIGTERM)
        except Exception:
            pass

        try:
            current_job.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(current_job.proc.pid), signal.SIGKILL)
            except Exception:
                pass

    def status(self) -> Dict[str, Any]:
        """Return current state and active issue info.

        Returns: {"state": str, "issue": {"number": str, "title": str} | None}
        """
        with self._lock:
            return {
                "state": self._state.value,
                "issue": (
                    dict(self._job.current_issue)
                    if self._job and self._job.current_issue
                    else None
                ),
            }

    # ── internals ────────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        with self._lock:
            job = self._job
        if job is None:
            return

        try:
            while True:
                line = job.proc.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\n")

                if line.startswith("RALPH:ISSUE:"):
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        number, title = parts[2], parts[3]
                        with self._lock:
                            job.current_issue = {"number": number, "title": title}
                        job.on_event("issue", {"number": number, "title": title})

                elif line.startswith("RALPH:COMPLETE"):
                    pr_url = self._peek_pr_url(job.proc)
                    job.on_event("complete", {"pr_url": pr_url})

                elif line.startswith("RALPH:ERROR:"):
                    message = line[len("RALPH:ERROR:"):]
                    job.on_event("error", {"message": message})

                # Check stop flag between readline() calls (between iterations).
                # Since ralph-once.sh output is captured in a subshell by ralph.sh,
                # all iteration output appears in a burst — the flag is checked after
                # each line, so SIGTERM lands after the current iteration's output.
                if self._stop_requested.is_set():
                    self._send_sigterm(job.proc)
                    break

        finally:
            exit_code = job.proc.wait()
            self._finish(job, exit_code)

    def _peek_pr_url(self, proc: subprocess.Popen) -> str:
        """Read ahead up to 5 lines to capture the gh pr create URL."""
        for _ in range(5):
            try:
                line = proc.stdout.readline()
            except Exception:
                break
            if not line:
                break
            stripped = line.strip()
            if stripped.startswith("https://github.com") and "/pull/" in stripped:
                return stripped
        return ""

    def _send_sigterm(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass

    def _finish(self, job: _Job, exit_code: int) -> None:
        shutil.rmtree(job.workspace, ignore_errors=True)
        with self._lock:
            if self._job is not job:
                return
            self._job = None
            if self._state == JobState.STOPPED:
                # force_stop() already set this; leave it
                return
            if self._state == JobState.STOPPING:
                # Graceful stop completed cleanly
                self._state = JobState.IDLE
            elif exit_code == 0:
                self._state = JobState.IDLE
            else:
                self._state = JobState.STOPPED


# ── module-level singleton ─────────────────────────────────────────────────
# bot.py uses: import job_manager; job_manager.start(...)

_manager = JobManager()

start = _manager.start
stop = _manager.stop
force_stop = _manager.force_stop
status = _manager.status
