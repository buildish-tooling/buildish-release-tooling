# Copyright 2026 The Apache Software Foundation
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
from collections.abc import Mapping, Sequence
from pathlib import Path

from apache_buildish_release_tooling.release.command_logging import (
    format_command,
    log_command_output,
    print_command,
)

_FORCE_CAPTURE_OUTPUT_ENV_NAME = "BUILDISH_COMMAND_CAPTURE_OUTPUT"


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
    completed = subprocess.run(  # noqa: S603
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        env=merged_env,
        input=input_text,
        text=True,
        capture_output=effective_capture_output,
        check=False,
    )
    if effective_capture_output:
        log_command_output("stdout", completed.stdout or "", extra_secret_values=extra_secret_values)
        log_command_output("stderr", completed.stderr or "", extra_secret_values=extra_secret_values)
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit code {completed.returncode}"
        raise CommandExecutionError(f"command failed: {format_command(command)}: {detail}")
    return completed
