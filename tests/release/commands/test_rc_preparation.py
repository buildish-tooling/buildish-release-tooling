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
"""RC preparation command integration tests."""

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class RcPreparationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """RC preparation command integration tests."""

    def test_prepare_rc_command_uses_yaml_component_config(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        github_output_path = sandbox_dir / "prepare-rc.outputs"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(
            clone_dir,
            "refs/remotes/origin/release/1.2.x^{commit}",
        )
        expected_source_date_epoch = subprocess.run(
            [
                "git",
                "-C",
                str(clone_dir),
                "show",
                "-s",
                "--format=%ct",
                expected_commit,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
        )
        self.assertEqual(0, completed.returncode)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual(expected_source_date_epoch, manifest["source_date_epoch"])
        self.assertEqual("release/1.2.x", manifest["resolved_release_branch"])
        self.assertEqual("3", manifest["rc_number"])
        self.assertEqual("v1.2.3-rc3", manifest["rc_tag"])
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual("1.2.3", github_outputs["version"])
        self.assertEqual("v1.2.3-rc3", github_outputs["rc_tag"])
        self.assertEqual(expected_commit, github_outputs["resolved_source_ref"])
        self.assertEqual(expected_source_date_epoch, github_outputs["source_date_epoch"])

    def test_cleanup_dev_svn_rcs_command_deletes_matching_version_directories(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "cleanup-dev-svn-rcs.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        for rc_directory in ("1.2.3-rc0", "1.2.3-rc2", "1.2.4-rc0"):
            client.mkdir_url(f"{dev_base_url}/{rc_directory}", f"create {rc_directory}")
        completed = run_cli(
            [
                "cleanup-dev-svn-rcs",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, manifest["component"])
        self.assertEqual("1.2.3-rc0,1.2.3-rc2", manifest["deleted_rc_directories"])
        self.assertEqual(["1.2.4-rc0/"], client.list_entries(dev_base_url))
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Cleanup ASF SVN dev/dist for version 1.2.3", summary_text)
        self.assertIn("| Deleted RC directory count | 2 |", summary_text)
        self.assertIn("1.2.3-rc0/", summary_text)

    def test_prepare_rc_rejects_non_production_release_targets_without_opt_in(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="file:///tmp/buildish-test/dev",
            release_base_url="file:///tmp/buildish-test/release",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("--allow-non-production-release-targets", completed.stderr)

    def test_prepare_rc_allows_non_production_release_targets_with_opt_in(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="file:///tmp/buildish-test/dev",
            release_base_url="file:///tmp/buildish-test/release",
        )
        completed = run_cli(
            [
                "prepare-rc",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertTrue(str(manifest["source_date_epoch"]).isdigit())
        self.assertEqual("file:///tmp/buildish-test/dev/1.2.3-rc0/", manifest["staging_url"])
