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

"""Unit tests for SVN command construction and path helpers."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.asf_svn import AsfSvnClient, url_join


class AsfSvnUnitTest(unittest.TestCase):
    """Verify deterministic SVN helper behavior without a real repository."""

    def test_url_join_normalizes_slashes(self) -> None:
        self.assertEqual(
            "https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-mammoth-cache/1.2.3-rc0",
            url_join(
                "https://dist.apache.org/repos/dist/dev/incubator/buildish/",
                "/buildish-mammoth-cache/",
                "1.2.3-rc0",
            ),
        )

    def test_checkout_url_runs_expected_command(self) -> None:
        client = AsfSvnClient()
        with mock.patch(
            "buildish_release_tooling.release.asf_svn.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            client.checkout_url(
                "https://example.invalid/repos/dist/dev/incubator/buildish",
                Path("/sandbox/wc"),
            )
        run_command.assert_called_once_with(
            ["svn", "checkout", "https://example.invalid/repos/dist/dev/incubator/buildish", "/sandbox/wc"],
            capture_output=False,
            check=True,
            extra_secret_values=["", ""],
        )

    def test_copy_url_runs_expected_command(self) -> None:
        client = AsfSvnClient()
        with mock.patch(
            "buildish_release_tooling.release.asf_svn.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            client.copy_url(
                "https://example.invalid/dev/1.2.3-rc0",
                "https://example.invalid/release/1.2.3",
                "promote release",
            )
        run_command.assert_called_once_with(
            [
                "svn",
                "copy",
                "-m",
                "promote release",
                "https://example.invalid/dev/1.2.3-rc0",
                "https://example.invalid/release/1.2.3",
            ],
            capture_output=False,
            check=True,
            extra_secret_values=["", ""],
        )

    def test_copy_url_with_credentials_uses_password_from_stdin(self) -> None:
        secret_value = "".join(["super", "-secret"])
        client = AsfSvnClient(username="release-user", password=secret_value)
        with mock.patch(
            "buildish_release_tooling.release.asf_svn.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            client.copy_url(
                "https://example.invalid/dev/1.2.3-rc0",
                "https://example.invalid/release/1.2.3",
                "promote release",
            )
        run_command.assert_called_once_with(
            [
                "svn",
                "--non-interactive",
                "--no-auth-cache",
                "--username",
                "release-user",
                "--password-from-stdin",
                "copy",
                "-m",
                "promote release",
                "https://example.invalid/dev/1.2.3-rc0",
                "https://example.invalid/release/1.2.3",
            ],
            capture_output=False,
            check=True,
            input_text=f"{secret_value}\n",
            extra_secret_values=["release-user", secret_value],
        )

    def test_delete_url_runs_expected_command(self) -> None:
        client = AsfSvnClient()
        with mock.patch(
            "buildish_release_tooling.release.asf_svn.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            client.delete_url("https://example.invalid/release/1.2.1", "prune old release")
        run_command.assert_called_once_with(
            ["svn", "delete", "-m", "prune old release", "https://example.invalid/release/1.2.1"],
            capture_output=False,
            check=True,
            extra_secret_values=["", ""],
        )

    def test_require_working_copy_root_uses_svn_info(self) -> None:
        client = AsfSvnClient()
        with mock.patch(
            "buildish_release_tooling.release.asf_svn.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "/sandbox/svnwc\n", ""),
        ) as run_command:
            actual = client.require_working_copy_root(Path("/sandbox/svnwc/nested/path"))
        self.assertEqual(Path("/sandbox/svnwc"), actual)
        run_command.assert_called_once_with(
            ["svn", "info", "--show-item", "wc-root", "/sandbox/svnwc/nested/path"],
            capture_output=True,
            check=True,
            extra_secret_values=["", ""],
        )
