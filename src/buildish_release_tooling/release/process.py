# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared subprocess execution helpers."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO

from buildish_release_tooling.release.command_logging import (
    format_command,
    log_command_output_file,
    print_command,
    sanitize_text,
)

_FORCE_CAPTURE_OUTPUT_ENV_NAME = "BUILDISH_COMMAND_CAPTURE_OUTPUT"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 60 * 60
MAX_CAPTURED_OUTPUT_BYTES = 16 * 1024 * 1024


class CommandExecutionError(RuntimeError):
    """Raised when a logged subprocess exits unsuccessfully."""


def _force_capture_output() -> bool:
    """Return whether command output should always be captured instead of streamed."""

    raw_value = os.environ.get(_FORCE_CAPTURE_OUTPUT_ENV_NAME)
    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def run_logged_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    inherit_parent_env: bool = True,
    input_text: str | None = None,
    capture_output: bool = True,
    check: bool = True,
    log_command: bool = True,
    extra_secret_values: Sequence[str] | None = None,
    timeout_seconds: float | None = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with sanitized command logging and optional captured output."""

    merged_env = dict(os.environ) if inherit_parent_env else {}
    if env is not None:
        merged_env.update(env)
    effective_capture_output = capture_output or _force_capture_output()
    if log_command:
        print_command(
            command,
            extra_secret_values,
            stderr_enabled=True,
        )
    else:
        print_command(
            command,
            extra_secret_values,
            stderr_enabled=False,
        )
    if effective_capture_output:
        completed = _run_logged_command_with_file_capture(
            command,
            cwd=cwd,
            env=merged_env,
            input_text=input_text,
            extra_secret_values=extra_secret_values,
            timeout_seconds=timeout_seconds,
        )
    else:
        completed = _run_logged_command_without_capture(
            command,
            cwd=cwd,
            env=merged_env,
            input_text=input_text,
            extra_secret_values=extra_secret_values,
            timeout_seconds=timeout_seconds,
        )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = sanitize_text(stderr or stdout or f"exit code {completed.returncode}", extra_secret_values)
        raise CommandExecutionError(
            f"command failed: {format_command(command, extra_secret_values)}: {detail}"
        )
    return completed


def _run_logged_command_with_file_capture(
    command: Sequence[str],
    *,
    cwd: Path | None,
    env: Mapping[str, str],
    input_text: str | None,
    extra_secret_values: Sequence[str] | None,
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            completed = subprocess.run(  # noqa: S603
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                env=env,
                input=input_text,
                text=True,
                stdout=stdout_file,
                stderr=stderr_file,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            log_command_output_file("stdout", stdout_file, extra_secret_values=extra_secret_values)
            log_command_output_file("stderr", stderr_file, extra_secret_values=extra_secret_values)
            output_detail = _captured_failure_detail(stdout_file, stderr_file, extra_secret_values)
            timeout_detail = "unknown timeout" if timeout_seconds is None else f"{timeout_seconds:g}s"
            suffix = f": {output_detail}" if output_detail else ""
            raise CommandExecutionError(
                "command timed out after "
                f"{timeout_detail}: {format_command(command, extra_secret_values)}{suffix}"
            ) from exc
        log_command_output_file("stdout", stdout_file, extra_secret_values=extra_secret_values)
        log_command_output_file("stderr", stderr_file, extra_secret_values=extra_secret_values)
        stdout = _read_captured_output_file(stdout_file, "stdout")
        stderr = _read_captured_output_file(stderr_file, "stderr")
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        stdout,
        stderr,
    )


def _run_logged_command_without_capture(
    command: Sequence[str],
    *,
    cwd: Path | None,
    env: Mapping[str, str],
    input_text: str | None,
    extra_secret_values: Sequence[str] | None,
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            input=input_text,
            text=True,
            capture_output=False,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        timeout_detail = "unknown timeout" if timeout_seconds is None else f"{timeout_seconds:g}s"
        raise CommandExecutionError(
            "command timed out after "
            f"{timeout_detail}: {format_command(command, extra_secret_values)}"
        ) from exc


def _captured_failure_detail(
    stdout_file: BinaryIO,
    stderr_file: BinaryIO,
    extra_secret_values: Sequence[str] | None,
) -> str:
    try:
        detail = _read_captured_output_file(stderr_file, "stderr").strip()
        if not detail:
            detail = _read_captured_output_file(stdout_file, "stdout").strip()
    except CommandExecutionError as exc:
        detail = str(exc)
    return sanitize_text(detail, extra_secret_values)


def _read_captured_output_file(file: BinaryIO, stream_name: str) -> str:
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    if file_size > MAX_CAPTURED_OUTPUT_BYTES:
        raise CommandExecutionError(
            f"captured {stream_name} exceeded {MAX_CAPTURED_OUTPUT_BYTES} bytes"
        )
    file.seek(0)
    return file.read().decode("utf-8", errors="replace")
