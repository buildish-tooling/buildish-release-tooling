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
"""Artifact-registration command integration tests."""

# ruff: noqa: F403, F405
from tests.release.commands.support import *


class ArtifactRegistrationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """Artifact-registration command integration tests."""

    def test_record_artifact_generic_file_command_writes_registration_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "bootstrap-zip"
        artifact_file_path = sandbox_dir / "buildish-example-bootstrap.zip"
        artifact_bytes = b"bootstrap payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
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
                "generic-file",
                "--artifact-id",
                artifact_id,
                "--role",
                "bootstrap-convenience-archive",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
                "--sha512-uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip.sha512",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
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
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_manifest_path.parent), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "generic-file",
                    "role": "bootstrap-convenience-archive",
                    "filename": "buildish-example-bootstrap.zip",
                    "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "checksums": {
                        "sha512": {
                            "value": expected_sha512,
                            "uri": "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip.sha512",
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
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_manifest_path.parent), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_generic_file_rejects_mismatched_explicit_sha512(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        artifact_file_path = sandbox_dir / "buildish-example-bootstrap.zip"
        artifact_file_path.write_bytes(b"bootstrap payload\n")
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
                "generic-file",
                "--artifact-id",
                "bootstrap-zip",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://github.com/apache/buildish-example/releases/download/v1.2.3-rc0/buildish-example-bootstrap.zip",
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

    def test_record_artifact_oci_image_command_writes_manifest_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
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
                "apache/buildish-example",
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
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
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
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/apache/buildish-example@{digest.lower()}",
                    "registry": "ghcr.io",
                    "repository": "apache/buildish-example",
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
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_multiplatform_image_ref(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
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
                            "platform": {"architecture": "arm64", "os": "linux", "variant": "v8"},
                        },
                        {
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                            "digest": "sha256:" + ("c3" * 32),
                            "size": 839,
                            "annotations": {"vnd.docker.reference.type": "attestation-manifest"},
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
                "ghcr.io/apache/buildish-example:1.2.3",
                "--artifact-origin",
                "source-commit",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(
                manifest_path,
                extra_env={"FAKE_DOCKER_STATE_DIR": str(docker_state_dir), "GITHUB_OUTPUT": str(github_output_path)},
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
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "oci-image",
                    "role": "container-image",
                    "uri": f"oci://ghcr.io/apache/buildish-example@{top_level_digest}",
                    "registry": "ghcr.io",
                    "repository": "apache/buildish-example",
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
            ["ghcr.io/apache/buildish-example:1.2.3|{{json .Manifest}}"],
            (docker_state_dir / "imagetools-inspect.log").read_text(encoding="utf-8").splitlines(),
        )

    def test_record_artifact_oci_image_command_derives_manifest_bundle_from_single_platform_image_ref(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
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
                "apache/buildish-example:1.2.3",
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
        self.assertEqual(
            [
                {
                    "artifact_id": "dockerhub-single-platform",
                    "kind": "oci-image",
                    "uri": f"oci://docker.io/apache/buildish-example@{top_level_digest}",
                    "registry": "docker.io",
                    "repository": "apache/buildish-example",
                    "digest": top_level_digest,
                }
            ],
            payload["secondary_artifacts"],
        )

    def test_record_artifact_oci_image_rejects_image_ref_mixed_with_manual_fields(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
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
                "ghcr.io/apache/buildish-example:1.2.3",
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
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
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
                "apache/buildish-example",
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

    def test_record_artifact_python_distribution_command_writes_manifest_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
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
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
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
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
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
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_python_distribution_rejects_mismatched_explicit_sha256(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
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

    def test_record_artifact_npm_package_command_writes_manifest_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "npm-package-main"
        artifact_file_path = sandbox_dir / "dist" / "apache-buildish-example-1.2.3.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_bytes = b"npm package payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        expected_integrity = "sha512-" + base64.b64encode(hashlib.sha512(artifact_bytes).digest()).decode("ascii")
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
                "@apache/buildish-example",
                "--package-version",
                "1.2.3",
                "--attestation-repository",
                "apache/buildish-example",
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
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
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "npm-package",
                    "role": "npm-package",
                    "filename": "buildish-example-1.2.3.tgz",
                    "uri": "https://registry.npmjs.org/@apache/buildish-example/-/buildish-example-1.2.3.tgz",
                    "registry_url": "https://registry.npmjs.org/",
                    "package_name": "@apache/buildish-example",
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
                        "repository": "apache/buildish-example",
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("npm-package", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_npm_package_command_derives_registry_metadata_from_canonical_uri(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        component_id = "buildish-example"
        artifact_id = "npm-package-main"
        artifact_file_path = sandbox_dir / "dist" / "local-package.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_bytes = b"npm package payload\n"
        artifact_file_path.write_bytes(artifact_bytes)
        expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
        expected_integrity = "sha512-" + base64.b64encode(hashlib.sha512(artifact_bytes).digest()).decode("ascii")
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
                "npm-package",
                "--artifact-id",
                artifact_id,
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://registry.npmjs.org/@apache/buildish-example/-/buildish-example-1.2.3.tgz",
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
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "npm-package",
                    "filename": "buildish-example-1.2.3.tgz",
                    "uri": "https://registry.npmjs.org/@apache/buildish-example/-/buildish-example-1.2.3.tgz",
                    "registry_url": "https://registry.npmjs.org/",
                    "package_name": "@apache/buildish-example",
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

    def test_record_artifact_npm_package_rejects_mismatched_explicit_integrity(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        artifact_file_path = sandbox_dir / "dist" / "buildish-example-1.2.3.tgz"
        artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_file_path.write_bytes(b"npm package payload\n")
        mismatched_integrity = "sha512-" + base64.b64encode(bytes(64)).decode("ascii")
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
                "npm-package",
                "--artifact-id",
                "npm-package-main",
                "--file",
                str(artifact_file_path),
                "--uri",
                "https://registry.npmjs.org/@apache/buildish-example/-/buildish-example-1.2.3.tgz",
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

    def test_record_artifact_maven_repository_command_writes_inventory_bundle(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        github_output_path = sandbox_dir / "record-artifact.outputs"
        component_id = "buildish-example"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        expected_sha512_by_path, expected_sizes_by_path = _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"
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
                "maven-repository",
                "--artifact-id",
                artifact_id,
                "--role",
                "maven-staging",
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--git-commit-sha",
                "0123456789abcdef0123456789abcdef01234567",
                "--inventory-workers",
                "1",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path, extra_env={"GITHUB_OUTPUT": str(github_output_path)}),
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
        expected_inventory_path = expected_bundle_dir / f"{artifact_id}-inventory.json"
        expected_inventory_sha512 = hashlib.sha512(expected_inventory_path.read_bytes()).hexdigest()
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("maven-repository", action_manifest["kind"])
        self.assertEqual(str(expected_manifest_path), action_manifest["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), action_manifest["artifact_bundle_dir"])
        self.assertEqual([str(expected_inventory_path)], action_manifest["inventory_paths"])

        payload = json.loads(expected_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [
                {
                    "artifact_id": artifact_id,
                    "kind": "maven-repository",
                    "role": "maven-staging",
                    "staging_repository_id": staging_repository_id,
                    "base_url": base_url,
                    "artifact_origin": "source-commit",
                    "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                    "inventory": {
                        "filename": f"{artifact_id}-inventory.json",
                        "sha512": expected_inventory_sha512,
                        "entry_count": len(expected_sha512_by_path),
                        "total_size_bytes": sum(expected_sizes_by_path.values()),
                    },
                }
            ],
            payload["secondary_artifacts"],
        )
        inventory_payload = json.loads(expected_inventory_path.read_text(encoding="utf-8"))
        self.assertEqual("1", inventory_payload["schema_version"])
        self.assertEqual("maven-repository", inventory_payload["inventory_type"])
        self.assertEqual(artifact_id, inventory_payload["artifact_id"])
        self.assertEqual(staging_repository_id, inventory_payload["staging_repository_id"])
        self.assertEqual(base_url, inventory_payload["base_url"])
        inventory_entries = {entry["path"]: entry for entry in inventory_payload["entries"]}
        self.assertEqual(sorted(expected_sha512_by_path), sorted(inventory_entries))
        for relative_path, expected_sha512 in expected_sha512_by_path.items():
            self.assertEqual(expected_sha512, inventory_entries[relative_path]["sha512"])
            self.assertEqual(expected_sizes_by_path[relative_path], inventory_entries[relative_path]["size_bytes"])

        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("maven-repository", github_outputs["artifact_kind"])
        self.assertEqual(str(expected_manifest_path), github_outputs["artifact_manifest_path"])
        self.assertEqual(str(expected_bundle_dir), github_outputs["artifact_bundle_dir"])

    def test_record_artifact_maven_repository_command_reports_progress_when_enabled(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        manifest_path = sandbox_dir / "record-artifact.json"
        component_id = "buildish-example"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"
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
                "--progress",
                "on",
                "--kind",
                "maven-repository",
                "--artifact-id",
                artifact_id,
                "--base-url",
                base_url,
                "--staging-repository-id",
                staging_repository_id,
                "--inventory-workers",
                "1",
            ],
            cwd=sandbox_dir,
            env=cli_env(manifest_path),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("progress: enumerating maven repository from ", completed.stderr)
        self.assertIn("progress: building maven repository inventory: 0/", completed.stderr)
        self.assertIn("progress: wrote maven repository inventory: ", completed.stderr)
