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
"""Release publication command integration tests."""

"""Source release SVN publication command tests."""

from tests.release.commands.release_publication_support import (
    ReleasePublicationCommandTestBase,
)
from tests.release.commands.support import (
    AsfSvnClient,
    cli_env,
    command_available,
    create_fake_gh_launcher,
    create_fake_gpg_launcher,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    json,
    run_cli,
    run_quiet,
    set_github_origin_url,
)


class SourceReleaseSvnPublicationCommandIntegrationTest(
    ReleasePublicationCommandTestBase
):
    """Source release SVN publication command tests."""

    def test_publish_source_release_svn_command_promotes_latest_rc_directory(
        self,
    ) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "buildish-tooling/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
        )
        manifest_text = self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        gpg_path = create_fake_gpg_launcher(sandbox_dir)
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--test-target-mode",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent, gpg_path.parent),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual(["1.2.3/"], client.list_entries(release_base_url))
        self.assertEqual("copied", manifest["publish_mode"])
        self.assertEqual(artifact_sha512, manifest["verified_source_artifact_sha512"])
        rerun = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--test-target-mode",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent, gpg_path.parent),
            ),
        )
        self.assertEqual(0, rerun.returncode, msg=rerun.stderr)
        rerun_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("already-present", rerun_manifest["publish_mode"])

    def test_publish_source_release_svn_command_rejects_missing_required_source_files(
        self,
    ) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, _working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "buildish-tooling/buildish-example")
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
                    "name": "Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--test-target-mode",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("missing required staged release files", completed.stderr)
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_staged_artifact_drift_from_vote_manifest(
        self,
    ) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "buildish-tooling/buildish-example")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
        )
        manifest_text = self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        run_quiet(["svn", "update", str(working_copy_dir)], check=True)
        drifted_artifact = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / "1.2.3-rc2"
            / "apache-buildish-example-1.2.3-incubating-src.tar.gz"
        )
        drifted_artifact.write_bytes(b"drifted source payload\n")
        run_quiet(
            ["svn", "commit", "-m", "drift staged artifact", str(working_copy_dir)],
            check=True,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        gpg_path = create_fake_gpg_launcher(sandbox_dir)
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--test-target-mode",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent, gpg_path.parent),
            ),
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn(
            "staged source artifact .sha512 sidecar does not match the staged source artifact bytes",
            completed.stderr,
        )
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_rc_drift(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, _working_copy_dir = (
            self._create_git_svn_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-source-release-svn.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc1")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "buildish-tooling/buildish-example")
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
                    "name": "Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        client.mkdir_url(f"{dev_base_url}/1.2.3-rc2", "create rc directory")
        completed = run_cli(
            [
                "publish-source-release-svn",
                "--component-config",
                str(config_path),
                "--test-target-mode",
                "--selected-rc-tag",
                "v1.2.3-rc1",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "draft GitHub Release for v1.2.3 now points at v1.2.3-rc2, expected v1.2.3-rc1",
            completed.stderr,
        )
