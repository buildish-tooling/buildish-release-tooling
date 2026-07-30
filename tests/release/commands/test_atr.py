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
"""ATR command integration tests."""

from tests.release.commands.support import (
    AsfSvnClient,
    ReleaseCommandsIntegrationTestSupport,
    cleanup_sandbox,
    cli_env,
    command_available,
    create_build_test_sandbox,
    create_fake_atr_launcher,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    init_git_origin_and_clone,
    init_svn_repo_and_checkout,
    json,
    run_cli,
)


class AtrCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """ATR command integration tests."""

    def test_publish_atr_candidate_command_uploads_staged_candidate_files(self) -> None:
        if not command_available("svnadmin") or not command_available("svn"):
            self.skipTest("svnadmin and svn are required for the SVN integration test")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        _repo_dir, repo_url, working_copy_dir = init_svn_repo_and_checkout(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-atr-candidate.json"
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: false",
                "  source_artifact_paths:",
                '    - "**/*-src.tar.gz"',
            ),
        )
        AsfSvnClient().mkdir_url(dev_base_url, "create dev component path")
        AsfSvnClient().mkdir_url(release_base_url, "create release component path")
        artifact_sha512 = self._stage_source_release_files(
            sandbox_dir,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=0,
        )
        self._stage_rc_vote_manifest_files(
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=0,
            repo_url=repo_url,
            artifact_sha512=artifact_sha512,
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        completed = run_cli(
            [
                "publish-atr-candidate",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--wait-for-checks",
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 6\n  success: 6\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("buildish-example", manifest["atr_project"])
        self.assertEqual("created", manifest["atr_release_mode"])
        self.assertEqual("00007", manifest["atr_latest_revision"])
        self.assertEqual("true", manifest["waited_for_checks"])
        self.assertEqual("6", manifest["atr_total_checks"])
        self.assertEqual(
            [
                "apache-buildish-example-1.2.3-incubating-src.tar.gz",
                "apache-buildish-example-1.2.3-incubating-src.tar.gz.sha512",
                "apache-buildish-example-1.2.3-incubating-src.tar.gz.asc",
                "rc-vote-manifest.json",
                "rc-vote-manifest.json.sha512",
                "rc-vote-manifest.json.asc",
            ],
            (atr_state_dir / "upload-paths.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertIn(
            "release-test.apache.org",
            (atr_state_dir / "seen-hosts.log").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "wave",
            (atr_state_dir / "seen-asf-uids.log").read_text(encoding="utf-8"),
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Publish ATR candidate", summary_text)
        self.assertIn("Total checks: 6", summary_text)

    def test_report_atr_checks_command_is_advisory_when_strict_checking_is_disabled(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "report-atr-checks.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: false",
            ),
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        (atr_state_dir / "state.json").write_text(
            json.dumps(
                {
                    "releases": {
                        "buildish-example/1.2.3": {
                            "project": "buildish-example",
                            "version": "1.2.3",
                            "phase": "release_candidate_draft",
                            "latest_revision_number": "00007",
                            "next_revision": 8,
                            "uploads": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "report-atr-checks",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 3\n  failure: 1\n  warning: 1\n  success: 1\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("00007", manifest["atr_reported_revision"])
        self.assertEqual("1", manifest["atr_failure_count"])
        self.assertEqual("false", manifest["would_block_release"])

    def test_report_atr_checks_command_fails_when_strict_checking_is_enabled(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "report-atr-checks.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        fetch_git_origin_refs(clone_dir)
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            atr_lines=(
                "atr:",
                "  enabled: true",
                "  base_url: https://release-test.apache.org",
                "  committee: buildish",
                "  product_line: buildish-example",
                "  strict_checking: true",
            ),
        )
        atr_path, atr_state_dir = create_fake_atr_launcher(sandbox_dir)
        (atr_state_dir / "state.json").write_text(
            json.dumps(
                {
                    "releases": {
                        "buildish-example/1.2.3": {
                            "project": "buildish-example",
                            "version": "1.2.3",
                            "phase": "release_candidate_draft",
                            "latest_revision_number": "00007",
                            "next_revision": 8,
                            "uploads": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "report-atr-checks",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "BUILDISH_ATR_ASF_UID": "wave",
                    "BUILDISH_ATR_PAT": "secret-pat",
                    "FAKE_ATR_STATE_DIR": str(atr_state_dir),
                    "FAKE_ATR_STATUS_OUTPUT": "Total checks: 3\n  failure: 1\n  warning: 1\n  success: 1\n",
                },
                prepend_dirs=(atr_path.parent,),
            ),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn("ATR strict checking is enabled", completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("true", manifest["would_block_release"])
        summary_text = manifest_path.with_suffix(".summary.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Report ATR checks", summary_text)
        self.assertIn("failure: 1", summary_text)
