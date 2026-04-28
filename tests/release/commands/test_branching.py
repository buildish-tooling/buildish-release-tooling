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
"""Branching command integration tests."""

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class BranchingCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Branching command integration tests."""

    def test_create_release_branch_command_applies_changes_when_requested(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-release-branch.json"
        git_create_branch(origin_dir, "release/1.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-release-branch",
                "--component-config",
                str(config_path),
                "--apply",
                "1.2.x",
                "release/1.x",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("release/1.2.x", manifest["release_branch"])
        created_commit = git_rev_parse(clone_dir, "refs/heads/release/1.2.x^{commit}")
        source_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.x^{commit}")
        self.assertEqual(source_commit, created_commit)
