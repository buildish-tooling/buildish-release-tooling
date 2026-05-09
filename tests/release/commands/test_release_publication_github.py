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

"""GitHub release publication command tests."""

# ruff: noqa: F403, F405
from tests.release.commands.release_publication_support import (
    ReleasePublicationCommandTestBase,
)
from tests.release.commands.support import *


class GitHubReleasePublicationCommandIntegrationTest(ReleasePublicationCommandTestBase):
    """GitHub release publication command tests."""

    def test_sync_draft_github_release_command_recreates_matching_draft_release(
        self,
    ) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc2")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        (clone_dir / "DISCLAIMER").write_text(
            "Apache Buildish Example is an effort undergoing incubation.\n",
            encoding="utf-8",
        )
        expected_commit = git_rev_parse(
            clone_dir,
            "refs/remotes/origin/release/1.2.x^{commit}",
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            project_status="incubating",
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
        self.assertIn("## Incubating Disclaimer", create_request["body"])
        self.assertIn(
            "Apache Buildish Example is an effort undergoing incubation",
            create_request["body"],
        )
        self.assertIn("Candidate tag: v1.2.3-rc3", create_request["body"])
        self.assertIn(
            "ASF SVN staging URL: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc3/",
            create_request["body"],
        )
        deleted_endpoints = (
            (gh_state_dir / "deleted-endpoints.log")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/11",
                "repos/apache/buildish-example/releases/12",
            ],
            deleted_endpoints,
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Sync draft GitHub Release", summary_text)
        self.assertIn("id: 42", summary_text)

    def test_sync_draft_github_release_reuses_same_rc_without_deleting_assets(
        self,
    ) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "Candidate tag: v1.2.3-rc0",
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

    def test_sync_draft_github_release_can_publish_public_candidate_prerelease(
        self,
    ) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            candidate_start_number=1,
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[],
            create_response={
                "id": 42,
                "draft": False,
                "prerelease": True,
                "tag_name": "v1.2.3-alpha1",
                "name": "Apache Buildish Example 1.2.3",
                "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-alpha1",
            },
        )
        completed = run_cli(
            [
                "sync-draft-github-release",
                "--component-config",
                str(config_path),
                "--candidate-label",
                "alpha",
                "--candidate-visibility",
                "public-prerelease",
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
        self.assertEqual("v1.2.3-alpha1", manifest["rc_tag"])
        self.assertEqual("v1.2.3-alpha1", manifest["release_tag"])
        create_request = json.loads(
            (gh_state_dir / "create-release-request.json").read_text(encoding="utf-8")
        )
        self.assertFalse(create_request["draft"])
        self.assertTrue(create_request["prerelease"])
        self.assertEqual("v1.2.3-alpha1", create_request["tag_name"])
        self.assertEqual(expected_commit, create_request["target_commitish"])
        self.assertIn("Candidate tag: v1.2.3-alpha1", create_request["body"])
        self.assertIn("not an official ASF release", create_request["body"])

    def test_sync_draft_github_release_retags_legacy_final_tag_release(self) -> None:
        sandbox_dir, origin_dir, clone_dir = self._create_git_sandbox()
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "sync-draft-github-release.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/buildish-example")
        expected_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )
        release_body = "\n".join(
            [
                "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                "",
                "Candidate tag: v1.2.3-rc0",
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
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc1",
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

    def test_finalize_draft_github_release_command_publishes_existing_draft(
        self,
    ) -> None:
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
            project_status="incubating",
        )
        rc_vote_manifest_text = self._rc_vote_manifest_text(
            source_commit_sha=expected_commit,
            incubator_disclaimer_text="Apache Buildish Example is an effort undergoing incubation.",
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
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc0",
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
            release_asset_text_by_id={201: rc_vote_manifest_text},
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
        self.assertNotIn("Draft GitHub Release placeholder", update_request["body"])
        self.assertIn("## Incubating Disclaimer", update_request["body"])
        self.assertIn(
            "Apache Buildish Example is an effort undergoing incubation.",
            update_request["body"],
        )
        self.assertIn("## Authoritative Source Release", update_request["body"])
        self.assertIn(
            "https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example/1.2.3/",
            update_request["body"],
        )
        self.assertIn(
            "apache-buildish-example-1.2.3-incubating-src.tar.gz.asc",
            update_request["body"],
        )
        self.assertIn(
            "GitHub release assets are convenience artifacts and are not the authoritative ASF release.",
            update_request["body"],
        )
        self.assertEqual(
            [
                "repos/apache/buildish-example/releases/assets/201",
                "repos/apache/buildish-example/releases/assets/202",
            ],
            (gh_state_dir / "deleted-asset-endpoints.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertIn(
            "Finalize draft GitHub Release",
            manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8"),
        )
