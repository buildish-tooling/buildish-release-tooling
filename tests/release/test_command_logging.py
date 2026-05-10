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

"""Tests for sanitized command logging."""

from __future__ import annotations

import io
import os
from unittest import mock
import unittest

from apache_buildish_release_tooling.release.command_logging import (
    command_log_sink,
    format_command,
    log_command_output_file,
    print_command,
)


class CommandLoggingTest(unittest.TestCase):
    """Verify that command logging redacts secrets consistently."""

    def test_format_command_redacts_named_credentials(self) -> None:
        original_env = dict(os.environ)
        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        secret_value = "".join(["super", "-secret"])
        os.environ["BUILDISH_SVN_DEV_USERNAME"] = "release-user"
        os.environ["BUILDISH_SVN_DEV_PASSWORD"] = secret_value
        actual = format_command(
            ["svn", "--non-interactive", "--username", "release-user", "--password", secret_value, "commit"]
        )
        self.assertEqual("svn --non-interactive --username '***' --password '***' commit", actual)

    def test_format_command_redacts_secret_values_embedded_in_arguments(self) -> None:
        original_env = dict(os.environ)
        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        secret_value = "".join(["super", "-secret"])
        os.environ["BUILDISH_SVN_DEV_USERNAME"] = "release-user"
        os.environ["BUILDISH_SVN_DEV_PASSWORD"] = secret_value
        actual = format_command(["curl", f"https://release-user:{secret_value}@example.invalid/path"])
        self.assertEqual("curl 'https://***:***@example.invalid/path'", actual)

    def test_command_logging_can_disable_default_stderr_echo_via_environment(self) -> None:
        original_env = dict(os.environ)

        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        os.environ["BUILDISH_COMMAND_LOG_STDERR"] = "0"
        stderr_buffer = io.StringIO()
        with mock.patch("sys.stderr", stderr_buffer):
            print_command(["git", "status"])
        self.assertEqual("", stderr_buffer.getvalue())

    def test_active_command_log_can_still_echo_to_stderr_when_default_echo_is_disabled(self) -> None:
        original_env = dict(os.environ)

        def restore_env() -> None:
            os.environ.clear()
            os.environ.update(original_env)

        self.addCleanup(restore_env)
        os.environ["BUILDISH_COMMAND_LOG_STDERR"] = "0"
        stderr_buffer = io.StringIO()
        log_buffer = io.StringIO()
        with (
            mock.patch("sys.stderr", stderr_buffer),
            command_log_sink(log_buffer, echo_to_stderr=True),
        ):
            print_command(["git", "status"])
        self.assertIn("+ git status\n", stderr_buffer.getvalue())
        self.assertIn("+ git status\n", log_buffer.getvalue())

    def test_log_command_output_file_streams_and_truncates(self) -> None:
        log_buffer = io.StringIO()
        output_file = io.BytesIO(b"alpha\nsecret-token\nomega\n")

        with command_log_sink(log_buffer, echo_to_stderr=False):
            truncated = log_command_output_file(
                "stderr",
                output_file,
                max_bytes=19,
                extra_secret_values=("secret-token",),
            )

        self.assertTrue(truncated)
        self.assertIn("stderr | alpha\n", log_buffer.getvalue())
        self.assertIn("stderr | ***\n", log_buffer.getvalue())
        self.assertIn("stderr | ... output truncated after 19 bytes\n", log_buffer.getvalue())
