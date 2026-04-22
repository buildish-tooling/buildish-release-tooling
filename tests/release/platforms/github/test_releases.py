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

"""Unit tests for GitHub Release API helpers."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.platforms.github import releases as github_releases


class GitHubReleasesTest(unittest.TestCase):
    """Verify GitHub Release helper behavior without invoking the real GitHub CLI."""

    def test_list_releases_filters_to_object_entries(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps([{"id": 1, "draft": True}, "ignored", {"id": 2, "draft": False}]),
                "",
            ),
        ):
            actual = github_releases.list_releases("buildish-tooling/buildish-example")
        self.assertEqual([{"id": 1, "draft": True}, {"id": 2, "draft": False}], actual)

    def test_list_releases_ignores_malformed_release_objects(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    [
                        {"id": 1, "draft": True, "tag_name": "v1.2.3"},
                        {"id": [], "draft": True, "tag_name": "broken"},
                        {"id": 2, "draft": False, "tag_name": "v1.2.2"},
                    ]
                ),
                "",
            ),
        ):
            actual = github_releases.list_releases("buildish-tooling/buildish-example")
        self.assertEqual(
            [
                {"id": 1, "draft": True, "tag_name": "v1.2.3"},
                {"id": 2, "draft": False, "tag_name": "v1.2.2"},
            ],
            actual,
        )

    def test_list_releases_returns_empty_list_for_non_list_payload_variants(self) -> None:
        malformed_payloads: tuple[object, ...] = (
            {},
            {"items": []},
            "not-a-list",
            17,
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with mock.patch(
                    "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
                ):
                    actual = github_releases.list_releases("buildish-tooling/buildish-example")
                self.assertEqual([], actual)

    def test_matching_draft_release_ids_matches_by_tag_or_name(self) -> None:
        actual = github_releases.matching_draft_release_ids(
            [
                {"id": 10, "draft": True, "tag_name": "v1.2.3", "name": "ignored"},
                {"id": 11, "draft": True, "tag_name": "v1.2.3-rc2", "name": "ignored"},
                {"id": 12, "draft": True, "tag_name": "v0.9.0", "name": "Buildish Example 1.2.3"},
                {"id": 13, "draft": False, "tag_name": "v1.2.3", "name": "Buildish Example 1.2.3"},
            ],
            tag_names=["v1.2.3", "v1.2.3-rc2"],
            release_name="Buildish Example 1.2.3",
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

    def test_release_by_tag_or_none_distinguishes_absence_from_duplicates(self) -> None:
        self.assertIsNone(
            github_releases.release_by_tag_or_none([], tag_name="v1.2.3")
        )
        with self.assertRaisesRegex(ValueError, "at most one"):
            github_releases.release_by_tag_or_none(
                [
                    {"id": 10, "tag_name": "v1.2.3"},
                    {"id": 11, "tag_name": "v1.2.3"},
                ],
                tag_name="v1.2.3",
            )

    def test_release_assets_preserve_size_and_digest_identity(self) -> None:
        actual = github_releases.release_assets(
            {
                "assets": [
                    {
                        "id": 101,
                        "name": "example.zip",
                        "size": 17,
                        "digest": f"sha256:{'a' * 64}",
                    }
                ]
            }
        )
        self.assertEqual(
            [
                {
                    "id": 101,
                    "name": "example.zip",
                    "size": 17,
                    "digest": f"sha256:{'a' * 64}",
                }
            ],
            actual,
        )

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

    def test_release_asset_ids_by_names_rejects_malformed_asset_payloads(self) -> None:
        actual = github_releases.release_asset_ids_by_names(
            {
                "assets": [
                    {"id": 101, "name": "rc-vote-manifest.json"},
                    {"id": [], "name": "broken-entry"},
                    {"id": 102, "name": ["still-broken"]},
                ]
            },
            asset_names=["rc-vote-manifest.json", "broken-entry"],
        )
        self.assertEqual({}, actual)

    def test_release_asset_ids_by_names_returns_empty_for_malformed_assets_variants(self) -> None:
        malformed_payloads: tuple[dict[str, object], ...] = (
            {"assets": {}},
            {"assets": "broken"},
            {"assets": [{"id": "not-an-int", "name": "rc-vote-manifest.json"}]},
        )
        for release_payload in malformed_payloads:
            with self.subTest(release_payload=release_payload):
                actual = github_releases.release_asset_ids_by_names(
                    release_payload,
                    asset_names=["rc-vote-manifest.json"],
                )
                self.assertEqual({}, actual)

    def test_delete_release_uses_delete_api_call(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.delete_release("buildish-tooling/buildish-example", 42)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "DELETE",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/buildish-tooling/buildish-example/releases/42",
            ],
            capture_output=False,
        )

    def test_delete_release_asset_uses_delete_api_call(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.delete_release_asset("buildish-tooling/buildish-example", 99)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "DELETE",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/buildish-tooling/buildish-example/releases/assets/99",
            ],
            capture_output=False,
        )

    def test_create_draft_release_posts_expected_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps({"id": 42, "tag_name": "v1.2.3"}),
                "",
            ),
        ) as run_command:
            actual = github_releases.create_draft_release(
                "buildish-tooling/buildish-example",
                tag_name="v1.2.3",
                target_commitish="deadbeef",
                release_name="Buildish Example 1.2.3",
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
                "repos/buildish-tooling/buildish-example/releases",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "tag_name": "v1.2.3",
                    "target_commitish": "deadbeef",
                    "name": "Buildish Example 1.2.3",
                    "body": "release body",
                    "draft": True,
                    "prerelease": False,
                    "generate_release_notes": False,
                }
            ),
        )

    def test_create_draft_release_rejects_malformed_release_payload_variants(self) -> None:
        malformed_payloads: tuple[object, ...] = (
            [],
            {"id": []},
            {"id": 42, "draft": []},
            {"id": 42, "assets": "broken"},
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with mock.patch(
                    "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        "GitHub release creation",
                    ):
                        github_releases.create_draft_release(
                            "buildish-tooling/buildish-example",
                            tag_name="v1.2.3",
                            target_commitish="deadbeef",
                            release_name="Buildish Example 1.2.3",
                            release_body="release body",
                        )

    def test_create_draft_release_rejects_non_object_payload_with_normalized_error(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GitHub release creation did not return a JSON object payload",
            ):
                github_releases.create_draft_release(
                    "buildish-tooling/buildish-example",
                    tag_name="v1.2.3",
                    target_commitish="deadbeef",
                    release_name="Buildish Example 1.2.3",
                    release_body="release body",
                )

    def test_update_release_posts_expected_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps({"id": 42, "draft": False}),
                "",
            ),
        ) as run_command:
            actual = github_releases.update_release(
                "buildish-tooling/buildish-example",
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
                "repos/buildish-tooling/buildish-example/releases/42",
                "--input",
                "-",
            ],
            input_text=json.dumps({"draft": False, "prerelease": False}),
        )

    def test_update_release_rejects_malformed_release_payload_variants(self) -> None:
        malformed_payloads: tuple[object, ...] = (
            [],
            {"id": "not-an-int"},
            {"id": 42, "draft": "nope"},
            {"id": 42, "assets": "broken"},
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with mock.patch(
                    "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
                ):
                    with self.assertRaisesRegex(
                        ValueError,
                        "GitHub release update",
                    ):
                        github_releases.update_release(
                            "buildish-tooling/buildish-example",
                            42,
                            payload={"draft": False, "prerelease": False},
                        )

    def test_update_release_rejects_non_object_payload_with_normalized_error(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GitHub release update did not return a JSON object payload",
            ):
                github_releases.update_release(
                    "buildish-tooling/buildish-example",
                    42,
                    payload={"draft": False, "prerelease": False},
                )

    def test_upload_release_assets_uses_release_upload_with_clobber(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.releases.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run_command:
            github_releases.upload_release_assets(
                "buildish-tooling/buildish-example",
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
                "buildish-tooling/buildish-example",
            ],
            capture_output=False,
        )
