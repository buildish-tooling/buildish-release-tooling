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
"""Materialization command integration tests."""

from tests.release.commands.support import (
    ReleaseCommandsIntegrationTestSupport,
    _read_simple_github_outputs,
    cleanup_sandbox,
    cli_env,
    create_build_test_sandbox,
    fetch_git_origin_refs,
    git_create_annotated_tag,
    git_create_branch,
    git_rev_parse,
    init_git_origin_and_clone,
    json,
    re,
    run_cli,
    subprocess,
)


class MaterializationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Materialization command integration tests."""

    def test_create_rc_materialization_tag_command_creates_local_rc_tag(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "create-rc-materialization-tag.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        expected_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )
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
        self.assertEqual(
            expected_commit, git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}")
        )

    def test_materialize_rc_git_content_command_generates_default_temp_ref_and_stages_repeatable_paths(
        self,
    ) -> None:
        _sandbox_dir, origin_dir, clone_dir, config_path = (
            self._prepare_detached_materialization_repo()
        )
        manifest_path = config_path.parent / "materialize-rc-git-content.json"
        github_output_path = config_path.parent / "materialize-rc-git-content.outputs"
        resolved_source_ref = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )
        materialized_ref_name = (
            "refs/heads/buildish-internal/materialized/v1.2.3-rc0/12345-6"
        )

        completed = run_cli(
            [
                "materialize-rc-git-content",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--materialized-path",
                "dist",
                "--materialized-path",
                "NOTICE.generated",
                "--run-command",
                (
                    "mkdir -p dist && printf 'payload\\n' > dist/release.txt && "
                    "printf 'generated notice\\n' > NOTICE.generated"
                ),
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "GITHUB_OUTPUT": str(github_output_path),
                    "GITHUB_RUN_ID": "12345",
                    "GITHUB_RUN_ATTEMPT": "6",
                },
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(resolved_source_ref, manifest["resolved_source_ref"])
        self.assertEqual(["dist", "NOTICE.generated"], manifest["materialized_paths"])
        self.assertEqual(materialized_ref_name, manifest["materialized_ref_name"])
        self.assertEqual("pushed", manifest["materialized_ref_mode"])
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(
            manifest["materialized_commit_sha"],
            github_outputs["materialized_commit_sha"],
        )
        self.assertEqual(materialized_ref_name, github_outputs["materialized_ref_name"])
        self.assertNotEqual(resolved_source_ref, manifest["materialized_commit_sha"])
        self.assertEqual(
            manifest["materialized_commit_sha"],
            git_rev_parse(origin_dir, f"{materialized_ref_name}^{{commit}}"),
        )
        materialized_payload = subprocess.run(
            [
                "git",
                "-C",
                str(clone_dir),
                "show",
                f"{manifest['materialized_commit_sha']}:dist/release.txt",
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertEqual("payload\n", materialized_payload)
        materialized_notice = subprocess.run(
            [
                "git",
                "-C",
                str(clone_dir),
                "show",
                f"{manifest['materialized_commit_sha']}:NOTICE.generated",
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        self.assertEqual("generated notice\n", materialized_notice)
        source_payload = subprocess.run(
            [
                "git",
                "-C",
                str(clone_dir),
                "show",
                f"{resolved_source_ref}:dist/release.txt",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, source_payload.returncode)
        self.assertIn(
            "Materialize RC Git content",
            manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8"),
        )

    def test_create_rc_materialization_tag_command_can_cleanup_generated_materialized_ref(
        self,
    ) -> None:
        _sandbox_dir, origin_dir, clone_dir, config_path = (
            self._prepare_detached_materialization_repo()
        )
        materialize_manifest_path = (
            config_path.parent / "materialize-rc-git-content.json"
        )
        tag_manifest_path = config_path.parent / "create-rc-materialization-tag.json"

        completed = run_cli(
            [
                "materialize-rc-git-content",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--materialized-path",
                "dist",
                "--run-command",
                "mkdir -p dist && printf 'payload\\n' > dist/release.txt",
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(materialize_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        materialize_manifest = json.loads(
            materialize_manifest_path.read_text(encoding="utf-8")
        )
        materialized_ref_name = materialize_manifest["materialized_ref_name"]
        self.assertRegex(
            materialized_ref_name,
            rf"^refs/heads/buildish-internal/materialized/v1\.2\.3-rc0/"
            rf"{re.escape(materialize_manifest['resolved_source_ref'][:12])}-[0-9a-f]{{8}}$",
        )

        completed = run_cli(
            [
                "create-rc-materialization-tag",
                "--component-config",
                str(config_path),
                "--rc-tag",
                "v1.2.3-rc0",
                "--target-commit",
                materialize_manifest["materialized_commit_sha"],
                "--cleanup-materialized-ref-name",
                materialized_ref_name,
                "1.2.3",
            ],
            cwd=clone_dir,
            env=cli_env(tag_manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        manifest = json.loads(tag_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("v1.2.3-rc0", manifest["rc_tag"])
        self.assertEqual(
            materialize_manifest["materialized_commit_sha"], manifest["target_commit"]
        )
        self.assertEqual("deleted", manifest["cleanup_materialized_ref_mode"])
        self.assertEqual(
            materialized_ref_name, manifest["cleanup_materialized_ref_name"]
        )
        self.assertEqual(
            materialize_manifest["materialized_commit_sha"],
            git_rev_parse(clone_dir, "v1.2.3-rc0^{commit}"),
        )
        remote_ref_check = subprocess.run(
            [
                "git",
                "-C",
                str(origin_dir),
                "show-ref",
                "--verify",
                "--quiet",
                materialized_ref_name,
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(1, remote_ref_check.returncode)

    def test_create_rc_materialization_tag_command_fails_when_rc_tag_already_exists(
        self,
    ) -> None:
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
