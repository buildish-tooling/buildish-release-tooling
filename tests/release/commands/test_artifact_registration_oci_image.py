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
"""OCI image artifact-registration command tests."""

from buildish_release_tooling.release.contracts import (
    SecondaryArtifactManifestV1,
)

from tests.release.commands.artifact_registration_support import (
    ArtifactRegistrationCommandTestBase,
)
from tests.release.commands.support import (
    _read_simple_github_outputs,
    cli_env,
    create_fake_docker_launcher,
    json,
    run_cli,
)


class OciImageArtifactRegistrationCommandTest(ArtifactRegistrationCommandTestBase):
    """OCI image artifact-registration command tests."""

    def test_record_artifact_oci_image_command_writes_manifest_bundle(self) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        component_id = "buildish-example"
        artifact_id = "ghcr-main-image"
        digest = "SHA256:" + ("A1" * 32)
        amd64_digest = "sha256:" + ("b2" * 32)
        arm64_digest = "sha256:" + ("c3" * 32)
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
                "oci-image",
                "--artifact-id",
                artifact_id,
                "--role",
                "container-image",
                "--registry",
                "ghcr.io",
                "--repository",
                "buildish-tooling/buildish-example",
                "--digest",
                digest,
                "--platform-digest",
                f"linux/amd64={amd64_digest}",
                "--platform-digest",
                f"linux/arm64={arm64_digest}",
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
        self.assertEqual("oci-image", action_manifest["kind"])
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
                "uri",
                "registry",
                "repository",
                "digest",
                "platform_digests",
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
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/buildish-tooling/buildish-example@{digest.lower()}",
                    "registry": "ghcr.io",
                    "repository": "buildish-tooling/buildish-example",
                    "digest": digest.lower(),
                    "platform_digests": [
                        {
                            "platform": "linux/amd64",
                            "digest": amd64_digest,
                        },
                        {
                            "platform": "linux/arm64",
                            "digest": arm64_digest,
                        },
                    ],
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("oci-image", github_outputs["artifact_kind"])
        self.assertEqual(
            str(expected_manifest_path), github_outputs["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), github_outputs["artifact_bundle_dir"]
        )

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_multiplatform_image_ref(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        component_id = "buildish-example"
        artifact_id = "ghcr-main-image"
        top_level_digest = "sha256:" + ("d4" * 32)
        amd64_digest = "sha256:" + ("a1" * 32)
        arm64_digest = "sha256:" + ("b2" * 32)
        (docker_state_dir / "imagetools-inspect-response.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.index.v1+json",
                    "digest": top_level_digest,
                    "size": 855,
                    "manifests": [
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": amd64_digest,
                            "size": 673,
                            "platform": {"architecture": "amd64", "os": "linux"},
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": arm64_digest,
                            "size": 677,
                            "platform": {
                                "architecture": "arm64",
                                "os": "linux",
                                "variant": "v8",
                            },
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": "sha256:" + ("c3" * 32),
                            "size": 839,
                            "annotations": {
                                "vnd.docker.reference.type": "attestation-manifest"
                            },
                            "platform": {"architecture": "unknown", "os": "unknown"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
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
                "oci-image",
                "--artifact-id",
                artifact_id,
                "--role",
                "container-image",
                "--image-ref",
                "ghcr.io/buildish-tooling/buildish-example:1.2.3",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={
                    "FAKE_DOCKER_STATE_DIR": str(docker_state_dir),
                    "GITHUB_OUTPUT": str(github_output_path),
                },
                prepend_dirs=(docker_path.parent,),
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
        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self._assert_secondary_artifact_entry_shape(
            payload,
            expected_entry_keys=[
                "artifact_id",
                "kind",
                "role",
                "artifact_origin",
                "git_commit_sha",
                "uri",
                "registry",
                "repository",
                "digest",
                "platform_digests",
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
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/buildish-tooling/buildish-example@{top_level_digest}",
                    "registry": "ghcr.io",
                    "repository": "buildish-tooling/buildish-example",
                    "digest": top_level_digest,
                    "platform_digests": [
                        {
                            "platform": "linux/amd64",
                            "digest": amd64_digest,
                        },
                        {
                            "platform": "linux/arm64/v8",
                            "digest": arm64_digest,
                        },
                    ],
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                }
            ],
            payload["secondary_artifacts"],
        )
        self.assertEqual(
            ["ghcr.io/buildish-tooling/buildish-example:1.2.3|{{json .Manifest}}"],
            (docker_state_dir / "imagetools-inspect.log")
            .read_text(encoding="utf-8")
            .splitlines(),
        )

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_single_platform_image_ref(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
        top_level_digest = "sha256:" + ("e5" * 32)
        (docker_state_dir / "imagetools-inspect-response.json").write_text(
            json.dumps(
                {
                    "schemaVersion": 2,
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": top_level_digest,
                    "size": 1054,
                    "config": {"mediaType": "application/vnd.oci.image.config.v1+json"},
                    "layers": [],
                }
            ),
            encoding="utf-8",
        )
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
                "oci-image",
                "--artifact-id",
                "dockerhub-single-platform",
                "--image-ref",
                "buildish-tooling/buildish-example:1.2.3",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_DOCKER_STATE_DIR": str(docker_state_dir)},
                prepend_dirs=(docker_path.parent,),
            ),
        )
        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        expected_manifest_path = (
            sandbox_dir
            / "build"
            / "release-artifacts"
            / "buildish-example"
            / "secondary-artifacts"
            / "dockerhub-single-platform"
            / "artifact-manifest.json"
        )
        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self._assert_secondary_artifact_entry_shape(
            payload,
            expected_entry_keys=[
                "artifact_id",
                "kind",
                "uri",
                "registry",
                "repository",
                "digest",
            ],
        )
        validated_manifest = SecondaryArtifactManifestV1.model_validate(payload)
        self.assertEqual(
            "dockerhub-single-platform",
            validated_manifest.secondary_artifacts[0].artifact_id,
        )
        self.assertEqual(
            [
                {
                    "artifact_id": "dockerhub-single-platform",
                    "kind": "oci-image",
                    "uri": f"oci://docker.io/buildish-tooling/buildish-example@{top_level_digest}",
                    "registry": "docker.io",
                    "repository": "buildish-tooling/buildish-example",
                    "digest": top_level_digest,
                }
            ],
            payload["secondary_artifacts"],
        )

    def test_record_artifact_oci_image_rejects_image_ref_mixed_with_manual_fields(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
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
                "oci-image",
                "--artifact-id",
                "ghcr-main-image",
                "--image-ref",
                "ghcr.io/buildish-tooling/buildish-example:1.2.3",
                "--digest",
                "sha256:" + ("0f" * 32),
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image --image-ref cannot be combined with --registry, --repository, --digest, or --platform-digest",
            completed.stderr,
        )

    def test_record_artifact_oci_image_rejects_invalid_digest(self) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
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
                "oci-image",
                "--artifact-id",
                "ghcr-main-image",
                "--registry",
                "ghcr.io",
                "--repository",
                "buildish-tooling/buildish-example",
                "--digest",
                "not-a-digest",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )
        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image --digest must be an OCI content digest like sha256:<hex>",
            completed.stderr,
        )
