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

import os
import unittest

from apache_buildish_release_tooling.release.command_logging import format_command


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
