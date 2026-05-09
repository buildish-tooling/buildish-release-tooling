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
"""Python distribution artifact-registration command tests."""

from apache_buildish_release_tooling.release.contracts import (
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


class PythonDistributionArtifactRegistrationCommandTest(
    ArtifactRegistrationCommandTestBase
):
    """Python distribution artifact-registration command tests."""

    def test_record_artifact_python_distribution_command_writes_manifest_bundle(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        artifact_file_path = sandbox_dir / "dist" / "example-1.2.3-py3-none-any.whl"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"wheel payload\n")
        expected_sha256 = hashlib.sha256(artifact_file_path.read_bytes()).hexdigest()
        component_id = "buildish-example"
        artifact_id = "pypi-wheel"
        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "python-distribution",
                "--artifact-id",
                artifact_id,
                "--role",
                "wheel",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                "--index-url",
                "https://test.pypi.org/simple/",
                "--project-name",
                "example",
                "--package-version",
                "1.2.3",
                "--sha256-uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl.sha256",
                "--attestation-repository",
                "apache/buildish-example",
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
        self.assertEqual("python-distribution", action_manifest["kind"])
        self.assertEqual(
            str(expected_manifest_path), action_manifest["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), action_manifest["artifact_bundle_dir"]
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
                "filename",
                "uri",
                "index_url",
                "project_name",
                "version",
                "checksums",
                "authenticity",
            ],
        )
        validated_manifest = SecondaryArtifactManifestV1.model_validate(payload)
        self.assertEqual(
            artifact_id, validated_manifest.secondary_artifacts[0].artifact_id
        )
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "python-distribution",
                    "role": "wheel",
                    "filename": "example-1.2.3-py3-none-any.whl",
                    "uri": "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                    "index_url": "https://test.pypi.org/simple/",
                    "project_name": "example",
                    "version": "1.2.3",
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha256": {
                            "value": expected_sha256,
                            "uri": "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl.sha256",
                        }
                    },
                    "authenticity": {
                        "scheme": "pypi-attestation",
                        "repository": "apache/buildish-example",
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("python-distribution", github_outputs["artifact_kind"])
        self.assertEqual(
            str(expected_manifest_path), github_outputs["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), github_outputs["artifact_bundle_dir"]
        )

    def test_record_artifact_python_distribution_rejects_mismatched_explicit_sha256(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        artifact_file_path = sandbox_dir / "dist" / "example-1.2.3-py3-none-any.whl"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"wheel payload\n")
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
        )

        completed = run_cli(
            [
                "record-artifact",
                "--component-config",
                str(config_path),
                "--kind",
                "python-distribution",
                "--artifact-id",
                "pypi-wheel",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://test.pypi.org/packages/example-1.2.3-py3-none-any.whl",
                "--index-url",
                "https://test.pypi.org/simple/",
                "--project-name",
                "example",
                "--package-version",
                "1.2.3",
                "--sha256",
                "0" * 64,
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "python-distribution --sha256 does not match the bytes of --file",
            completed.stderr,
        )
