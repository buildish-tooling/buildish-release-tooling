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

"""Tests for release-harness subprocess helpers."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

from buildish_release_tooling.harness.process import (
    DEFAULT_HARNESS_COMMAND_TIMEOUT_SECONDS,
    LONG_HARNESS_COMMAND_TIMEOUT_SECONDS,
    harness_command_timeout_seconds,
    run_harness_command,
    wait_for_harness_process,
)


class HarnessProcessTest(unittest.TestCase):
    """Verify harness subprocess timeout behavior."""

    def test_run_harness_command_applies_default_timeout(self) -> None:
        completed = subprocess.CompletedProcess(["git", "status"], 0, "", "")
        with mock.patch(
            "buildish_release_tooling.harness.process.subprocess.run",
            return_value=completed,
        ) as run_mock:
            result = run_harness_command(["git", "status"], check=True, capture_output=True, text=True)

        self.assertIs(result, completed)
        self.assertEqual(DEFAULT_HARNESS_COMMAND_TIMEOUT_SECONDS, run_mock.call_args.kwargs["timeout"])

    def test_harness_command_timeout_uses_environment_override(self) -> None:
        with mock.patch.dict(os.environ, {"BUILDISH_HARNESS_COMMAND_TIMEOUT_SECONDS": "12.5"}):
            self.assertEqual(12.5, harness_command_timeout_seconds())

    def test_run_harness_command_preserves_explicit_timeout(self) -> None:
        completed = subprocess.CompletedProcess(["git", "status"], 0, "", "")
        with mock.patch(
            "buildish_release_tooling.harness.process.subprocess.run",
            return_value=completed,
        ) as run_mock:
            run_harness_command(["git", "status"], timeout=3)

        self.assertEqual(3, run_mock.call_args.kwargs["timeout"])

    def test_wait_for_harness_process_kills_on_timeout(self) -> None:
        process = mock.Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired(["act"], 1), 9]

        with self.assertRaises(subprocess.TimeoutExpired):
            wait_for_harness_process(process, timeout=1)

        process.kill.assert_called_once_with()
        self.assertEqual([mock.call(timeout=1), mock.call()], process.wait.call_args_list)

    def test_wait_for_harness_process_uses_long_default_timeout(self) -> None:
        process = mock.Mock()
        process.wait.return_value = 0
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(0, wait_for_harness_process(process))

        process.wait.assert_called_once_with(timeout=LONG_HARNESS_COMMAND_TIMEOUT_SECONDS)
