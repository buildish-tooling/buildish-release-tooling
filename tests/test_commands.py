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

"""Integration tests for the CLI command surface."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from apache_buildish_release_tooling.asf_svn import AsfSvnClient

from tests.support import (
    cli_env,
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    create_fake_docker_launcher,
    create_fake_gh_launcher,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    init_git_origin_and_clone,
    init_svn_repo_and_checkout,
    run_cli,
    set_github_origin_url,
)


class CommandsIntegrationTest(unittest.TestCase):
    """Verify high-level command behavior through the CLI entrypoint."""

    @staticmethod
    def _write_component_config(
        config_path: Path,
        *,
        component_id: str,
        dev_base_url: str,
        release_base_url: str,
        vote_release_name: str = "Apache Buildish Example",
        moving_tags_enabled: bool = True,
        latest_tag_enabled: bool = False,
        secondary_targets: tuple[str, ...] = ("github-action",),
        final_tag_mode: str = "rc-source-commit",
    ) -> None:
        """Write a minimal component configuration used by CLI integration tests."""

        config_path.write_text(
            "\n".join(
                [
                    f"component_id: {component_id}",
                    f"source_artifact_prefix: apache-{component_id}",
                    f"asf_dist_dev_base: {dev_base_url}",
                    f"asf_dist_release_base: {release_base_url}",
                    f"moving_tags_enabled: {'true' if moving_tags_enabled else 'false'}",
                    f"latest_tag_enabled: {'true' if latest_tag_enabled else 'false'}",
                    "secondary_targets:",
                    *[f"  - {target}" for target in secondary_targets],
                    f"final_tag_mode: {final_tag_mode}",
                    f"vote_release_name: {vote_release_name}",
                    "release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/",
                    "verify_rc_instructions: verify",
                    "prepare_rc_runs_tests: false",
                    "release_branch_ci_required: true",
                ]
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _stage_source_release_files(
        sandbox_dir: Path,
        working_copy_dir: Path,
        *,
        component_id: str,
        version: str,
        rc_number: int,
    ) -> None:
        """Stage the minimal ASF source-release files in one SVN working copy RC directory."""

        client = AsfSvnClient()
        subprocess.run(["svn", "update", str(working_copy_dir)], check=True, capture_output=True, text=True)
        artifact_name = f"apache-{component_id}-{version}-incubating-src.tar.gz"
        artifact_path = sandbox_dir / artifact_name
        artifact_path.write_bytes(b"dummy source payload\n")
        sha512_path = sandbox_dir / f"{artifact_name}.sha512"
        sha512_path.write_text(f"{'a' * 128}  {artifact_name}\n", encoding="utf-8")
        asc_path = sandbox_dir / f"{artifact_name}.asc"
        asc_path.write_text("-----BEGIN PGP SIGNATURE-----\n<dummy>\n-----END PGP SIGNATURE-----\n", encoding="utf-8")
        target_dir = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / f"{version}-rc{rc_number}"
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        for source_path, destination_name in (
            (artifact_path, artifact_name),
            (sha512_path, f"{artifact_name}.sha512"),
            (asc_path, f"{artifact_name}.asc"),
        ):
            destination_path = target_dir / destination_name
            destination_path.write_bytes(source_path.read_bytes())
            subprocess.run(
                ["svn", "add", "--force", str(destination_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        client.commit_working_copy(working_copy_dir, "stage source release files")

    def test_prepare_rc_command_uses_yaml_component_config(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "prepare-rc.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
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
        self.assertEqual(0, completed.returncode)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected_commit, manifest["resolved_source_ref"])
        self.assertEqual("release/1.2.x", manifest["resolved_release_branch"])
        self.assertEqual("3", manifest["rc_number"])
        self.assertEqual("v1.2.3-rc3", manifest["rc_tag"])

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

    def test_release_version_command_infers_release_line_and_pruning_from_svn(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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
        self.assertEqual("1.2.1,1.2.2", manifest["archive_versions"])

    def test_sync_draft_github_release_command_recreates_matching_draft_release(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
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
                "tag_name": "v1.2.3",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
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
        self.assertEqual("11,12", manifest["deleted_release_ids"])
        self.assertEqual("created", manifest["sync_mode"])
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3", manifest["release_tag"])
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
            manifest["release_url"],
        )
        create_request = json.loads(
            (gh_state_dir / "create-release-request.json").read_text(encoding="utf-8")
        )
        self.assertTrue(create_request["draft"])
        self.assertEqual("v1.2.3", create_request["tag_name"])
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
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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
        self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=2,
        )
        completed = run_cli(
            [
                "publish-source-release-svn",
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
        self.assertEqual("v1.2.3-rc2", manifest["selected_rc_tag"])
        self.assertEqual(["1.2.3/"], client.list_entries(release_base_url))
        self.assertEqual("copied", manifest["publish_mode"])
        rerun = run_cli(
            [
                "publish-source-release-svn",
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
        self.assertEqual(0, rerun.returncode, msg=rerun.stderr)
        rerun_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("already-present", rerun_manifest["publish_mode"])

    def test_publish_source_release_svn_command_rejects_missing_required_source_files(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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
        self.assertIn("missing required source release files", completed.stderr)
        self.assertEqual([], client.list_entries(release_base_url))

    def test_publish_source_release_svn_command_rejects_rc_drift(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, _working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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
        self.assertEqual("1.2.1,1.2.2", manifest["pruned_versions"])
        self.assertEqual(["1.2.3/", "1.3.0/"], client.list_entries(release_base_url))

    def test_create_final_tag_command_creates_remote_annotated_tag(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
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
                    "tag_name": "v1.2.3",
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

    def test_create_rc_materialization_tag_command_creates_local_rc_tag(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("source-commit", manifest["tag_target_origin"])
        self.assertEqual(expected_commit, git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}"))

    def test_create_rc_materialization_tag_command_fails_when_rc_tag_already_exists(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0", "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("tag already exists: v1.2.3-rc0", completed.stderr)

    def test_sync_draft_github_release_reuses_same_rc_without_deleting_assets(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
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
        self.assertEqual("reused", manifest["sync_mode"])
        self.assertEqual("", manifest["deleted_release_ids"])
        self.assertFalse((gh_state_dir / "deleted-endpoints.log").exists())
        self.assertFalse((gh_state_dir / "create-release-request.json").exists())

    def test_sync_draft_github_release_rejects_higher_existing_rc(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
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

    def test_update_moving_tags_command_updates_only_aliases_that_do_not_roll_back(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-tags.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        subprocess.run(
            ["git", "-C", str(origin_dir), "checkout", "-b", "line-1.3", "main"],
            check=True,
        )
        (origin_dir / "release-1.3.txt").write_text("1.3.4\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin_dir), "add", "release-1.3.txt"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "release 1.3.4"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.3.4", "-m", "v1.3.4"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1", "-m", "v1"],
            check=True,
        )
        subprocess.run(["git", "-C", str(origin_dir), "checkout", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.2", "-m", "v1.2.2"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2", "-m", "v1.2"],
            check=True,
        )
        (origin_dir / "release-1.2.3.txt").write_text("1.2.3\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin_dir), "add", "release-1.2.3.txt"], check=True)
        subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "release 1.2.3"], check=True)
        subprocess.run(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.3", "-m", "v1.2.3"],
            check=True,
        )
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3^{commit}")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("github-action",),
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[],
            create_tag_response={"sha": "moving-tag-object-sha"},
            update_ref_response={"ref": "refs/tags/v1.2"},
        )
        completed = run_cli(
            [
                "update-moving-tags",
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
        self.assertEqual(expected_commit, manifest["target_commit"])
        self.assertEqual("v1.2", manifest["updated_tags"])
        self.assertEqual("v1", manifest["skipped_tags"])
        create_tag_request = json.loads((gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8"))
        self.assertEqual("v1.2", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        update_ref_request = json.loads((gh_state_dir / "update-ref-request.json").read_text(encoding="utf-8"))
        self.assertEqual("moving-tag-object-sha", update_ref_request["sha"])
        requests_log = (gh_state_dir / "requests.log").read_text(encoding="utf-8")
        self.assertIn("PATCH repos/apache/buildish-example/git/refs/tags/v1.2", requests_log)
        self.assertNotIn("PATCH repos/apache/buildish-example/git/refs/tags/v1\n", requests_log)

    def test_update_moving_image_aliases_command_emits_derived_aliases(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-image-aliases.json"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("dockerhub",),
        )
        completed = run_cli(
            [
                "update-moving-image-aliases",
                "--component-config",
                str(config_path),
                "1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("1.2.3", manifest["exact_image_tag"])
        self.assertEqual("1 1.2", manifest["image_aliases"])

    def test_publish_dockerhub_moving_tags_command_creates_alias_refs(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-dockerhub-moving-tags.json"
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("dockerhub",),
        )
        completed = run_cli(
            [
                "publish-dockerhub-moving-tags",
                "--component-config",
                str(config_path),
                "1.2.3",
                "docker.io/apache/buildish-example:1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "DOCKERHUB_USER": "buildish-bot",
                    "DOCKERHUB_TOKEN": "super-secret-token",
                    "FAKE_DOCKER_STATE_DIR": str(docker_state_dir),
                },
                prepend_dirs=(docker_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("docker.io/apache/buildish-example:1.2.3", manifest["source_image"])
        self.assertEqual("docker.io/apache/buildish-example", manifest["image_repository"])
        self.assertEqual(
            "docker.io/apache/buildish-example:1 docker.io/apache/buildish-example:1.2",
            manifest["published_alias_refs"],
        )
        self.assertEqual(
            "buildish-bot",
            (docker_state_dir / "login-user.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "docker.io",
            (docker_state_dir / "login-registry.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            [
                "docker.io/apache/buildish-example:1|docker.io/apache/buildish-example:1.2.3|false",
                "docker.io/apache/buildish-example:1.2|docker.io/apache/buildish-example:1.2.3|false",
            ],
            (docker_state_dir / "imagetools-create.log").read_text(encoding="utf-8").splitlines(),
        )

    def test_attach_github_release_assets_command_uploads_assets_with_optional_sidecars(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for the GitHub Release asset-signing integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "attach-github-release-assets.json"
        asset_path = sandbox_dir / "buildish-example.zip"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)
        asset_path.write_bytes(b"release-asset\n")
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            secondary_targets=("github-release-assets",),
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
                }
            ],
        )

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout

        completed = run_cli(
            [
                "attach-github-release-assets",
                "--component-config",
                str(config_path),
                "--sign",
                "--checksum",
                "sha512",
                "--checksum",
                "sha256",
                "1.2.3",
                str(asset_path),
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("42", manifest["release_id"])
        self.assertEqual("v1.2.3", manifest["release_tag"])
        self.assertEqual("buildish-example.zip", manifest["primary_asset_names"])
        self.assertEqual("sha512,sha256", manifest["checksum_algorithms"])
        self.assertIn("buildish-example.zip.asc", manifest["generated_signature_asset_names"])
        self.assertIn("buildish-example.zip.sha512", manifest["generated_checksum_asset_names"])
        self.assertIn("buildish-example.zip.sha256", manifest["generated_checksum_asset_names"])
        self.assertTrue(manifest["gpg_fingerprint"])

        self.assertTrue((asset_path.with_name("buildish-example.zip.asc")).is_file())
        self.assertEqual(
            [
                str(asset_path),
                str(asset_path.with_name("buildish-example.zip.sha512")),
                str(asset_path.with_name("buildish-example.zip.sha256")),
                str(asset_path.with_name("buildish-example.zip.asc")),
            ],
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual(
            "v1.2.3",
            (gh_state_dir / "release-upload-tag.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "apache/buildish-example",
            (gh_state_dir / "release-upload-repo.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "true",
            (gh_state_dir / "release-upload-clobber.txt").read_text(encoding="utf-8").strip(),
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Attach GitHub Release assets", summary_text)
        self.assertIn("buildish-example.zip.sha512", summary_text)
        self.assertIn("buildish-example.zip.asc", summary_text)

    def test_finalize_draft_github_release_command_publishes_existing_draft(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
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
        self.assertEqual("rc-vote-manifest.json,rc-vote-manifest.json.asc", manifest["deleted_asset_names"])
        update_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertFalse(update_request["draft"])
        self.assertFalse(update_request["prerelease"])
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

    def test_finalize_rc_vote_materials_command_stages_manifest_and_mirrors_it(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for RC vote-manifest signing")
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        source_manifest_path = sandbox_dir / "build-source-rc.json"
        rc_tag_manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        secondary_manifest_path = sandbox_dir / "secondary-artifacts.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        keys_path = working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)

        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")

        subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        )
        public_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        secret_key = subprocess.run(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(source_home)},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        keys_path.write_text(public_key, encoding="utf-8")
        subprocess.run(["svn", "add", str(keys_path)], check=True)
        subprocess.run(["svn", "commit", "-m", "add KEYS", str(working_copy_dir)], check=True)
        secondary_manifest_path.write_text(
            json.dumps(
                {
                    "secondary_artifacts": [
                        {
                            "target_family": "github-release-assets",
                            "role": "bootstrap-convenience-archive",
                            "filename": "buildish-example-bootstrap.zip",
                            "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
                            "artifact_origin": "source-commit",
                            "git_commit_sha": git_rev_parse(clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"),
                            "checksums": {
                                "sha512": {
                                    "value": "deadbeef",
                                    "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip.sha512",
                                }
                            },
                            "signatures": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        completed = run_cli(
            [
                "build-source-rc",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                source_manifest_path,
                extra_env={"BUILDISH_GPG_PRIVATE_KEY": secret_key},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(rc_tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--secondary-artifact-manifest",
                str(secondary_manifest_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                finalize_manifest_path,
                extra_env={
                    "BUILDISH_GPG_PRIVATE_KEY": secret_key,
                    "FAKE_GH_STATE_DIR": str(gh_state_dir),
                },
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(finalize_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(
            f"{dev_base_url}/1.2.3-rc0/rc-vote-manifest.json",
            manifest["authoritative_manifest_url"],
        )
        self.assertIn("rc-vote-manifest.json.asc", manifest["mirrored_asset_names"])
        self.assertTrue(manifest["gpg_fingerprint"])
        self.assertEqual(
            [
                "rc-vote-manifest.json",
                "rc-vote-manifest.json.asc",
                "rc-vote-manifest.json.sha512",
            ],
            sorted(
                entry
                for entry in client.list_entries(f"{dev_base_url}/1.2.3-rc0")
                if entry.startswith("rc-vote-manifest.json")
            ),
        )
        staged_manifest = json.loads(
            subprocess.run(
                [
                    "svn",
                    "cat",
                    f"{dev_base_url}/1.2.3-rc0/rc-vote-manifest.json",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
        )
        self.assertEqual("rc-vote", staged_manifest["manifest_type"])
        self.assertEqual(component_id, staged_manifest["component_id"])
        self.assertEqual("v1.2.3-rc0", staged_manifest["rc_tag"])
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["uri"],
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3",
            staged_manifest["draft_github_release"]["url"],
        )
        self.assertEqual(
            [
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.sha512"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.asc"),
            ],
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines(),
        )
        summary_text = finalize_manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Finalize RC vote materials for version 1.2.3", summary_text)
        self.assertIn("### Technical details", summary_text)
        self.assertIn("### RC vote manifest", summary_text)
        self.assertIn('"manifest_type": "rc-vote"', summary_text)
        self.assertIn("Project vote subject", summary_text)
        self.assertIn("Please vote in the next 72 hours.", summary_text)
        self.assertIn(f"{release_base_url.rsplit('/', 1)[0]}/KEYS", summary_text)

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
