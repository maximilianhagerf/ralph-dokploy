"""Tests for job_manager.py: state machine, subprocess lifecycle, callbacks."""

import io
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from job_manager import JobManager, JobState


def _mock_proc(lines: list[str], returncode: int = 0) -> MagicMock:
    """Popen mock that yields lines from stdout and exits with returncode."""
    content = "\n".join(lines) + ("\n" if lines else "")
    proc = MagicMock()
    proc.stdout = io.StringIO(content)
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    proc.pid = 99999
    return proc


def _blocking_proc() -> tuple[MagicMock, threading.Event]:
    """Popen mock whose stdout blocks until released."""
    release = threading.Event()

    class _BlockingIO:
        def readline(self):
            release.wait()
            return ""  # EOF once released

    proc = MagicMock()
    proc.stdout = _BlockingIO()
    proc.poll.return_value = None
    proc.wait.return_value = 0
    proc.pid = 99999
    return proc, release


@patch("job_manager.shutil.rmtree")
@patch("os.makedirs")
@patch("os.killpg")
@patch("os.getpgid", return_value=99999)
@patch("job_manager.subprocess.Popen")
@patch("job_manager.subprocess.run")
def test_start_transitions_to_running(
    mock_run, mock_popen, mock_getpgid, mock_killpg, mock_makedirs, mock_rmtree
):
    mock_run.return_value = MagicMock(returncode=0)
    proc, release = _blocking_proc()
    mock_popen.return_value = proc

    manager = JobManager()
    started = threading.Event()

    original_reader = manager._reader_loop

    def patched_reader():
        started.set()
        original_reader()

    manager._reader_loop = patched_reader

    err = manager.start("https://github.com/owner/repo.git", "1", "main", "feat", lambda *_: None)
    started.wait(timeout=1)

    assert err is None
    assert manager.status()["state"] == JobState.RUNNING.value

    release.set()


@patch("job_manager.shutil.rmtree")
@patch("os.makedirs")
@patch("os.killpg")
@patch("os.getpgid", return_value=99999)
@patch("job_manager.subprocess.Popen")
@patch("job_manager.subprocess.run")
def test_stop_while_running_transitions_to_stopping(
    mock_run, mock_popen, mock_getpgid, mock_killpg, mock_makedirs, mock_rmtree
):
    mock_run.return_value = MagicMock(returncode=0)
    proc, release = _blocking_proc()
    mock_popen.return_value = proc

    manager = JobManager()
    started = threading.Event()

    # Wrap on_event to signal when reader thread is alive
    original_reader = manager._reader_loop

    def patched_reader():
        started.set()
        original_reader()

    manager._reader_loop = patched_reader

    manager.start("https://github.com/owner/repo.git", "1", "main", "feat", lambda *_: None)
    started.wait(timeout=1)

    manager.stop()
    assert manager.status()["state"] == JobState.STOPPING.value

    release.set()  # unblock reader so daemon thread can exit cleanly


@patch("job_manager.shutil.rmtree")
@patch("os.makedirs")
@patch("os.killpg")
@patch("os.getpgid", return_value=99999)
@patch("job_manager.subprocess.Popen")
@patch("job_manager.subprocess.run")
def test_force_stop_transitions_to_stopped_immediately(
    mock_run, mock_popen, mock_getpgid, mock_killpg, mock_makedirs, mock_rmtree
):
    mock_run.return_value = MagicMock(returncode=0)
    proc, release = _blocking_proc()
    proc.wait.return_value = 0
    mock_popen.return_value = proc

    manager = JobManager()
    started = threading.Event()

    original_reader = manager._reader_loop

    def patched_reader():
        started.set()
        original_reader()

    manager._reader_loop = patched_reader

    manager.start("https://github.com/owner/repo.git", "1", "main", "feat", lambda *_: None)
    started.wait(timeout=1)

    manager.force_stop()

    assert manager.status()["state"] == JobState.STOPPED.value

    release.set()


@patch("job_manager.shutil.rmtree")
@patch("os.makedirs")
@patch("os.killpg")
@patch("os.getpgid", return_value=99999)
@patch("job_manager.subprocess.Popen")
@patch("job_manager.subprocess.run")
def test_start_while_running_returns_error_no_second_spawn(
    mock_run, mock_popen, mock_getpgid, mock_killpg, mock_makedirs, mock_rmtree
):
    mock_run.return_value = MagicMock(returncode=0)
    proc, release = _blocking_proc()
    mock_popen.return_value = proc

    manager = JobManager()
    started = threading.Event()

    original_reader = manager._reader_loop

    def patched_reader():
        started.set()
        original_reader()

    manager._reader_loop = patched_reader

    err1 = manager.start("https://github.com/owner/repo.git", "1", "main", "feat", lambda *_: None)
    started.wait(timeout=1)

    err2 = manager.start("https://github.com/owner/repo.git", "2", "main", "feat2", lambda *_: None)

    assert err1 is None
    assert err2 is not None
    assert "RUNNING" in err2
    assert mock_popen.call_count == 1

    release.set()


@patch("job_manager.shutil.rmtree")
@patch("os.makedirs")
@patch("os.getpgid", return_value=99999)
@patch("job_manager.subprocess.Popen")
@patch("job_manager.subprocess.run")
def test_job_completion_transitions_to_idle_and_fires_complete(
    mock_run, mock_popen, mock_getpgid, mock_makedirs, mock_rmtree
):
    mock_run.return_value = MagicMock(returncode=0)
    mock_popen.return_value = _mock_proc(
        ["RALPH:ISSUE:5:Fix the bug", "working...", "RALPH:COMPLETE"],
        returncode=0,
    )

    events: list[tuple[str, dict]] = []
    done = threading.Event()

    def on_event(event_type, payload):
        events.append((event_type, payload))
        if event_type == "complete":
            done.set()

    manager = JobManager()
    err = manager.start("https://github.com/owner/repo.git", "1", "main", "feat", on_event)

    assert err is None
    done.wait(timeout=2)
    time.sleep(0.05)  # let _finish() update state

    assert manager.status()["state"] == JobState.IDLE.value
    complete_events = [e for e in events if e[0] == "complete"]
    assert len(complete_events) == 1
