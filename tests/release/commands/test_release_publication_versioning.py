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
"""Release publication command integration tests."""

"""Release version and pruning command tests."""

# ruff: noqa: F403, F405
from tests.release.commands.release_publication_support import (
    ReleasePublicationCommandTestBase,
)
from tests.release.commands.support import *


class ReleaseVersionCommandIntegrationTest(ReleasePublicationCommandTestBase):
    """Release version and pruning command tests."""

    def test_release_version_command_infers_release_line_and_pruning_from_svn(
        self,
    ) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, _working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "release-version.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.3.0"):
            client.mkdir_url(
                f"{release_base_url}/{published_version}", f"create {published_version}"
            )
        completed = run_cli(
            [
                "release-version",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.x", manifest["release_line"])
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual(["1.2.1", "1.2.2"], manifest["archive_versions"])

    def test_prune_older_line_releases_command_deletes_specific_line_versions(
        self,
    ) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, _working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prune-older-line-releases.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.2.3", "1.3.0"):
            client.mkdir_url(
                f"{release_base_url}/{published_version}", f"create {published_version}"
            )
        completed = run_cli(
            [
                "prune-older-line-releases",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.x", manifest["release_line"])
        self.assertEqual(["1.2.1", "1.2.2"], manifest["pruned_versions"])
        self.assertEqual(["1.2.3/", "1.3.0/"], client.list_entries(release_base_url))
