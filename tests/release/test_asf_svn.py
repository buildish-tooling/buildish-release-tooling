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

"""Integration tests for the SVN abstraction."""

from __future__ import annotations

import subprocess
import unittest

from buildish_release_tooling.release.asf_svn import AsfSvnClient, url_join

from tests.support import (
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    init_svn_repo_and_checkout,
)


class AsfSvnIntegrationTest(unittest.TestCase):
    """Exercise stage/promote/prune flows against a detached local SVN repository."""

    def test_asf_svn_can_stage_promote_and_prune(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        client = AsfSvnClient()
        component_id = "buildish-mammoth-cache"
        dev_base_url = url_join(repo_url, "dist/dev/incubator/buildish", component_id)
        release_base_url = url_join(repo_url, "dist/release/incubator/buildish", component_id)
        rc_url = url_join(dev_base_url, "1.2.3-rc0")
        old_release_url = url_join(release_base_url, "1.2.1")
        final_release_url = url_join(release_base_url, "1.2.3")
        artifact_path = sandbox_dir / "buildish-mammoth-cache-1.2.3-incubating-src.tar.gz"
        artifact_path.write_text("artifact\n", encoding="utf-8")

        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        subprocess.run(["svn", "update", str(working_copy_dir)], check=True, capture_output=True, text=True)
        client.working_copy_put_file(
            working_copy_dir,
            artifact_path,
            f"dist/dev/incubator/buildish/{component_id}/1.2.3-rc0/{artifact_path.name}",
        )
        client.working_copy_put_file(
            working_copy_dir,
            artifact_path,
            f"dist/release/incubator/buildish/{component_id}/1.2.1/buildish-mammoth-cache-1.2.1-incubating-src.tar.gz",
        )
        client.commit_working_copy(working_copy_dir, "stage draft release artifacts")

        self.assertEqual(["1.2.3-rc0/"], client.list_entries(dev_base_url))
        client.copy_url(rc_url, final_release_url, "promote release candidate to release")
        self.assertEqual(["1.2.1/", "1.2.3/"], client.list_entries(release_base_url))
        client.delete_url(old_release_url, "prune older same-line release")
        self.assertFalse(client.path_exists(old_release_url))
