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

"""Integration tests for Git repository helpers."""

from __future__ import annotations

import subprocess
import unittest

from apache_buildish_release_tooling.git_repo import GitRepository

from tests.support import cleanup_sandbox, create_build_test_sandbox, fetch_git_origin_refs, init_git_origin_and_clone


class GitRepositoryIntegrationTest(unittest.TestCase):
    """Exercise branch and tag resolution against real disposable repositories."""

    def test_git_repo_can_resolve_remote_release_branches_and_tags(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        subprocess.run(["git", "-C", str(origin_dir), "branch", "release/1.x", "main"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "branch", "release/1.2.x", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.3-rc0", "-m", "rc0", "main"], check=True
        )
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.3-rc2", "-m", "rc2", "main"], check=True
        )
        fetch_git_origin_refs(clone_dir)
        repo = GitRepository(clone_dir)
        resolved_branch = repo.resolve_release_branch_for_version("1.2.3")
        resolved_commit = repo.resolve_commit("release/1.2.x")
        release_head = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "refs/remotes/origin/release/1.2.x^{commit}"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual("release/1.2.x", resolved_branch)
        self.assertEqual(release_head, resolved_commit)
        self.assertEqual(2, repo.highest_matching_rc_number_or_zero("1.2.3"))
        self.assertEqual("v1.2.3-rc2", repo.latest_matching_rc_tag("1.2.3"))

    def test_git_repo_can_create_branch_from_remote_tracking_source_ref(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        subprocess.run(["git", "-C", str(origin_dir), "branch", "release/1.x", "main"], check=True)
        fetch_git_origin_refs(clone_dir)
        repo = GitRepository(clone_dir)
        repo.create_branch("release/1.2.x", "release/1.x")
        source_commit = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "refs/remotes/origin/release/1.x^{commit}"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        created_commit = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "refs/heads/release/1.2.x^{commit}"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        self.assertEqual(source_commit, created_commit)
