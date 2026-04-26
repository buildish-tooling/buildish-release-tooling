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

"""Unit tests for GitHub Release API helpers."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from apache_buildish_release_tooling.release import github_releases


class GitHubReleasesTest(unittest.TestCase):
    """Verify GitHub Release helper behavior without invoking the real GitHub CLI."""

    def test_list_releases_filters_to_object_entries(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps([{"id": 1, "draft": True}, "ignored", {"id": 2, "draft": False}]),
                "",
            ),
        ):
            actual = github_releases.list_releases("apache/buildish-example")
        self.assertEqual([{"id": 1, "draft": True}, {"id": 2, "draft": False}], actual)

    def test_matching_draft_release_ids_matches_by_tag_or_name(self) -> None:
        actual = github_releases.matching_draft_release_ids(
            [
                {"id": 10, "draft": True, "tag_name": "v1.2.3", "name": "ignored"},
                {"id": 11, "draft": True, "tag_name": "v1.2.3-rc2", "name": "ignored"},
                {"id": 12, "draft": True, "tag_name": "v0.9.0", "name": "Apache Buildish Example 1.2.3"},
                {"id": 13, "draft": False, "tag_name": "v1.2.3", "name": "Apache Buildish Example 1.2.3"},
            ],
            tag_names=["v1.2.3", "v1.2.3-rc2"],
            release_name="Apache Buildish Example 1.2.3",
        )
        self.assertEqual([10, 11, 12], actual)

    def test_release_by_tag_returns_unique_match(self) -> None:
        actual = github_releases.release_by_tag(
            [
                {"id": 10, "draft": True, "tag_name": "v1.2.3"},
                {"id": 11, "draft": False, "tag_name": "v1.2.2"},
            ],
            tag_name="v1.2.3",
        )
        self.assertEqual({"id": 10, "draft": True, "tag_name": "v1.2.3"}, actual)

    def test_release_asset_ids_by_names_returns_matching_asset_ids(self) -> None:
        actual = github_releases.release_asset_ids_by_names(
            {
                "assets": [
                    {"id": 101, "name": "rc-vote-manifest.json"},
                    {"id": 102, "name": "rc-vote-manifest.json.asc"},
                    {"id": 103, "name": "ignored.txt"},
                ]
            },
            asset_names=["rc-vote-manifest.json", "rc-vote-manifest.json.sha512"],
        )
        self.assertEqual({"rc-vote-manifest.json": 101}, actual)

    def test_delete_release_uses_delete_api_call(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.delete_release("apache/buildish-example", 42)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "DELETE",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/apache/buildish-example/releases/42",
            ],
            capture_output=False,
        )

    def test_delete_release_asset_uses_delete_api_call(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.delete_release_asset("apache/buildish-example", 99)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "DELETE",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/apache/buildish-example/releases/assets/99",
            ],
            capture_output=False,
        )

    def test_create_draft_release_posts_expected_payload(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps({"id": 42, "tag_name": "v1.2.3"}),
                "",
            ),
        ) as run_command:
            actual = github_releases.create_draft_release(
                "apache/buildish-example",
                tag_name="v1.2.3",
                target_commitish="deadbeef",
                release_name="Apache Buildish Example 1.2.3",
                release_body="release body",
            )
        self.assertEqual({"id": 42, "tag_name": "v1.2.3"}, actual)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "POST",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/apache/buildish-example/releases",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "tag_name": "v1.2.3",
                    "target_commitish": "deadbeef",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "release body",
                    "draft": True,
                    "prerelease": False,
                    "generate_release_notes": False,
                }
            ),
        )

    def test_update_release_posts_expected_payload(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps({"id": 42, "draft": False}),
                "",
            ),
        ) as run_command:
            actual = github_releases.update_release(
                "apache/buildish-example",
                42,
                payload={"draft": False, "prerelease": False},
            )
        self.assertEqual({"id": 42, "draft": False}, actual)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "PATCH",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/apache/buildish-example/releases/42",
                "--input",
                "-",
            ],
            input_text=json.dumps({"draft": False, "prerelease": False}),
        )

    def test_upload_release_assets_uses_release_upload_with_clobber(self) -> None:
        with mock.patch(
            "apache_buildish_release_tooling.release.github_releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.upload_release_assets(
                "apache/buildish-example",
                tag_name="v1.2.3",
                asset_paths=[Path("build/one.zip"), Path("build/one.zip.sha512")],
                clobber=True,
            )
        run_command.assert_called_once_with(
            [
                "gh",
                "release",
                "upload",
                "v1.2.3",
                "build/one.zip",
                "build/one.zip.sha512",
                "--clobber",
                "-R",
                "apache/buildish-example",
            ],
            capture_output=False,
        )
