"""Run a noisy command while emitting only bounded lifecycle records.

The child writes its combined stdout and stderr to a private log. This process
prints one JSON record after the child starts and one after it exits. An agent
can wait for a long VPS or CI command without loading repeated status output
into its context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Sequence

from . import __version__


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return seconds


def _label(value: str) -> str:
    if not value or len(value) > 120 or any(char in value for char in "\r\n"):
        raise argparse.ArgumentTypeError(
            "must contain 1 to 120 characters without a newline"
        )
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a command with stdout and stderr in a private log, then emit "
            "only start and completion JSON records."
        )
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--label",
        required=True,
        type=_label,
        help="Short public label. Do not include credentials or command arguments.",
    )
    parser.add_argument(
        "--log",
        required=True,
        type=Path,
        help="New log path. The wrapper refuses to replace an existing file.",
    )
    parser.add_argument(
        "--timeout-seconds",
        required=True,
        type=_positive_seconds,
        help="Maximum child runtime before the process group is stopped.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run after --.",
    )
    return parser


def _event(**fields: object) -> None:
    print(json.dumps(fields, sort_keys=True, separators=(",", ":")), flush=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait()


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        _parser().error("a command is required after --")

    log_path = args.log.expanduser().resolve()
    log_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    started = time.monotonic()
    timed_out = False
    interrupted = False

    try:
        # Exclusive creation protects earlier evidence. The explicit mode keeps
        # the log private when the caller has a permissive umask.
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _event(label=args.label, log_path=str(log_path), status="log_exists")
        return 73
    except OSError as exc:
        _event(
            error_type=type(exc).__name__,
            label=args.label,
            log_path=str(log_path),
            status="log_open_failed",
        )
        return 74

    with os.fdopen(descriptor, "wb") as log_handle:
        try:
            process = subprocess.Popen(
                command,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            _event(
                error_type=type(exc).__name__,
                label=args.label,
                log_path=str(log_path),
                status="start_failed",
            )
            return 127

        received_signal: int | None = None

        def stop_on_signal(signum: int, _frame: object) -> None:
            nonlocal received_signal
            received_signal = signum
            raise KeyboardInterrupt

        previous_handlers = {
            signum: signal.signal(signum, stop_on_signal)
            for signum in (signal.SIGHUP, signal.SIGTERM)
        }
        _event(
            label=args.label,
            log_path=str(log_path),
            pid=process.pid,
            status="started",
        )
        try:
            return_code = process.wait(timeout=args.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_process_group(process)
            return_code = 124
        except KeyboardInterrupt:
            interrupted = True
            _stop_process_group(process)
            return_code = 128 + (received_signal or signal.SIGINT)
        finally:
            for signum, previous_handler in previous_handlers.items():
                signal.signal(signum, previous_handler)
            log_handle.flush()
            os.fsync(log_handle.fileno())

    elapsed = round(time.monotonic() - started, 3)
    _event(
        elapsed_seconds=elapsed,
        exit_code=return_code,
        interrupted=interrupted,
        label=args.label,
        log_bytes=log_path.stat().st_size,
        log_path=str(log_path),
        log_sha256=_file_sha256(log_path),
        status="completed",
        termination_signal=received_signal,
        timed_out=timed_out,
    )
    return return_code


def main() -> None:
    raise SystemExit(run())
