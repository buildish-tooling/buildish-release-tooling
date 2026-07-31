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

"""Unit tests for GitHub Git-tag/ref API helpers."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from buildish_release_tooling.release.platforms.github import refs as github_git_refs


class GitHubGitRefsTest(unittest.TestCase):
    """Verify GitHub Git-ref helper behavior without invoking the real GitHub CLI."""

    def test_create_annotated_tag_object_rejects_non_object_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GitHub tag-object creation did not return a JSON object payload",
            ):
                github_git_refs.create_annotated_tag_object(
                    "buildish-tooling/buildish-example",
                    tag_name="v1.2.3",
                    target_commit="deadbeef",
                    message="Release Buildish Example 1.2.3",
                )

    def test_resolve_annotated_tag_target_commit_follows_tag_object(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            side_effect=(
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {
                            "ref": "refs/tags/v1.2.3",
                            "object": {"sha": "tag-object-sha", "type": "tag"},
                        }
                    ),
                    "",
                ),
                subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {"object": {"sha": "commit-sha", "type": "commit"}}
                    ),
                    "",
                ),
            ),
        ) as run_command:
            actual = github_git_refs.resolve_annotated_tag_target_commit(
                "buildish-tooling/buildish-example",
                tag_name="v1.2.3",
            )

        self.assertEqual("commit-sha", actual)
        self.assertEqual(2, run_command.call_count)

    def test_resolve_annotated_tag_target_commit_rejects_lightweight_tag(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "ref": "refs/tags/v1.2.3",
                        "object": {"sha": "commit-sha", "type": "commit"},
                    }
                ),
                "",
            ),
        ):
            with self.assertRaisesRegex(ValueError, "not an annotated tag"):
                github_git_refs.resolve_annotated_tag_target_commit(
                    "buildish-tooling/buildish-example",
                    tag_name="v1.2.3",
                )

    def test_create_ref_rejects_invalid_object_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, json.dumps({"ref": []}), ""),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GitHub ref creation returned a malformed GitHub Git object payload",
            ):
                github_git_refs.create_ref(
                    "buildish-tooling/buildish-example",
                    ref_name="refs/tags/v1.2.3",
                    target_sha="tag-object-sha",
                )

    def test_update_ref_rejects_invalid_object_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, json.dumps({"sha": []}), ""),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "GitHub ref update returned a malformed GitHub Git object payload",
            ):
                github_git_refs.update_ref(
                    "buildish-tooling/buildish-example",
                    ref_name="refs/tags/v1",
                    target_sha="deadbeef",
                    force=True,
                )

    def test_create_annotated_tag_object_posts_expected_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, json.dumps({"sha": "tag-object-sha"}), ""),
        ) as run_command:
            actual = github_git_refs.create_annotated_tag_object(
                "buildish-tooling/buildish-example",
                tag_name="v1.2.3",
                target_commit="deadbeef",
                message="Release Buildish Example 1.2.3",
            )
        self.assertEqual({"sha": "tag-object-sha"}, actual)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "POST",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/buildish-tooling/buildish-example/git/tags",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "tag": "v1.2.3",
                    "message": "Release Buildish Example 1.2.3",
                    "object": "deadbeef",
                    "type": "commit",
                }
            ),
        )

    def test_create_ref_posts_expected_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, json.dumps({"ref": "refs/tags/v1.2.3"}), ""),
        ) as run_command:
            actual = github_git_refs.create_ref(
                "buildish-tooling/buildish-example",
                ref_name="refs/tags/v1.2.3",
                target_sha="tag-object-sha",
            )
        self.assertEqual({"ref": "refs/tags/v1.2.3"}, actual)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "POST",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/buildish-tooling/buildish-example/git/refs",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "ref": "refs/tags/v1.2.3",
                    "sha": "tag-object-sha",
                }
            ),
        )

    def test_update_ref_posts_expected_payload(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.platforms.github.refs.run_logged_command",
            return_value=subprocess.CompletedProcess([], 0, json.dumps({"ref": "refs/tags/v1"}), ""),
        ) as run_command:
            actual = github_git_refs.update_ref(
                "buildish-tooling/buildish-example",
                ref_name="refs/tags/v1",
                target_sha="deadbeef",
                force=True,
            )
        self.assertEqual({"ref": "refs/tags/v1"}, actual)
        run_command.assert_called_once_with(
            [
                "gh",
                "api",
                "-X",
                "PATCH",
                "-H",
                "Accept: application/vnd.github+json",
                "repos/buildish-tooling/buildish-example/git/refs/tags/v1",
                "--input",
                "-",
            ],
            input_text=json.dumps(
                {
                    "sha": "deadbeef",
                    "force": True,
                }
            ),
        )
