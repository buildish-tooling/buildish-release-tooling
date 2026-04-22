# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Subprocess timeout helpers for release-harness execution."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from typing import Any

_HARNESS_TIMEOUT_ENV_NAME = "BUILDISH_HARNESS_COMMAND_TIMEOUT_SECONDS"
DEFAULT_HARNESS_COMMAND_TIMEOUT_SECONDS = 10 * 60
LONG_HARNESS_COMMAND_TIMEOUT_SECONDS = 60 * 60


def harness_command_timeout_seconds(default: float = DEFAULT_HARNESS_COMMAND_TIMEOUT_SECONDS) -> float:
    """Return the configured harness subprocess timeout in seconds."""

    raw_value = os.environ.get(_HARNESS_TIMEOUT_ENV_NAME)
    if raw_value is None:
        return default
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{_HARNESS_TIMEOUT_ENV_NAME} must be a number of seconds") from exc
    if timeout <= 0:
        raise ValueError(f"{_HARNESS_TIMEOUT_ENV_NAME} must be greater than zero")
    return timeout


def run_harness_command(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run a harness subprocess with a default timeout."""

    if timeout is None:
        timeout = harness_command_timeout_seconds()
    return subprocess.run(command, timeout=timeout, **kwargs)  # noqa: S603


def wait_for_harness_process(
    process: subprocess.Popen[Any],
    *,
    timeout: float | None = None,
) -> int:
    """Wait for a harness child process, killing it if the timeout expires."""

    if timeout is None:
        timeout = harness_command_timeout_seconds(LONG_HARNESS_COMMAND_TIMEOUT_SECONDS)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
