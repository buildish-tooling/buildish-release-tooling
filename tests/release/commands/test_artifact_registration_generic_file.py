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
"""Generic-file artifact-registration command tests."""

from buildish_release_tooling.release.contracts import (
    SecondaryArtifactManifestV1,
)

from tests.release.commands.artifact_registration_support import (
    ArtifactRegistrationCommandTestBase,
)
from tests.release.commands.support import (
    _read_simple_github_outputs,
    cli_env,
    hashlib,
    json,
    run_cli,
)


class GenericFileArtifactRegistrationCommandTest(ArtifactRegistrationCommandTestBase):
    """Generic-file artifact-registration command tests."""

    def test_record_artifact_generic_file_command_writes_registration_bundle(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        component_id = "example-project"
        artifact_id = "bootstrap-zip"
        artifact_file_path = sandbox_dir / "example-project-bootstrap.zip"
        artifact_bytes = b"bootstrap payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
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
                "generic-file",
                "--artifact-id",
                artifact_id,
                "--role",
                "bootstrap-convenience-archive",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/example-project/releases/download/v1.2.3-rc0/example-project-bootstrap.zip",
                "--sha512-uri",
                "https://github.com/apache/example-project/releases/download/v1.2.3-rc0/example-project-bootstrap.zip.sha512",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
                "--reproducibility-profile-id",
                "bootstrap-zip",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}
            ),
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
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("generic-file", action_manifest["kind"])
        self.assertEqual(
            str(expected_manifest_path), action_manifest["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_manifest_path.parent), action_manifest["artifact_bundle_dir"]
        )
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self._assert_secondary_artifact_entry_shape(
            payload,
            expected_entry_keys=[
                "artifact_id",
                "kind",
                "role",
                "artifact_origin",
                "git_commit_sha",
                "reproducibility",
                "filename",
                "uri",
                "checksums",
                "signatures",
            ],
        )
        validated_manifest = SecondaryArtifactManifestV1.model_validate(payload)
        self.assertEqual(
            artifact_id,
            validated_manifest.secondary_artifacts[0].artifact_id,
        )
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "generic-file",
                    "role": "bootstrap-convenience-archive",
                    "filename": "example-project-bootstrap.zip",
                    "uri": "https://github.com/apache/example-project/releases/download/v1.2.3-rc0/example-project-bootstrap.zip",
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "reproducibility": {
                        "profile_id": "bootstrap-zip",
                    },
                    "checksums": {
                        "sha512": {
                            "value": expected_sha512,
                            "uri": "https://github.com/apache/example-project/releases/download/v1.2.3-rc0/example-project-bootstrap.zip.sha512",
                        }
                    },
                    "signatures": [],
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("generic-file", github_outputs["artifact_kind"])
        self.assertEqual(
            str(expected_manifest_path), github_outputs["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_manifest_path.parent), github_outputs["artifact_bundle_dir"]
        )

    def test_record_artifact_generic_file_rejects_mismatched_explicit_sha512(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        artifact_file_path = sandbox_dir / "example-project-bootstrap.zip"
        artifact_file_path.write_bytes(b"bootstrap payload\n")
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
                "generic-file",
                "--artifact-id",
                "bootstrap-zip",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/example-project/releases/download/v1.2.3-rc0/example-project-bootstrap.zip",
                "--sha512",
                "0" * 128,
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "generic-file --sha512 does not match the bytes of --file",
            completed.stderr,
        )
