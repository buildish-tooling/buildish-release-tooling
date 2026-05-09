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
"""RC vote-material command integration tests."""

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class VoteMaterialsCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """RC vote-material command integration tests."""

    _baseline_root: Path
    _origin_template: Path
    _svn_repo_template: Path
    _public_key: str
    _secret_key: str
    _finalize_origin_template: Path
    _finalize_svn_repo_template: Path

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        if not command_available("gpg"):
            raise unittest.SkipTest("gpg is required for RC vote-manifest signing")
        if not command_available("svnadmin") or not command_available("svn"):
            raise unittest.SkipTest("svnadmin and svn are required for the SVN integration test")
        cls._baseline_root = create_build_test_sandbox()
        cls._origin_template = init_git_origin_repo(cls._baseline_root, dir_name="origin-template")
        cls._svn_repo_template, _repo_url = init_svn_repo(cls._baseline_root, dir_name="svnrepo-template")
        gpg_home = cls._baseline_root / "gpg-source"
        gpg_home.mkdir(parents=True, exist_ok=True)
        gpg_home.chmod(0o700)
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
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        )
        cls._public_key = run_quiet(
            [
                "gpg",
                "--armor",
                "--export",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        ).stdout
        cls._secret_key = run_quiet(
            [
                "gpg",
                "--armor",
                "--export-secret-keys",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
            ],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        ).stdout
        cls._finalize_origin_template = cls._build_finalize_origin_template()
        cls._finalize_svn_repo_template = cls._build_finalize_svn_repo_template()

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_sandbox(cls._baseline_root)
        super().tearDownClass()

    def _create_vote_materials_sandbox(self) -> tuple[Path, Path, Path, Path, str, Path]:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir = copy_test_tree(self._origin_template, sandbox_dir / "origin")
        clone_dir = clone_git_origin(origin_dir, sandbox_dir / "clone")
        repo_dir = copy_test_tree(self._svn_repo_template, sandbox_dir / "svnrepo")
        working_copy_dir = sandbox_dir / "svnwc"
        repo_url = checkout_svn_repo(repo_dir, working_copy_dir)
        return sandbox_dir, origin_dir, clone_dir, repo_dir, repo_url, working_copy_dir

    @classmethod
    def _build_finalize_origin_template(cls) -> Path:
        """Build one reusable Git origin template for finalize-RC vote-material scenarios."""

        origin_dir = init_git_origin_repo(cls._baseline_root / "finalize-rc-family", dir_name="origin-template")
        git_create_branch(origin_dir, "release/1.x")
        git_create_branch(origin_dir, "release/1.2.x")
        git_create_annotated_tag(origin_dir, "v1.2.3-rc0")
        return origin_dir

    @classmethod
    def _build_finalize_svn_repo_template(cls) -> Path:
        """Build one reusable SVN repository template with staged RC source artifacts and KEYS."""

        family_root = cls._baseline_root / "finalize-rc-family"
        repo_dir, repo_url = init_svn_repo(family_root, dir_name="svnrepo-template")
        working_copy_dir = family_root / "svnwc-template"
        checkout_svn_repo(repo_dir, working_copy_dir)
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        keys_path = working_copy_dir / "dist" / "release" / "incubator" / "buildish" / "KEYS"
        client.mkdir_url(dev_base_url, "create dev component path")
        client.mkdir_url(release_base_url, "create release component path")
        keys_path.write_text(cls._public_key, encoding="utf-8")
        run_quiet(["svn", "add", str(keys_path)], check=True)
        run_quiet(["svn", "commit", "-m", "add KEYS", str(working_copy_dir)], check=True)
        cls._stage_source_release_files(
            family_root,
            working_copy_dir,
            component_id=component_id,
            version="1.2.3",
            rc_number=0,
        )
        return repo_dir

    def _create_finalize_vote_materials_sandbox(
        self,
    ) -> tuple[Path, Path, Path, Path, str, Path]:
        """Create one disposable sandbox from the cached finalize-RC staging family."""

        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        origin_dir = copy_test_tree(self._finalize_origin_template, sandbox_dir / "origin")
        clone_dir = clone_git_origin(origin_dir, sandbox_dir / "clone")
        fetch_git_origin_refs(clone_dir)
        repo_dir = copy_test_tree(self._finalize_svn_repo_template, sandbox_dir / "svnrepo")
        working_copy_dir = sandbox_dir / "svnwc"
        repo_url = checkout_svn_repo(repo_dir, working_copy_dir)
        return sandbox_dir, origin_dir, clone_dir, repo_dir, repo_url, working_copy_dir

    def test_finalize_rc_vote_materials_command_stages_manifest_and_mirrors_it(self) -> None:
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, working_copy_dir = (
            self._create_finalize_vote_materials_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        record_artifact_manifest_path = sandbox_dir / "record-artifact.json"
        record_artifact_outputs_path = sandbox_dir / "record-artifact.outputs"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        (clone_dir / "DISCLAIMER").write_text(
            "Apache Buildish Example is an effort undergoing incubation.\n",
            encoding="utf-8",
        )

        expected_source_date_epoch = int(
            run_quiet(
                [
                    "git",
                    "-C",
                    str(clone_dir),
                    "show",
                    "-s",
                    "--format=%ct",
                    "refs/remotes/origin/release/1.2.x^{commit}",
                ],
                check=True,
            ).stdout.strip()
        )
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
            project_status="incubating",
            verify_rc_lines=(
                "verify_rc:",
                "  source:",
                "    reproducibility:",
                "      profile_id: source-release",
                "      mode: exact-bytes",
                "  profiles:",
                "    source-release:",
                "      kind: source-artifact",
                "      build:",
                "        command: [\"./buildish-release-tooling/rebuild-source.sh\"]",
                "        output_globs:",
                "          - target/apache-example-*.tar.gz",
                "      comparison:",
                "        mode: exact-bytes",
            ),
        )
        secret_key = self._secret_key
        bootstrap_asset_path = sandbox_dir / "buildish-example-bootstrap.zip"
        bootstrap_asset_path.write_bytes(b"bootstrap payload\n")
        expected_secondary_commit = git_rev_parse(
            clone_dir, "refs/remotes/origin/release/1.2.x^{commit}"
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--kind",
                "generic-file",
                "--artifact-id",
                "bootstrap-zip",
                "--role",
                "bootstrap-convenience-archive",
                "--file",
                str(bootstrap_asset_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
                "--sha512-uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip.sha512",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                expected_secondary_commit,
            ],
            cwd=clone_dir,
            env=cli_env(
                record_artifact_manifest_path,
                extra_env={"GITHUB_OUTPUT": str(record_artifact_outputs_path)},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        secondary_manifest_path = Path(
            _read_simple_github_outputs(record_artifact_outputs_path)["artifact_manifest_path"]
        )

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
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
        self.assertEqual(
            f"{dev_base_url}/1.2.3-rc0/verify-rc-bootstrap.sh",
            manifest["bootstrap_script_url"],
        )
        self.assertIn("rc-vote-manifest.json.asc", manifest["mirrored_asset_names"])
        self.assertIn("verify-rc-bootstrap.sh.asc", manifest["mirrored_asset_names"])
        self.assertTrue(manifest["gpg_fingerprint"])
        self.assertEqual(
            [
                "rc-vote-manifest.json",
                "rc-vote-manifest.json.asc",
                "rc-vote-manifest.json.sha512",
                "verify-rc-bootstrap.sh",
                "verify-rc-bootstrap.sh.asc",
                "verify-rc-bootstrap.sh.sha512",
            ],
            sorted(
                entry
                for entry in client.list_entries(f"{dev_base_url}/1.2.3-rc0")
                if entry.startswith("rc-vote-manifest.json") or entry.startswith("verify-rc-bootstrap.sh")
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
        self.assertEqual("DISCLAIMER", staged_manifest["incubator_disclaimer"]["source_path"])
        self.assertEqual(
            "Apache Buildish Example is an effort undergoing incubation.",
            staged_manifest["incubator_disclaimer"]["text"],
        )
        self.assertEqual(expected_source_date_epoch, staged_manifest["source_date_epoch"])
        self.assertEqual(
            "source-release",
            staged_manifest["vote_materials"]["source_artifacts"][0]["reproducibility"]["profile_id"],
        )
        self.assertEqual(
            "bootstrap-zip",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["artifact_id"],
        )
        self.assertEqual(
            "generic-file",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["kind"],
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/download/v1.2.3/buildish-example-bootstrap.zip",
            staged_manifest["vote_materials"]["secondary_artifacts"][0]["uri"],
        )
        self.assertEqual(
            "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
            staged_manifest["draft_github_release"]["url"],
        )
        self.assertEqual("v1.2.3-rc0", staged_manifest["draft_github_release"]["tag"])
        self.assertEqual(
            [
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.sha512"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "rc-vote-manifest.json.asc"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "verify-rc-bootstrap.sh"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "verify-rc-bootstrap.sh.sha512"),
                str(clone_dir / "build" / "release-artifacts" / component_id / "verify-rc-bootstrap.sh.asc"),
            ],
            (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual(
            "v1.2.3-rc0",
            (gh_state_dir / "release-upload-tag.txt").read_text(encoding="utf-8").strip(),
        )
        update_release_request = json.loads(
            (gh_state_dir / "update-release-request.json").read_text(encoding="utf-8")
        )
        self.assertIn("## Incubating Disclaimer", update_release_request["body"])
        self.assertIn("Apache Buildish Example is an effort undergoing incubation", update_release_request["body"])
        self.assertIn("Verify RC bootstrap one-liner:", update_release_request["body"])
        self.assertIn("verify-rc-bootstrap.sh", update_release_request["body"])
        summary_text = finalize_manifest_path.with_suffix(".summary.md").read_text(encoding="utf-8")
        self.assertIn("Finalize RC vote materials for version 1.2.3", summary_text)
        self.assertIn("### Technical details", summary_text)
        self.assertIn("### RC vote manifest", summary_text)
        self.assertIn("### Verification bootstrap one-liner", summary_text)
        self.assertIn('"manifest_type": "rc-vote"', summary_text)
        self.assertIn("Project vote subject", summary_text)
        self.assertIn("Incubating disclaimer:", summary_text)
        self.assertIn("Verification bootstrap convenience:", summary_text)
        self.assertIn("Please vote in the next 72 hours.", summary_text)
        self.assertIn(f"{release_base_url.rsplit('/', 1)[0]}/KEYS", summary_text)

    def test_finalize_rc_vote_materials_command_stages_maven_repository_inventory(self) -> None:
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, working_copy_dir = (
            self._create_finalize_vote_materials_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        record_artifact_manifest_path = sandbox_dir / "record-artifact.json"
        record_artifact_outputs_path = sandbox_dir / "record-artifact.outputs"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        client = AsfSvnClient()
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"

        expected_source_date_epoch = int(
            run_quiet(
                [
                    "git",
                    "-C",
                    str(clone_dir),
                    "show",
                    "-s",
                    "--format=%ct",
                    "refs/remotes/origin/release/1.2.x^{commit}",
                ],
                check=True,
            ).stdout.strip()
        )
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )

        secret_key = self._secret_key

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
                "--kind",
                "maven-repository",
                "--artifact-id",
                "maven-staging-main",
                "--role",
                "maven-staging",
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--inventory-workers",
                "1",
            ],
            cwd=clone_dir,
            env=cli_env(
                record_artifact_manifest_path,
                extra_env={"GITHUB_OUTPUT": str(record_artifact_outputs_path)},
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        secondary_manifest_path = Path(
            _read_simple_github_outputs(record_artifact_outputs_path)["artifact_manifest_path"]
        )
        local_inventory_path = secondary_manifest_path.parent / "maven-staging-main-inventory.json"

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
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
        secondary_artifact = staged_manifest["vote_materials"]["secondary_artifacts"][0]
        self.assertEqual(expected_source_date_epoch, staged_manifest["source_date_epoch"])
        self.assertEqual("maven-repository", secondary_artifact["kind"])
        self.assertEqual("maven-staging-main", secondary_artifact["artifact_id"])
        self.assertEqual(staging_repository_id, secondary_artifact["staging_repository_id"])
        self.assertEqual(base_url, secondary_artifact["base_url"])
        self.assertEqual("maven-staging-main-inventory.json", secondary_artifact["inventory"]["filename"])
        self.assertEqual(
            f"{dev_base_url}/1.2.3-rc0/maven-staging-main-inventory.json",
            secondary_artifact["inventory"]["uri"],
        )
        self.assertEqual(
            hashlib.sha512(local_inventory_path.read_bytes()).hexdigest(),
            secondary_artifact["inventory"]["sha512"],
        )
        self.assertIn(
            "maven-staging-main-inventory.json",
            client.list_entries(f"{dev_base_url}/1.2.3-rc0"),
        )
        staged_inventory = json.loads(
            subprocess.run(
                [
                    "svn",
                    "cat",
                    f"{dev_base_url}/1.2.3-rc0/maven-staging-main-inventory.json",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout
        )
        self.assertEqual(
            json.loads(local_inventory_path.read_text(encoding="utf-8")),
            staged_inventory,
        )
        uploaded_paths = (gh_state_dir / "release-upload-files.log").read_text(encoding="utf-8").splitlines()
        self.assertIn(str(local_inventory_path), uploaded_paths)

    def test_finalize_rc_vote_materials_rejects_staged_source_artifact_drift(self) -> None:
        sandbox_dir, origin_dir, clone_dir, _repo_dir, repo_url, working_copy_dir = (
            self._create_finalize_vote_materials_sandbox()
        )
        config_path = sandbox_dir / "component.yaml"
        finalize_manifest_path = sandbox_dir / "finalize-rc-vote-materials.json"
        component_id = "buildish-example"
        dev_base_url = f"{repo_url}/dist/dev/incubator/buildish/{component_id}"
        release_base_url = f"{repo_url}/dist/release/incubator/buildish/{component_id}"

        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=dev_base_url,
            release_base_url=release_base_url,
        )

        secret_key = self._secret_key

        run_quiet(["svn", "update", str(working_copy_dir)], check=True)
        drifted_artifact = (
            working_copy_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / "1.2.3-rc0"
            / "apache-buildish-example-1.2.3-incubating-src.tar.gz"
        )
        drifted_artifact.write_bytes(b"drifted source payload\n")
        run_quiet(["svn", "commit", "-m", "drift staged artifact", str(working_copy_dir)], check=True)

        set_github_origin_url(clone_dir, "apache/buildish-example")
        gh_path, gh_state_dir = create_fake_gh_launcher(
            sandbox_dir,
            list_response=[
                {
                    "id": 42,
                    "draft": True,
                    "tag_name": "v1.2.3-rc0",
                    "name": "Apache Buildish Example 1.2.3",
                    "html_url": "https://github.com/apache/buildish-example/releases/tag/v1.2.3-rc0",
                    "body": "\n".join(
                        [
                            "Candidate GitHub Release placeholder for Apache Buildish Example 1.2.3.",
                            "",
                            "Candidate tag: v1.2.3-rc0",
                            f"Resolved source ref: {git_rev_parse(clone_dir, 'v1.2.3-rc0^{commit}')}",
                        ]
                    ),
                    "assets": [],
                }
            ],
        )
        completed = run_cli(
            [
                "finalize-rc-vote-materials",
                "--component-config",
                str(config_path),
                "--allow-non-production-release-targets",
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
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "staged source artifact .sha512 sidecar does not match the staged source artifact bytes",
            completed.stderr,
        )
