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

"""Pytest-wide subprocess safety defaults."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from typing import Any

import pytest

_TEST_TIMEOUT_ENV_NAME = "BUILDISH_TEST_COMMAND_TIMEOUT_SECONDS"
_DEFAULT_TEST_COMMAND_TIMEOUT_SECONDS = 5 * 60


def _test_command_timeout_seconds() -> float:
    raw_value = os.environ.get(_TEST_TIMEOUT_ENV_NAME)
    if raw_value is None:
        return _DEFAULT_TEST_COMMAND_TIMEOUT_SECONDS
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{_TEST_TIMEOUT_ENV_NAME} must be a number of seconds") from exc
    if timeout <= 0:
        raise ValueError(f"{_TEST_TIMEOUT_ENV_NAME} must be greater than zero")
    return timeout


@pytest.fixture(autouse=True)
def _default_subprocess_run_timeout(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure direct test subprocess.run calls have a timeout by default."""

    original_run = subprocess.run

    def run_with_default_timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        kwargs.setdefault("timeout", _test_command_timeout_seconds())
        return original_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run_with_default_timeout)
    yield
