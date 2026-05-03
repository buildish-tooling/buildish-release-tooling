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

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class ReleasePublicationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Release publication command integration tests."""

    _baseline_root: Path
    _origin_template: Path
    _svn_repo_template: Path

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._baseline_root = create_build_test_sandbox()
        cls._origin_template = init_git_origin_repo(cls._baseline_root, dir_name="origin-template")
        cls._svn_repo_template, _repo_url = init_svn_repo(cls._baseline_root, dir_name="svnrepo-template")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_sandbox(cls._baseline_root)
        super().tearDownClass()

    def _create_git_sandbox(self) -> tuple[Path, Path, Path]:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir = copy_test_tree(self._origin_template, sandbox_dir / "origin")
        clone_dir = clone_git_origin(origin_dir, sandbox_dir / "clone")
        return sandbox_dir, origin_dir, clone_dir

    def _create_git_svn_sandbox(self) -> tuple[Path, Path, Path, Path, str, Path]:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        repo_dir = copy_test_tree(self._svn_repo_template, sandbox_dir / "svnrepo")
        working_copy_dir = sandbox_dir / "svnwc"
        repo_url = checkout_svn_repo(repo_dir, working_copy_dir)
        return sandbox_dir, origin_dir, clone_dir, repo_dir, repo_url, working_copy_dir

    def test_release_version_command_infers_release_line_and_pruning_from_svn(self) -> None:
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.3.0"):
            client.mkdir_url(f"{release_base_url}/{published_version}", f"create {published_version}")
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

    def test_sync_draft_github_release_command_recreates_matching_draft_release(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(
            clone_dir,
            "refs/remotes/origin/release/1.2.x^{commit}",
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 11,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                },
                {
                    "id": 12,
                    "draft": True,
                    "tag_name": "v1.2.3-rc2",
                    "name": "Stale RC draft",
                },
                {
                    "id": 99,
                    "draft": False,
                    "tag_name": "v1.2.2",
                    "name": "Apache Buildish Example 1.2.2",
                },
            ],
            create_response={
                "id": 42,
                "tag_name": "v1.2.3-rc3",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc3",
            },
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
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
        self.assertEqual("apache/buildish-example", manifest["repository_slug"])
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual("v1.2.3-rc3", manifest["rc_tag"])
        self.assertEqual("v1.2.3", manifest["final_tag"])
        self.assertEqual(["11", "12"], manifest["deleted_release_ids"])
        self.assertEqual("created", manifest["sync_mode"])
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3-rc3", manifest["release_tag"])
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc3",
            manifest["release_url"],
        )
        create_request = json.loads(
            (gh_state_dir / "create-release-request.json").read_text(encoding="utf-8")
        )
        self.assertTrue(create_request["draft"])
        self.assertEqual("v1.2.3-rc3", create_request["tag_name"])
        self.assertEqual(expected_commit, create_request["target_commitish"])
        self.assertEqual("Apache Buildish Example 1.2.3", create_request["name"])
        self.assertIn("RC tag: v1.2.3-rc3", create_request["body"])
        self.assertIn(
            "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc3/",
            create_request["body"],
        )
        deleted_endpoints = (
            gh_state_dir / "deleted-endpoints.log"
        ).read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/11",
                "repos/apache/buildish-example/releases/12",
            ],
            deleted_endpoints,
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Sync draft GitHub Release", summary_text)
        self.assertIn("id: 42", summary_text)

    def test_publish_source_release_svn_command_promotes_latest_rc_directory(self) -> None:
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
        set_github_origin_url(clone_dir, "apache/buildish-example")
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
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        completed = run_cli(
            [
                "publish-source-release-svn",
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
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual(["1.2.3/"], client.list_entries(release_base_url))
        self.assertEqual("copied", manifest["publish_mode"])
        self.assertEqual(artifact_sha512, manifest["verified_source_artifact_sha512"])
        rerun = run_cli(
            [
                "publish-source-release-svn",
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
        self.assertEqual(0, rerun.returncode, msg=rerun.stderr)
        rerun_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("already-present", rerun_manifest["publish_mode"])

    def test_publish_source_release_svn_command_rejects_missing_required_source_files(self) -> None:
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
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
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("missing required staged release files", completed.stderr)
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_staged_artifact_drift_from_vote_manifest(self) -> None:
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
        set_github_origin_url(clone_dir, "apache/buildish-example")
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
        run_quiet(["svn", "commit", "-m", "drift staged artifact", str(working_copy_dir)], check=True)
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ],
                    ),
                    "assets": [{"id": 700, "name": "rc-vote-manifest.json"}],
                }
            ],
            release_asset_text_by_id={700: manifest_text},
        )
        completed = run_cli(
            [
                "publish-source-release-svn",
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
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
                "--allow-non-production-release-targets",
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

    def test_prune_older_line_releases_command_deletes_specific_line_versions(self) -> None:
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc2^{commit}')}",
                        ]
                    ),
                }
            ],
        )
        client.mkdir_url(release_base_url, "create release component path")
        for published_version in ("1.2.1", "1.2.2", "1.2.3", "1.3.0"):
            client.mkdir_url(f"{release_base_url}/{published_version}", f"create {published_version}")
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

    def test_create_final_tag_command_creates_remote_annotated_tag(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-final-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc3")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3-rc2^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
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
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc2",
                            f"Resolved source ref: {expected_commit}",
                        ]
                    ),
                }
            ],
            create_tag_response={"sha": "tag-object-sha"},
            create_ref_response={"ref": "refs/tags/v1.2.3"},
        )
        completed = run_cli(
            [
                "create-final-tag",
                "--component-config",
                str(config_path),
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
        self.assertEqual("v1.2.3", manifest["final_tag"])
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("github-api", manifest["tag_creation_mode"])
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        create_tag_request = json.loads((gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        create_ref_request = json.loads((gh_state_dir / "create-ref-request.json").read_text(encoding="utf-8"))
        self.assertEqual("refs/tags/v1.2.3", create_ref_request["ref"])
        self.assertEqual("tag-object-sha", create_ref_request["sha"])

    def test_sync_draft_github_release_reuses_same_rc_without_deleting_assets(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "RC tag: v1.2.3-rc0",
                "Final tag: v1.2.3",
                f"Resolved source ref: {expected_commit}",
                "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/",
                "Final tag mode: rc-source-commit",
                "",
                "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
            ]
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": release_body,
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                }
            ],
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
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
        self.assertEqual("reused", manifest["sync_mode"])
        self.assertEqual([], manifest["deleted_release_ids"])
        self.assertFalse((gh_state_dir / "deleted-endpoints.log").exists())
        self.assertFalse((gh_state_dir / "create-release-request.json").exists())

    def test_sync_draft_github_release_retags_legacy_final_tag_release(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "RC tag: v1.2.3-rc0",
                "Final tag: v1.2.3",
                f"Resolved source ref: {expected_commit}",
                "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/",
                "Final tag mode: rc-source-commit",
                "",
                "This draft release is convenience metadata only and must remain unpublished until the ASF vote passes.",
            ]
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": release_body,
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
                }
            ],
            update_release_response={
                "id": 42,
                "draft": True,
                "tag_name": "v1.2.3-rc0",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
            },
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
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
        self.assertEqual("updated", manifest["sync_mode"])
        self.assertEqual("v1.2.3-rc0", manifest["release_tag"])
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("v1.2.3-rc0", update_request["tag_name"])
        self.assertEqual(expected_commit, update_request["target_commitish"])

    def test_sync_draft_github_release_rejects_higher_existing_rc(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc1",
                        ]
                    ),
                }
            ],
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
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
        self.assertIn("higher RC", completed.stderr)

    def test_finalize_draft_github_release_command_publishes_existing_draft(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "finalize-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0", "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "body": "\n".join(
                        [
                            "Draft GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "RC tag: v1.2.3-rc0",
                            f"Resolved source ref: {expected_commit}",
                        ]
                    ),
                    "assets": [
                        {"id": 201, "name": "rc-vote-manifest.json"},
                        {"id": 202, "name": "rc-vote-manifest.json.asc"},
                        {"id": 203, "name": "keep-me.txt"},
                    ],
                }
            ],
            update_release_response={
                "id": 42,
                "draft": False,
                "tag_name": "v1.2.3",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
            },
        )
        completed = run_cli(
            [
                "finalize-draft-github-release",
                "--component-config",
                str(config_path),
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
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3", manifest["release_tag"])
        self.assertEqual("published-draft", manifest["finalize_mode"])
        self.assertEqual(
            ["rc-vote-manifest.json", "rc-vote-manifest.json.asc"],
            manifest["deleted_asset_names"],
        )
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertFalse(update_request["draft"])
        self.assertFalse(update_request["prerelease"])
        self.assertEqual("v1.2.3", update_request["tag_name"])
        self.assertEqual(expected_commit, update_request["target_commitish"])
        self.assertEqual("Apache Buildish Example 1.2.3", update_request["name"])
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/assets/201",
                "repos/apache/buildish-example/releases/assets/202",
            ],
            (gh_state_dir / "deleted-asset-endpoints.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertIn(
            "Finalize draft GitHub Release",
            manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8"),
        )
