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
"""npm package artifact-registration command tests."""

from buildish_release_tooling.release.contracts import (
    SecondaryArtifactManifestV1,
)

from tests.release.commands.artifact_registration_support import (
    ArtifactRegistrationCommandTestBase,
)
from tests.release.commands.support import (
    _read_simple_github_outputs,
    base64,
    cli_env,
    hashlib,
    json,
    run_cli,
)


class NpmPackageArtifactRegistrationCommandTest(ArtifactRegistrationCommandTestBase):
    """npm package artifact-registration command tests."""

    def test_record_artifact_npm_package_command_writes_manifest_bundle(self) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        component_id = "example-project"
        artifact_id = "npm-package-main"
        artifact_file_path = sandbox_dir / "dist" / "apache-example-project-1.2.3.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_bytes = b"npm package payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        expected_integrity = "sha512-" + base64.b64encode(
            hashlib.sha512(artifact_bytes).digest()
        ).decode("ascii")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "npm-package",
                "--artifact-id",
                artifact_id,
                "--role",
                "npm-package",
                "--file",
                str(artifact_file_path),
                "--registry-url",
                "https://registry.npmjs.org/",
                "--package-name",
                "@apache/example-project",
                "--package-version",
                "1.2.3",
                "--attestation-repository",
                "apache/example-project",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_bundle_dir = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
        )
        expected_manifest_path = expected_bundle_dir / "artifact-manifest.json"
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("npm-package", action_manifest["kind"])
        self.assertEqual(
            str(expected_manifest_path), action_manifest["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), action_manifest["artifact_bundle_dir"]
        )
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        validated_manifest = SecondaryArtifactManifestV1.model_validate(payload)
        self.assertEqual(
            artifact_id, validated_manifest.secondary_artifacts[0].artifact_id
        )
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "npm-package",
                    "role": "npm-package",
                    "filename": "example-project-1.2.3.tgz",
                    "uri": "https://registry.npmjs.org/@apache/example-project/-/example-project-1.2.3.tgz",
                    "registry_url": "https://registry.npmjs.org/",
                    "package_name": "@apache/example-project",
                    "version": "1.2.3",
                    "integrity": expected_integrity,
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha512": {
                            "value": expected_sha512,
                        }
                    },
                    "authenticity": {
                        "scheme": "npm-provenance",
                        "repository": "apache/example-project",
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("npm-package", github_outputs["artifact_kind"])
        self.assertEqual(
            str(expected_manifest_path), github_outputs["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), github_outputs["artifact_bundle_dir"]
        )

    def test_record_artifact_npm_package_command_derives_registry_metadata_from_canonical_uri(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        component_id = "example-project"
        artifact_id = "npm-package-main"
        artifact_file_path = sandbox_dir / "dist" / "local-package.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_bytes = b"npm package payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        expected_integrity = "sha512-" + base64.b64encode(
            hashlib.sha512(artifact_bytes).digest()
        ).decode("ascii")
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "npm-package",
                "--artifact-id",
                artifact_id,
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://registry.npmjs.org/@apache/example-project/-/example-project-1.2.3.tgz",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_manifest_path = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / component_id
            / "secondary-artifacts"
            / artifact_id
            / "artifact-manifest.json"
        )

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        validated_manifest = SecondaryArtifactManifestV1.model_validate(payload)
        self.assertEqual(
            artifact_id, validated_manifest.secondary_artifacts[0].artifact_id
        )
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "npm-package",
                    "filename": "example-project-1.2.3.tgz",
                    "uri": "https://registry.npmjs.org/@apache/example-project/-/example-project-1.2.3.tgz",
                    "registry_url": "https://registry.npmjs.org/",
                    "package_name": "@apache/example-project",
                    "version": "1.2.3",
                    "integrity": expected_integrity,
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha512": {
                            "value": expected_sha512,
                        }
                    },
                }
            ],
            payload["secondary_artifacts"],
        )

    def test_record_artifact_npm_package_rejects_mismatched_explicit_integrity(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        artifact_file_path = sandbox_dir / "dist" / "example-project-1.2.3.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"npm package payload\n")
        mismatched_integrity = "sha512-" + base64.b64encode(bytes(64)).decode("ascii")
        self._write_component_config(
            config_path,
            component_id="example-project",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/example/example-project",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/example/example-project",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "npm-package",
                "--artifact-id",
                "npm-package-main",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://registry.npmjs.org/@apache/example-project/-/example-project-1.2.3.tgz",
                "--integrity",
                mismatched_integrity,
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "npm-package --integrity does not match the bytes of --file",
            completed.stderr,
        )
