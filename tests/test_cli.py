from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def _run(tmp_path: Path, child_code: str, *, timeout: str = "5"):
    log_path = tmp_path / "command.log"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_quiet_run",
            "--label",
            "test-command",
            "--log",
            str(log_path),
            "--timeout-seconds",
            timeout,
            "--",
            sys.executable,
            "-c",
            child_code,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    events = [json.loads(line) for line in result.stdout.splitlines()]
    return result, events, log_path


def test_success_keeps_child_output_out_of_agent_stream(tmp_path: Path) -> None:
    result, events, log_path = _run(
        tmp_path,
        "print('first private line'); print('second private line')",
    )

    assert result.returncode == 0
    assert [event["status"] for event in events] == ["started", "completed"]
    assert "private line" not in result.stdout
    assert result.stderr == ""
    assert log_path.read_text() == "first private line\nsecond private line\n"
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert events[-1]["log_bytes"] == log_path.stat().st_size
    assert events[-1]["log_sha256"] == hashlib.sha256(log_path.read_bytes()).hexdigest()


def test_failure_keeps_large_output_in_log_and_returns_child_status(
    tmp_path: Path,
) -> None:
    result, events, log_path = _run(
        tmp_path,
        "import sys; [print(f'line-{i}') for i in range(2000)]; sys.exit(7)",
    )

    assert result.returncode == 7
    assert len(result.stdout) < 1000
    assert events[-1]["exit_code"] == 7
    assert events[-1]["timed_out"] is False
    assert "line-1999" in log_path.read_text()


def test_timeout_stops_child_process_group(tmp_path: Path) -> None:
    result, events, _ = _run(
        tmp_path,
        "import time; print('started', flush=True); time.sleep(30)",
        timeout="0.1",
    )

    assert result.returncode == 124
    assert events[-1]["exit_code"] == 124
    assert events[-1]["timed_out"] is True


def test_existing_log_is_not_replaced(tmp_path: Path) -> None:
    log_path = tmp_path / "command.log"
    log_path.write_text("prior evidence\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_quiet_run",
            "--label",
            "test-command",
            "--log",
            str(log_path),
            "--timeout-seconds",
            "5",
            "--",
            sys.executable,
            "-c",
            "print('replacement')",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 73
    assert json.loads(result.stdout)["status"] == "log_exists"
    assert log_path.read_text() == "prior evidence\n"


def test_termination_signal_stops_child_process_group(tmp_path: Path) -> None:
    log_path = tmp_path / "command.log"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_quiet_run",
            "--label",
            "test-command",
            "--log",
            str(log_path),
            "--timeout-seconds",
            "30",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    started = json.loads(process.stdout.readline())

    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)
    completed = json.loads(stdout)

    assert process.returncode == 128 + signal.SIGTERM
    assert stderr == ""
    assert completed["interrupted"] is True
    assert completed["termination_signal"] == signal.SIGTERM
    try:
        os.kill(started["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("child process still exists after wrapper termination")
