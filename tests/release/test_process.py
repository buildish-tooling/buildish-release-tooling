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

"""Tests for subprocess execution helpers."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest import mock

from apache_buildish_release_tooling.release.process import CommandExecutionError, run_logged_command


class ProcessTest(unittest.TestCase):
    """Verify subprocess helper behavior that tests rely on for quiet execution."""

    def test_run_logged_command_can_force_output_capture_via_environment(self) -> None:
        original_env = dict(os.environ)

        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        os.environ["BUILDISH_COMMAND_CAPTURE_OUTPUT"] = "1"
        completed = subprocess.CompletedProcess(["svn", "info"], 0, "", "")
        with (
            mock.patch(
                "apache_buildish_release_tooling.release.process.subprocess.run",
                return_value=completed,
            ) as run_mock,
            mock.patch("apache_buildish_release_tooling.release.process.print_command"),
            mock.patch("apache_buildish_release_tooling.release.process.log_command_output"),
        ):
            result = run_logged_command(["svn", "info"], capture_output=False)

        self.assertIs(result, completed)
        self.assertTrue(run_mock.call_args.kwargs["capture_output"])
        self.assertEqual(3600, run_mock.call_args.kwargs["timeout"])

    def test_run_logged_command_redacts_failure_details(self) -> None:
        completed = subprocess.CompletedProcess(
            ["gh", "auth", "status"],
            1,
            "",
            "failed for token secret-token\n",
        )
        with (
            mock.patch(
                "apache_buildish_release_tooling.release.process.subprocess.run",
                return_value=completed,
            ),
            mock.patch("apache_buildish_release_tooling.release.process.print_command"),
            mock.patch("apache_buildish_release_tooling.release.process.log_command_output"),
        ):
            with self.assertRaisesRegex(CommandExecutionError, r"\*\*\*") as context:
                run_logged_command(
                    ["gh", "auth", "status", "--token", "secret-token"],
                    extra_secret_values=("secret-token",),
                )

        self.assertNotIn("secret-token", str(context.exception))

    def test_run_logged_command_raises_sanitized_timeout(self) -> None:
        timeout = subprocess.TimeoutExpired(
            ["deploy", "secret-token"],
            timeout=2,
            stderr="waiting on secret-token\n",
        )
        with (
            mock.patch(
                "apache_buildish_release_tooling.release.process.subprocess.run",
                side_effect=timeout,
            ) as run_mock,
            mock.patch("apache_buildish_release_tooling.release.process.print_command"),
        ):
            with self.assertRaisesRegex(CommandExecutionError, "timed out") as context:
                run_logged_command(
                    ["deploy", "secret-token"],
                    extra_secret_values=("secret-token",),
                    timeout_seconds=2,
                )

        self.assertEqual(2, run_mock.call_args.kwargs["timeout"])
        self.assertNotIn("secret-token", str(context.exception))
