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
"""Verify-rc secondary artifact kind tests."""

from tests.release.commands.verification_support import (
    VerificationCommandsIntegrationTestBase,
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    json,
    run_cli,
)


class VerificationArtifactKindCommandTest(VerificationCommandsIntegrationTestBase):
    """Verify-rc secondary artifact kind tests."""

    def test_verify_rc_command_verifies_maven_repository_secondary_artifact(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_maven_repository_fixture(sandbox_dir)
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("maven-repository", secondary_verification["kind"])
        self.assertTrue(
            secondary_verification["live_repository"]["matches_signed_inventory"]
        )
        self.assertEqual(
            1, len(secondary_verification["live_repository"]["signature_verifications"])
        )

    def test_verify_rc_command_verifies_python_distribution_secondary_artifact(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_python_distribution_fixture(sandbox_dir)
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("python-distribution", secondary_verification["kind"])
        self.assertTrue(
            secondary_verification["index_resolution"]["sha256_matches_index"]
        )
        self.assertEqual(
            "simple-json", secondary_verification["index_resolution"]["found_via"]
        )

    def test_verify_rc_command_fails_closed_when_python_distribution_is_missing_from_index(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_python_distribution_fixture(
            sandbox_dir,
            missing_index_entry=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "python-distribution file is not present in the declared simple index",
            completed.stderr,
        )

    def test_verify_rc_command_verifies_python_distribution_reproducibility_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_python_distribution_fixture(
            sandbox_dir,
            include_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "pypi-wheel", secondary_verification["reproducibility"]["profile_id"]
        )
        self.assertEqual(
            ["dist/example-1.2.3-py3-none-any.whl"],
            secondary_verification["reproducibility"]["effective_execution"]["build"][
                "output_paths"
            ],
        )

    def test_verify_rc_command_reports_python_distribution_reproducibility_drift_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_python_distribution_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
            archive_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "python-distribution reproducibility output does not match the staged artifact bytes",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "byte-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_python_distribution_drift(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        fixture, verify_completed = (
            self._materialize_cached_python_distribution_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_python_distribution_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: pypi-wheel", inspect_completed.stderr)
        self.assertIn("Project: example", inspect_completed.stderr)
        self.assertIn("Version: 1.2.3", inspect_completed.stderr)
        self.assertIn("Distribution type: wheel", inspect_completed.stderr)
        self.assertIn("Simple index:", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Drift classification: size-and-binary-drift", inspect_completed.stderr
        )
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: zip", inspect_completed.stderr)
        self.assertIn(
            "Archive drift classification: mixed-entry-drift", inspect_completed.stderr
        )
        self.assertIn("Archive metadata mismatches", inspect_completed.stderr)
        self.assertIn(
            "Likely cause: more than one top-level archive drift category is present",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Wheel hint: this often points to ZIP member metadata, entry order, or wheel payload generation drift",
            inspect_completed.stderr,
        )
        self.assertIn("example/__init__.py", inspect_completed.stderr)

    def test_verify_rc_command_verifies_npm_package_secondary_artifact(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_npm_package_fixture(sandbox_dir)
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("npm-package", secondary_verification["kind"])
        self.assertTrue(
            secondary_verification["registry_resolution"][
                "tarball_url_matches_manifest"
            ]
        )
        self.assertTrue(
            secondary_verification["registry_resolution"]["integrity_matches_manifest"]
        )

    def test_verify_rc_command_fails_closed_when_npm_registry_integrity_drifts(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_npm_package_fixture(
            sandbox_dir,
            drift_registry_integrity=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "npm-package registry integrity does not match the signed manifest",
            completed.stderr,
        )

    def test_verify_rc_command_verifies_npm_package_reproducibility_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_npm_package_fixture(
            sandbox_dir,
            include_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "npm-package-main",
            secondary_verification["reproducibility"]["profile_id"],
        )
        self.assertEqual(
            ["dist/example-project-1.2.3.tgz"],
            secondary_verification["reproducibility"]["effective_execution"]["build"][
                "output_paths"
            ],
        )

    def test_verify_rc_command_reports_npm_package_reproducibility_drift_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_npm_package_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
            archive_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "npm-package reproducibility output does not match the staged artifact bytes",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "byte-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_npm_package_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        fixture, verify_completed = self._materialize_cached_npm_package_drift_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_npm_package_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: npm-package-main", inspect_completed.stderr)
        self.assertIn("Package: @apache/example-project", inspect_completed.stderr)
        self.assertIn("Version: 1.2.3", inspect_completed.stderr)
        self.assertIn("Declared integrity: sha512-", inspect_completed.stderr)
        self.assertIn("Registry URL:", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Drift classification: size-and-binary-drift", inspect_completed.stderr
        )
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: tar", inspect_completed.stderr)
        self.assertIn(
            "Archive drift classification: mixed-entry-drift", inspect_completed.stderr
        )
        self.assertIn("Archive metadata mismatches", inspect_completed.stderr)
        self.assertIn(
            "Likely cause: more than one top-level archive drift category is present",
            inspect_completed.stderr,
        )
        self.assertIn(
            "npm hint: this often points to npm pack file selection, tar header metadata, or generated package contents",
            inspect_completed.stderr,
        )
        self.assertIn("package/package.json", inspect_completed.stderr)

    def test_verify_rc_command_fails_closed_when_maven_repository_drifts_from_inventory(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_maven_repository_fixture(
            sandbox_dir,
            drift_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "live maven repository checksum does not match the signed inventory",
            completed.stderr,
        )

    def test_verify_rc_command_verifies_maven_repository_reproducibility_in_full_mode(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_maven_repository_fixture(
            sandbox_dir,
            include_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "maven-staging", secondary_verification["reproducibility"]["profile_id"]
        )
        metadata_reference = next(
            reference
            for reference in secondary_verification["reproducibility"]["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [
                "artifact_id",
                "kind",
                "profile_id",
                "comparison_mode",
                "canonical_recipe",
                "effective_execution",
                "override",
                "repository_dir",
                "require_signatures",
                "path_rules",
                "matches_remote_bytes",
                "failure_class",
                "verified_path_count",
                "failed_path_count",
                "skipped_path_count",
                "path_results",
                "issues",
            ],
            list(metadata_payload),
        )
        self.assertGreater(metadata_payload["verified_path_count"], 0)
        self.assertEqual(0, metadata_payload["failed_path_count"])
        self.assertGreaterEqual(metadata_payload["skipped_path_count"], 0)
        self.assertEqual([], metadata_payload["path_results"])
        self.assertEqual(
            [".buildish-out/m2repo"],
            secondary_verification["reproducibility"]["effective_execution"]["build"][
                "output_paths"
            ],
        )

    def test_verify_rc_command_verifies_maven_repository_reproducibility_with_unrelated_local_repo_files(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_maven_repository_fixture(
            sandbox_dir,
            include_reproducibility=True,
            include_unrelated_local_repo_files=True,
            omit_sidecar_path_rules=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )

    def test_verify_rc_command_reports_maven_repository_reproducibility_drift_in_full_mode(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_maven_repository_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "maven-repository reproducibility exact-bytes comparison failed",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "path-comparison-failed",
            secondary_verification["reproducibility"]["failure_class"],
        )
        metadata_reference = next(
            reference
            for reference in secondary_verification["reproducibility"]["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertGreaterEqual(metadata_payload["verified_path_count"], 0)
        self.assertEqual(1, metadata_payload["failed_path_count"])
        self.assertGreaterEqual(metadata_payload["skipped_path_count"], 0)
        self.assertEqual(1, len(metadata_payload["path_results"]))

    def test_inspect_repro_command_reports_saved_maven_repository_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = (
            self._materialize_cached_maven_repository_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_maven_repository_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: maven-staging-main", inspect_completed.stderr)
        self.assertIn("Verified comparable paths: 1", inspect_completed.stderr)
        self.assertIn("Failed comparable paths: 1", inspect_completed.stderr)
        self.assertIn("Failed by mode: exact-bytes=1", inspect_completed.stderr)
        self.assertIn("Failed by category: metadata-text=1", inspect_completed.stderr)
        self.assertIn(
            "Failed by repository directory: org/example/app/1.0.0=1",
            inspect_completed.stderr,
        )
        self.assertIn("Likely descriptor/text drift", inspect_completed.stderr)
        self.assertIn(
            "Maven hint: start with versioning, generated POM/module files, and other descriptor text paths",
            inspect_completed.stderr,
        )
        self.assertIn("Failed metadata/text paths: 1", inspect_completed.stderr)
        self.assertIn(
            "Metadata/text path: org/example/app/1.0.0/app-1.0.0.pom [exact-bytes] raw bytes differ",
            inspect_completed.stderr,
        )

    def test_verify_rc_command_verifies_oci_image_secondary_artifact(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_oci_image_fixture(sandbox_dir)
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("oci-image", secondary_verification["kind"])
        self.assertTrue(secondary_verification["inspection"]["digest_matches_manifest"])
        self.assertTrue(secondary_verification["inspection"]["platform_digests_match"])

    def test_verify_rc_command_fails_closed_when_oci_image_platform_digest_drifts(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_oci_image_fixture(
            sandbox_dir,
            drift_registry_image=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image platform digests do not match the signed manifest",
            completed.stderr,
        )

    def test_verify_rc_command_verifies_oci_image_reproducibility_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_oci_image_fixture(
            sandbox_dir,
            include_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "oci-main-image", secondary_verification["reproducibility"]["profile_id"]
        )
        self.assertEqual(
            [".buildish-out/oci-image-rebuilt.marker"],
            secondary_verification["reproducibility"]["effective_execution"]["build"][
                "output_paths"
            ],
        )
        metadata_reference = next(
            reference
            for reference in secondary_verification["reproducibility"]["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [
                "artifact_id",
                "kind",
                "profile_id",
                "comparison_mode",
                "canonical_recipe",
                "effective_execution",
                "override",
                "image_ref",
                "declared_digest",
                "expected_platform_digests",
                "rebuilt_digest",
                "rebuilt_platform_digests",
                "matches_remote_bytes",
                "failure_class",
                "issues",
            ],
            list(metadata_payload),
        )

    def test_verify_rc_command_reports_oci_image_reproducibility_drift_in_full_mode(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_oci_image_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image reproducibility digest does not match the signed manifest",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "digest-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_oci_image_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        fixture, verify_completed = self._materialize_cached_oci_image_drift_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_oci_image_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: ghcr-main-image", inspect_completed.stderr)
        self.assertIn(
            "Top-level image digest differs from the signed manifest",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Platform digests matched the signed manifest", inspect_completed.stderr
        )
        self.assertIn("Drift classification: metadata-only", inspect_completed.stderr)
        self.assertIn(
            "Likely OCI index/config metadata drift", inspect_completed.stderr
        )
        self.assertIn("Rebuilt digest", inspect_completed.stderr)

    def test_inspect_repro_command_reports_saved_oci_image_platform_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        fixture, verify_completed = (
            self._materialize_cached_oci_image_platform_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_oci_image_platform_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn(
            "Platform digests differ from the signed manifest", inspect_completed.stderr
        )
        self.assertIn("Changed platform count: 1", inspect_completed.stderr)
        self.assertIn(
            "Platform drift summary: changed=1 missing=0 unexpected=0",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Drift classification: top-level-and-platform-payload",
            inspect_completed.stderr,
        )
        self.assertIn("Changed platform: linux/arm64", inspect_completed.stderr)
        self.assertIn("Platform payload drift is present", inspect_completed.stderr)
        self.assertIn(
            "OCI hint: compare the rebuilt platform images above before reviewing top-level manifest/index metadata",
            inspect_completed.stderr,
        )
