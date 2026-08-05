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
"""Secondary-target command integration tests."""

from pathlib import Path

from tests.release.commands.support import (
    ReleaseCommandsIntegrationTestSupport,
    cleanup_sandbox,
    cli_env,
    command_available,
    create_build_test_sandbox,
    create_fake_docker_launcher,
    create_fake_gh_launcher,
    fetch_git_origin_refs,
    git_create_branch,
    git_rev_parse,
    hashlib,
    init_git_origin_and_clone,
    json,
    os,
    run_cli,
    run_quiet,
    set_github_origin_url,
)


class SecondaryTargetCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Secondary-target command integration tests."""

    def test_update_moving_tags_command_updates_only_aliases_that_do_not_roll_back(
        self,
    ) -> None:
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
        run_quiet(
            ["git", "-C", str(origin_dir), "commit", "-m", "release 1.3.4"], check=True
        )
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
        run_quiet(
            ["git", "-C", str(origin_dir), "add", "release-1.2.3.txt"], check=True
        )
        run_quiet(
            ["git", "-C", str(origin_dir), "commit", "-m", "release 1.2.3"], check=True
        )
        run_quiet(
            ["git", "-C", str(origin_dir), "tag", "-a", "v1.2.3", "-m", "v1.2.3"],
            check=True,
        )
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/example-project")
        expected_commit = git_rev_parse(clone_dir, "v1.2.3^{commit}")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
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
        self.assertEqual(["v1.2"], manifest["updated_tags"])
        self.assertEqual(["v1"], manifest["skipped_tags"])
        create_tag_request = json.loads(
            (gh_state_dir / "create-tag-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("v1.2", create_tag_request["tag"])
        self.assertEqual(expected_commit, create_tag_request["object"])
        update_ref_request = json.loads(
            (gh_state_dir / "update-ref-request.json").read_text(encoding="utf-8")
        )
        self.assertEqual("moving-tag-object-sha", update_ref_request["sha"])
        requests_log = (gh_state_dir / "requests.log").read_text(encoding="utf-8")
        self.assertIn(
            "PATCH repos/apache/example-project/git/refs/tags/v1.2", requests_log
        )
        self.assertNotIn(
            "PATCH repos/apache/example-project/git/refs/tags/v1\n", requests_log
        )

    def test_update_moving_image_aliases_command_emits_derived_aliases(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "update-moving-image-aliases.json"
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
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
        self.assertEqual(["1", "1.2"], manifest["image_aliases"])

    def test_publish_dockerhub_moving_tags_command_creates_alias_refs(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "publish-dockerhub-moving-tags.json"
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
            secondary_targets=("dockerhub",),
        )
        completed = run_cli(
            [
                "publish-dockerhub-moving-tags",
                "--component-config",
                str(config_path),
                "1.2.3",
                "docker.io/apache/example-project:1.2.3",
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
        self.assertEqual(
            "docker.io/apache/example-project:1.2.3", manifest["source_image"]
        )
        self.assertEqual(
            "docker.io/apache/example-project", manifest["image_repository"]
        )
        self.assertEqual(
            [
                "docker.io/apache/example-project:1",
                "docker.io/apache/example-project:1.2",
            ],
            manifest["published_alias_refs"],
        )
        self.assertEqual(
            "buildish-bot",
            (docker_state_dir / "login-user.txt").read_text(encoding="utf-8").strip(),
        )
        self.assertEqual(
            "docker.io",
            (docker_state_dir / "login-registry.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )
        self.assertEqual(
            [
                "docker.io/apache/example-project:1|docker.io/apache/example-project:1.2.3|false",
                "docker.io/apache/example-project:1.2|docker.io/apache/example-project:1.2.3|false",
            ],
            (docker_state_dir / "imagetools-create.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )

    def test_attach_github_release_assets_command_uploads_assets_with_optional_sidecars(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest(
                "gpg is required for the GitHub Release asset-signing integration test"
            )
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "attach-github-release-assets.json"
        asset_path = sandbox_dir / "example-project.zip"
        source_home = sandbox_dir / "gpg-source"
        source_home.mkdir(parents=True, exist_ok=True)
        source_home.chmod(0o700)
        asset_path.write_bytes(b"release-asset\n")
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/example-project")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
            secondary_targets=("github-release-assets",),
        )
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3",
                    "name": "Apache Example Project 1.2.3",
                    "html_url": "https://github.com/apache/example-project/releases/tag/v1.2.3",
                }
            ],
            list_responses=[
                [
                    {
                        "id": 42,
                        "draft": True,
                        "tag_name": "v1.2.3",
                        "name": "Apache Example Project 1.2.3",
                        "html_url": "https://github.com/apache/example-project/releases/tag/v1.2.3",
                    }
                ],
                [
                    {
                        "id": 42,
                        "draft": True,
                        "tag_name": "v1.2.3",
                        "name": "Apache Example Project 1.2.3",
                        "html_url": "https://github.com/apache/example-project/releases/tag/v1.2.3",
                        "assets": [
                            {
                                "id": 91,
                                "name": asset_path.name,
                                "size": asset_path.stat().st_size,
                                "digest": "sha256:"
                                + hashlib.sha256(asset_path.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ],
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
        self.assertEqual(["example-project.zip"], manifest["primary_asset_names"])
        self.assertEqual(["sha512", "sha256"], manifest["checksum_algorithms"])
        self.assertIn(
            "example-project.zip.asc", manifest["generated_signature_asset_names"]
        )
        self.assertIn(
            "example-project.zip.sha512", manifest["generated_checksum_asset_names"]
        )
        self.assertIn(
            "example-project.zip.sha256", manifest["generated_checksum_asset_names"]
        )
        self.assertTrue(manifest["gpg_fingerprint"])

        self.assertTrue((asset_path.with_name("example-project.zip.asc")).is_file())
        self.assertEqual(
            [
                str(asset_path),
                str(asset_path.with_name("example-project.zip.sha512")),
                str(asset_path.with_name("example-project.zip.sha256")),
                str(asset_path.with_name("example-project.zip.asc")),
            ],
            (gh_state_dir / "release-upload-files.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertEqual(
            "v1.2.3",
            (gh_state_dir / "release-upload-tag.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )
        self.assertEqual(
            "apache/example-project",
            (gh_state_dir / "release-upload-repo.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )
        self.assertEqual(
            "true",
            (gh_state_dir / "release-upload-clobber.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )
        summary_text = manifest_path.with_suffix(".summary.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Attach GitHub Release assets", summary_text)
        self.assertIn("example-project.zip.sha512", summary_text)
        self.assertIn("example-project.zip.asc", summary_text)

        prepared_dir = sandbox_dir / "prepared-assets"
        prepared_manifest_path = sandbox_dir / "prepare-release-assets.json"
        completed = run_cli(
            [
                "prepare-release-assets",
                "--component-config",
                str(config_path),
                "--output-dir",
                str(prepared_dir),
                str(asset_path),
            ],
            cwd=clone_dir,
            env=cli_env(
                prepared_manifest_path,
                extra_env={"BUILDISH_GPG_PRIVATE_KEY": secret_key},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        prepared_manifest = json.loads(
            prepared_manifest_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            [
                "example-project.zip",
                "example-project.zip.sha512",
                "example-project.zip.asc",
            ],
            prepared_manifest["prepared_asset_names"],
        )
        self.assertEqual(
            b"release-asset\n", (prepared_dir / asset_path.name).read_bytes()
        )
        self.assertTrue((prepared_dir / "example-project.zip.sha512").is_file())
        self.assertTrue((prepared_dir / "example-project.zip.asc").is_file())

    def test_immutable_evidence_attachment_reuses_exact_assets(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir, clone_dir = init_git_origin_and_clone(sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        fetch_git_origin_refs(clone_dir)
        set_github_origin_url(clone_dir, "apache/example-project")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url=(
                "https://dist.apache.org/repos/dist/dev/incubator/example/example-project"
            ),
            release_base_url=(
                "https://dist.apache.org/repos/dist/release/incubator/example/example-project"
            ),
            secondary_targets=("github-release-assets",),
        )
        first = sandbox_dir / "buildish-verification-evidence--first.json"
        second = sandbox_dir / "buildish-verification-evidence--second.json"
        first.write_bytes(b"first evidence\n")
        second.write_bytes(b"second evidence\n")

        def asset(asset_id: int, path: object) -> dict[str, object]:
            asset_path = Path(str(path))
            return {
                "id": asset_id,
                "name": asset_path.name,
                "size": asset_path.stat().st_size,
                "digest": "sha256:"
                + hashlib.sha256(asset_path.read_bytes()).hexdigest(),
            }

        def release(assets: list[dict[str, object]]) -> dict[str, object]:
            return {
                "id": 42,
                "draft": False,
                "tag_name": "v1.2.3",
                "name": "Example Project 1.2.3",
                "html_url": (
                    "https://github.com/apache/example-project/releases/tag/v1.2.3"
                ),
                "assets": assets,
            }

        partial_release = release([asset(91, first)])
        complete_release = release([asset(91, first), asset(92, second)])
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=partial_release,
            list_responses=[[partial_release], [complete_release]],
        )
        first_manifest = sandbox_dir / "immutable-attachment-first.json"
        command = [
            "attach-github-release-assets",
            "--component-config",
            str(config_path),
            "--immutable",
            "1.2.3",
            str(first),
            str(second),
        ]
        completed = run_cli(
            command,
            cwd=clone_dir,
            env=cli_env(
                first_manifest,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        first_result = json.loads(first_manifest.read_text(encoding="utf-8"))
        self.assertEqual([second.name], first_result["uploaded_asset_names"])
        self.assertEqual(
            [str(second)],
            (gh_state_dir / "release-upload-files.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )
        self.assertEqual(
            "false",
            (gh_state_dir / "release-upload-clobber.txt")
            .read_text(encoding="utf-8")
            .strip(),
        )

        (gh_state_dir / "release-upload-files.log").unlink()
        second_manifest = sandbox_dir / "immutable-attachment-second.json"
        completed = run_cli(
            command,
            cwd=clone_dir,
            env=cli_env(
                second_manifest,
                extra_env={"FAKE_GH_STATE_DIR": str(gh_state_dir)},
                prepend_dirs=(gh_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        second_result = json.loads(second_manifest.read_text(encoding="utf-8"))
        self.assertEqual([], second_result["uploaded_asset_names"])
        self.assertFalse((gh_state_dir / "release-upload-files.log").exists())
