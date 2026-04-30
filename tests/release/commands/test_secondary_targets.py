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
"""Secondary-target command integration tests."""

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class SecondaryTargetCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Secondary-target command integration tests."""

    def test_update_moving_tags_command_updates_only_aliases_that_do_not_roll_back(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-tags.json"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        run_quiet(
            ["git", "-C", str(origin_dir), "checkout", "-b", "line-1.3", "main"],
            check=True,
        )
        (origin_dir / "release-1.3.txt").write_text("1.3.4\n", encoding="utf-8")
        run_quiet(["git", "-C", str(origin_dir), "add", "release-1.3.txt"], check=True)
        run_quiet(["git", "-C", str(origin_dir), "commit", "-m", "release 1.3.4"], check=True)
        run_quiet(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.3.4", "-m", "v1.3.4"],
            check=True,
        )
        run_quiet(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1", "-m", "v1"],
            check=True,
        )
        run_quiet(["git", "-C", str(origin_dir), "checkout", "main"], check=True)
        run_quiet(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.2", "-m", "v1.2.2"],
            check=True,
        )
        run_quiet(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2", "-m", "v1.2"],
            check=True,
        )
        (origin_dir / "release-1.2.3.txt").write_text("1.2.3\n", encoding="utf-8")
        run_quiet(["git", "-C", str(origin_dir), "add", "release-1.2.3.txt"], check=True)
        run_quiet(["git", "-C", str(origin_dir), "commit", "-m", "release 1.2.3"], check=True)
        run_quiet(
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

        run_quiet(
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
        secret_key = run_quiet(
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
