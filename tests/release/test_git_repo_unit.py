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

"""Unit tests for Git command construction helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from buildish_release_tooling.release.git_repo import GitRepository, require_worktree_root


class GitRepositoryUnitTest(unittest.TestCase):
    """Verify deterministic Git helper behavior without a real repository."""

    def test_create_branch_runs_expected_git_command(self) -> None:
        repo = GitRepository(Path("/repo"))
        with (
            mock.patch.object(GitRepository, "branch_exists", return_value=False),
            mock.patch.object(GitRepository, "resolve_commit", return_value="deadbeef"),
            mock.patch.object(GitRepository, "_run") as run_git,
        ):
            repo.create_branch("release/1.2.x", "main")
        run_git.assert_called_once_with("branch", "release/1.2.x", "deadbeef", capture_output=False)

    def test_create_annotated_tag_runs_expected_git_command(self) -> None:
        repo = GitRepository(Path("/repo"))
        with (
            mock.patch.object(GitRepository, "tag_exists", return_value=False),
            mock.patch.object(GitRepository, "_run") as run_git,
        ):
            repo.create_annotated_tag("v1.2.3", "deadbeef", "release v1.2.3")
        run_git.assert_called_once_with(
            "tag",
            "-a",
            "v1.2.3",
            "-m",
            "release v1.2.3",
            "deadbeef",
            capture_output=False,
        )

    def test_require_worktree_root_delegates_to_current_worktree_root(self) -> None:
        with mock.patch(
            "buildish_release_tooling.release.git_repo.current_worktree_root",
            return_value=Path("/repo"),
        ) as current_root:
            actual = require_worktree_root(Path("/worktree/subdir"))
        self.assertEqual(Path("/repo"), actual)
        current_root.assert_called_once_with(Path("/worktree/subdir"))
