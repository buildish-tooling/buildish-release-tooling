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
"""Maven repository artifact-registration command tests."""

from buildish_release_tooling.release.contracts import (
    SecondaryArtifactManifestV1,
)

from tests.release.commands.artifact_registration_support import (
    ArtifactRegistrationCommandTestBase,
)
from tests.release.commands.support import (
    _read_simple_github_outputs,
    _write_test_maven_repository,
    cli_env,
    hashlib,
    json,
    run_cli,
)


class MavenRepositoryArtifactRegistrationCommandTest(
    ArtifactRegistrationCommandTestBase
):
    """Maven repository artifact-registration command tests."""

    def test_record_artifact_maven_repository_command_writes_inventory_bundle(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        github_output_path = sandbox.github_output_path
        component_id = "example-project"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        expected_sha512_by_path, expected_sizes_by_path = _write_test_maven_repository(
            repository_root
        )
        base_url = f"{repository_root.as_uri()}/"
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
        expected_inventory_path = expected_bundle_dir / f"{artifact_id}-inventory.json"
        expected_inventory_sha512 = hashlib.sha512(
            expected_inventory_path.read_bytes()
        ).hexdigest()
        self.assertEqual(str(expected_manifest_path), completed.stdout.strip())
        action_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(component_id, action_manifest["component"])
        self.assertEqual("record-artifact", action_manifest["action"])
        self.assertEqual(artifact_id, action_manifest["artifact_id"])
        self.assertEqual("maven-repository", action_manifest["kind"])
        self.assertEqual(
            str(expected_manifest_path), action_manifest["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), action_manifest["artifact_bundle_dir"]
        )
        self.assertEqual(
            [str(expected_inventory_path)], action_manifest["inventory_paths"]
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
        inventory_payload = json.loads(
            expected_inventory_path.read_text(encoding="utf-8")
        )
        self.assertEqual("1", inventory_payload["schema_version"])
        self.assertEqual("maven-repository", inventory_payload["inventory_type"])
        self.assertEqual(artifact_id, inventory_payload["artifact_id"])
        self.assertEqual(
            staging_repository_id, inventory_payload["staging_repository_id"]
        )
        self.assertEqual(base_url, inventory_payload["base_url"])
        inventory_entries = {
            entry["path"]: entry for entry in inventory_payload["entries"]
        }
        self.assertEqual(sorted(expected_sha512_by_path), sorted(inventory_entries))
        for relative_path, expected_sha512 in expected_sha512_by_path.items():
            self.assertEqual(
                expected_sha512, inventory_entries[relative_path]["sha512"]
            )
            self.assertEqual(
                expected_sizes_by_path[relative_path],
                inventory_entries[relative_path]["size_bytes"],
            )

        github_outputs = _read_simple_github_outputs(github_output_path)
        self.assertEqual(artifact_id, github_outputs["artifact_id"])
        self.assertEqual("maven-repository", github_outputs["artifact_kind"])
        self.assertEqual(
            str(expected_manifest_path), github_outputs["artifact_manifest_path"]
        )
        self.assertEqual(
            str(expected_bundle_dir), github_outputs["artifact_bundle_dir"]
        )

    def test_record_artifact_maven_repository_command_reports_progress_when_enabled(
        self,
    ) -> None:
        sandbox = self._create_record_artifact_sandbox()
        sandbox_dir = sandbox.root
        config_path = sandbox.config_path
        manifest_path = sandbox.manifest_path
        component_id = "example-project"
        artifact_id = "maven-staging-main"
        staging_repository_id = "orgapacheexample-1234"
        repository_root = sandbox_dir / staging_repository_id
        _write_test_maven_repository(repository_root)
        base_url = f"{repository_root.as_uri()}/"
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
        self.assertIn(
            "progress: building maven repository inventory: 0/", completed.stderr
        )
        self.assertIn("progress: wrote maven repository inventory: ", completed.stderr)
