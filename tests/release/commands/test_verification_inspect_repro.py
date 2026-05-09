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
"""Inspect-repro command tests."""

# ruff: noqa: F403, F405
from tests.release.commands.verification_support import *


class VerificationInspectReproCommandTest(VerificationCommandsIntegrationTestBase):
    """Inspect-repro command tests."""

    def test_inspect_repro_command_reports_saved_generic_file_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        inspect_completed = self._cached_generic_file_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Inspect Repro", inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 1", inspect_completed.stderr)
        self.assertIn("Source artifact failures: 0", inspect_completed.stderr)
        self.assertIn("Secondary artifact failures: 1", inspect_completed.stderr)
        self.assertIn("Failure kinds: generic-file=1", inspect_completed.stderr)
        self.assertIn("Failure classes: byte-mismatch=1", inspect_completed.stderr)
        self.assertIn(
            "Failure groups: secondary/generic-file/byte-mismatch=1",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure group: secondary/generic-file/byte-mismatch: bootstrap-zip",
            inspect_completed.stderr,
        )
        self.assertIn("Artifact 1/1: bootstrap-zip", inspect_completed.stderr)
        self.assertIn(
            "Build command: sh buildish-release-tooling/rebuild-bootstrap.sh",
            inspect_completed.stderr,
        )
        self.assertIn("Build working directory: .", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertIn(
            "Retained evidence: comparison-metadata, staged-artifact, rebuilt-artifact",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Drift classification: text-content-drift", inspect_completed.stderr
        )
        self.assertIn("Size delta bytes: 0", inspect_completed.stderr)
        self.assertIn("Unified text diff", inspect_completed.stderr)
        self.assertIn("Outcome", inspect_completed.stderr)
        self.assertIn(
            "Inspected 1 saved reproducibility failure(s)", inspect_completed.stderr
        )

    def test_inspect_repro_command_can_emit_machine_readable_json(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        inspect_completed = self._cached_generic_file_drift_inspect_result("--json")

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        payload = json.loads(inspect_completed.stdout)
        self.assertEqual(
            [
                "schema_version",
                "report_type",
                "verify_rc_report_schema_version",
                "bundle_schema_version",
                "component_id",
                "rc_tag",
                "verify_rc_verdict",
                "build_checks_attempted",
                "report_json_path",
                "inspection_bundle_path",
                "selected_artifact_ids",
                "selected_failure_classes",
                "summary_only",
                "summary",
                "targets",
            ],
            list(payload),
        )
        self.assertEqual("inspect-repro", payload["report_type"])
        self.assertEqual("1", payload["schema_version"])
        self.assertEqual("1", payload["verify_rc_report_schema_version"])
        self.assertEqual("1", payload["bundle_schema_version"])
        self.assertEqual("buildish-example", payload["component_id"])
        self.assertEqual("v1.2.3-rc0", payload["rc_tag"])
        self.assertTrue(payload["build_checks_attempted"])
        self.assertFalse(payload["summary_only"])
        self.assertEqual([], payload["selected_artifact_ids"])
        self.assertEqual([], payload["selected_failure_classes"])
        self.assertEqual(1, payload["summary"]["failure_count"])
        self.assertEqual(
            [{"key": "secondary/generic-file/byte-mismatch", "count": 1}],
            payload["summary"]["failure_groups"],
        )
        self.assertEqual(1, len(payload["targets"]))
        target = payload["targets"][0]
        self.assertEqual("bootstrap-zip", target["artifact_id"])
        self.assertEqual("generic-file", target["kind"])
        self.assertEqual("byte-mismatch", target["failure_class"])
        self.assertEqual(
            "secondary/generic-file/byte-mismatch", target["failure_group"]
        )
        self.assertEqual("bootstrap-zip", target["profile_id"])
        self.assertEqual("canonical-profile", target["recipe_source"])
        self.assertEqual("host-direct", target["execution_backend"])
        self.assertEqual(
            ["sh", "buildish-release-tooling/rebuild-bootstrap.sh"],
            target["build_command"],
        )
        self.assertEqual(".", target["build_working_directory"])
        self.assertEqual(
            [
                "BUILDISH_PROJECT_ROOT",
                "BUILDISH_SOURCE_DATE_EPOCH",
                "BUILDISH_WORK_DIR",
                "SOURCE_DATE_EPOCH",
                "TMPDIR",
            ],
            target["injected_environment_keys"],
        )
        self.assertIn("comparison-metadata", target["evidence_labels"])
        self.assertEqual(
            ["comparison-metadata", "staged-artifact", "rebuilt-artifact"],
            [evidence["label"] for evidence in target["evidence"]],
        )

    def test_inspect_repro_json_contract_for_summary_only_mixed_failures(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_mixed_failure_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "mixed-failures-all-kinds",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                    include_maven_repository=True,
                    include_maven_repository_reproducibility=True,
                    drift_maven_repository_reproducibility=True,
                    include_oci_image=True,
                    include_oci_image_reproducibility=True,
                    drift_oci_image_reproducibility_platform=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=("--json", "--summary-only"),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        payload = json.loads(inspect_completed.stdout)
        self.assertEqual(
            [
                "schema_version",
                "report_type",
                "verify_rc_report_schema_version",
                "bundle_schema_version",
                "component_id",
                "rc_tag",
                "verify_rc_verdict",
                "build_checks_attempted",
                "report_json_path",
                "inspection_bundle_path",
                "selected_artifact_ids",
                "selected_failure_classes",
                "summary_only",
                "summary",
                "targets",
            ],
            list(payload),
        )
        self.assertTrue(payload["summary_only"])
        self.assertEqual([], payload["selected_artifact_ids"])
        self.assertEqual([], payload["selected_failure_classes"])
        self.assertEqual(4, payload["summary"]["failure_count"])
        self.assertEqual(1, payload["summary"]["source_failure_count"])
        self.assertEqual(3, payload["summary"]["secondary_failure_count"])
        self.assertEqual(
            [
                {"key": "generic-file", "count": 1},
                {"key": "maven-repository", "count": 1},
                {"key": "oci-image", "count": 1},
                {"key": "source-artifact", "count": 1},
            ],
            payload["summary"]["failure_kinds"],
        )
        self.assertEqual(
            [
                {"key": "byte-mismatch", "count": 2},
                {"key": "digest-mismatch", "count": 1},
                {"key": "path-comparison-failed", "count": 1},
            ],
            payload["summary"]["failure_classes"],
        )
        self.assertEqual(
            [
                {"key": "secondary/generic-file/byte-mismatch", "count": 1},
                {
                    "key": "secondary/maven-repository/path-comparison-failed",
                    "count": 1,
                },
                {"key": "secondary/oci-image/digest-mismatch", "count": 1},
                {"key": "source/source-artifact/byte-mismatch", "count": 1},
            ],
            payload["summary"]["failure_groups"],
        )
        self.assertEqual(
            [
                "source-artifact",
                "bootstrap-zip",
                "maven-staging-main",
                "ghcr-main-image",
            ],
            [target["artifact_id"] for target in payload["targets"]],
        )
        self.assertEqual(
            ["source-artifact", "generic-file", "maven-repository", "oci-image"],
            [target["kind"] for target in payload["targets"]],
        )

    def test_inspect_repro_json_contract_for_selected_targets(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_selected_failure_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "source-generic-maven-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                    include_maven_repository=True,
                    include_maven_repository_reproducibility=True,
                    drift_maven_repository_reproducibility=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=(
                "--json",
                "--artifact-id",
                "source-artifact",
                "--artifact-id",
                "maven-staging-main",
            ),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        payload = json.loads(inspect_completed.stdout)
        self.assertEqual(
            ["source-artifact", "maven-staging-main"],
            payload["selected_artifact_ids"],
        )
        self.assertEqual(2, payload["summary"]["failure_count"])
        self.assertEqual(
            ["source-artifact", "maven-staging-main"],
            [target["artifact_id"] for target in payload["targets"]],
        )
        self.assertEqual(
            ["byte-mismatch", "path-comparison-failed"],
            [target["failure_class"] for target in payload["targets"]],
        )

    def test_inspect_repro_command_can_filter_to_selected_artifact_ids(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = (
            self._materialize_cached_source_and_generic_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "source-and-generic-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=("--artifact-id", "bootstrap-zip"),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Selected artifact ids: bootstrap-zip", inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 1", inspect_completed.stderr)
        self.assertIn(
            "Failure target: bootstrap-zip [generic-file] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertNotIn("Source Artifact 1/1", inspect_completed.stderr)
        self.assertIn("Artifact 1/1: bootstrap-zip", inspect_completed.stderr)

    def test_inspect_repro_command_can_filter_to_selected_failure_classes(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            drift_source_artifact=True,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
            include_maven_repository=True,
            include_maven_repository_reproducibility=True,
            drift_maven_repository_reproducibility=True,
        )
        verify_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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

        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = run_cli(
            [
                "inspect-repro",
                "--failure-class",
                "path-comparison-failed",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn(
            "Selected failure classes: path-comparison-failed", inspect_completed.stderr
        )
        self.assertIn("Reproducibility failures: 1", inspect_completed.stderr)
        self.assertIn(
            "Failure target: maven-staging-main [maven-repository] path-comparison-failed",
            inspect_completed.stderr,
        )
        self.assertNotIn(
            "Failure target: source-artifact [source-artifact] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertNotIn(
            "Failure target: bootstrap-zip [generic-file] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertIn("Artifact 1/1: maven-staging-main", inspect_completed.stderr)

    def test_inspect_repro_command_compact_mode_omits_deep_analysis(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = (
            self._materialize_cached_source_and_generic_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "source-and-generic-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=("--compact",),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn(
            "Compact mode requested; emitting compact per-artifact headers only",
            inspect_completed.stderr,
        )
        self.assertIn("Source Artifact 1/2", inspect_completed.stderr)
        self.assertIn("Artifact 2/2: bootstrap-zip", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertNotIn("Unified text diff", inspect_completed.stderr)
        self.assertNotIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Summarized 2 saved reproducibility failure(s) in compact mode",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_summary_only_skips_per_artifact_analysis(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = (
            self._materialize_cached_source_and_generic_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "source-and-generic-drift",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=("--summary-only",),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 2", inspect_completed.stderr)
        self.assertIn(
            "Failure target: source-artifact [source-artifact] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure target: bootstrap-zip [generic-file] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Summary-only mode requested; skipping per-artifact inspection",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Summarized 2 saved reproducibility failure(s)", inspect_completed.stderr
        )
        self.assertNotIn("Unified text diff", inspect_completed.stderr)
        self.assertNotIn("Artifact 1/2:", inspect_completed.stderr)

    def test_inspect_repro_command_summary_only_lists_all_targets_for_mixed_failures(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_mixed_failure_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_inspect_repro_result(
            "mixed-failures-all-kinds",
            build_family=lambda cache_dir: self._build_cached_verification_family(
                cache_dir,
                build_fixture=lambda family_dir: self._prepare_verification_fixture(
                    family_dir,
                    drift_source_artifact=True,
                    secondary_kind="generic-file",
                    include_generic_file_reproducibility=True,
                    drift_generic_file_reproducibility=True,
                    include_maven_repository=True,
                    include_maven_repository_reproducibility=True,
                    drift_maven_repository_reproducibility=True,
                    include_oci_image=True,
                    include_oci_image_reproducibility=True,
                    drift_oci_image_reproducibility_platform=True,
                ),
                verify_command=lambda cached_fixture: self._verify_rc_command(
                    cached_fixture,
                    mode="full",
                    inspection_bundle=True,
                ),
            ),
            inspect_args=("--summary-only",),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 4", inspect_completed.stderr)
        self.assertIn(
            "Failure groups: secondary/generic-file/byte-mismatch=1, "
            "secondary/maven-repository/path-comparison-failed=1, "
            "secondary/oci-image/digest-mismatch=1, source/source-artifact/byte-mismatch=1",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure group: source/source-artifact/byte-mismatch: source-artifact",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure group: secondary/generic-file/byte-mismatch: bootstrap-zip",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure group: secondary/maven-repository/path-comparison-failed: maven-staging-main",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure group: secondary/oci-image/digest-mismatch: ghcr-main-image",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure target: source-artifact [source-artifact] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure target: bootstrap-zip [generic-file] byte-mismatch",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure target: maven-staging-main [maven-repository] path-comparison-failed",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Failure target: ghcr-main-image [oci-image] digest-mismatch",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_rejects_unknown_selected_artifact_ids(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_generic_file_drift_inspect_result(
            "--artifact-id",
            "does-not-exist",
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            "requested inspect-repro artifact ids did not match any retained reproducibility failures: does-not-exist; available: bootstrap-zip",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_rejects_malformed_report_and_bundle_json(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        valid_report_text = fixture.report_json_path.read_text(encoding="utf-8")
        fixture.report_json_path.write_text("{\n", encoding="utf-8")
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            f"verify-rc report is not valid JSON: {fixture.report_json_path}",
            inspect_completed.stderr,
        )

        fixture.report_json_path.write_text(valid_report_text, encoding="utf-8")
        bundle_manifest_path = fixture.inspection_bundle_path / "inspection-bundle.json"
        bundle_manifest_path.write_text("{\n", encoding="utf-8")
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            f"inspection bundle manifest is not valid JSON: {bundle_manifest_path}",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_rejects_malformed_comparison_metadata(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        source_fixture, verify_completed = self._materialize_cached_source_drift_family(
            sandbox_dir
        )
        self.assertEqual(1, verify_completed.returncode)
        source_metadata_path = self._bundle_artifact_metadata_path(
            source_fixture.inspection_bundle_path,
            artifact_id="source-artifact",
        )
        source_metadata_path.write_text("{\n", encoding="utf-8")
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(source_fixture.report_json_path),
            ],
            cwd=source_fixture.origin_dir,
            env=self._fixture_cli_env(source_fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            f"source-artifact reproducibility metadata is not valid JSON: {source_metadata_path}",
            inspect_completed.stderr,
        )

        secondary_sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, secondary_sandbox_dir)
        secondary_fixture, verify_completed = (
            self._materialize_cached_generic_file_drift_family(secondary_sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        secondary_metadata_path = self._bundle_artifact_metadata_path(
            secondary_fixture.inspection_bundle_path,
            artifact_id="bootstrap-zip",
        )
        secondary_metadata_path.write_text("{\n", encoding="utf-8")
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(secondary_fixture.report_json_path),
            ],
            cwd=secondary_fixture.origin_dir,
            env=self._fixture_cli_env(secondary_fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            f"file-like reproducibility metadata is not valid JSON: {secondary_metadata_path}",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_reports_shallow_archive_drift_for_generic_file(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = (
            self._materialize_cached_generic_file_archive_drift_family(sandbox_dir)
        )
        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = self._cached_generic_file_archive_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: zip", inspect_completed.stderr)
        self.assertIn(
            "Archive drift classification: entry-content-drift",
            inspect_completed.stderr,
        )
        self.assertIn("Archive member-content mismatches", inspect_completed.stderr)
        self.assertIn(
            "Likely cause: one or more top-level archive member payloads changed",
            inspect_completed.stderr,
        )
        self.assertIn("bootstrap.txt", inspect_completed.stderr)

    def test_verify_rc_persists_shallow_archive_analysis_for_archive_backed_generic_file(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            archive_generic_file_reproducibility=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        reproducibility = report_payload["secondary_artifact_verifications"][0][
            "reproducibility"
        ]
        self.assertEqual(
            {
                "classification": "entries-match",
                "raw_bytes_equal": True,
                "archive_format": "zip",
                "staged_archive_format": "zip",
                "rebuilt_archive_format": "zip",
                "staged_entry_count": 1,
                "rebuilt_entry_count": 1,
                "missing_paths": [],
                "unexpected_paths": [],
                "entry_order_mismatches": [],
                "metadata_mismatches": [],
                "content_mismatches": [],
            },
            reproducibility["archive_analysis"],
        )
        metadata_reference = next(
            reference
            for reference in reproducibility["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            reproducibility["archive_analysis"], metadata_payload["archive_analysis"]
        )

    def test_inspect_repro_command_reports_saved_source_artifact_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_source_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        source_reproducibility = report_payload["source_artifact_verification"][
            "reproducibility"
        ]
        self.assertEqual(
            {"comparison-metadata", "staged-artifact", "rebuilt-artifact"},
            {evidence["label"] for evidence in source_reproducibility["evidence"]},
        )

        inspect_completed = self._cached_source_drift_inspect_result()

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Failure kinds: source-artifact=1", inspect_completed.stderr)
        self.assertIn("Source Artifact 1/1", inspect_completed.stderr)
        self.assertIn("Kind: source-artifact", inspect_completed.stderr)
        self.assertIn("Recipe source: verifier-internal", inspect_completed.stderr)
        self.assertIn(
            "Build command: internal:create-from-git", inspect_completed.stderr
        )
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertIn(
            "Retained evidence: comparison-metadata, staged-artifact, rebuilt-artifact",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Retained staged and rebuilt source-artifact copies differ",
            inspect_completed.stderr,
        )
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: tar", inspect_completed.stderr)
        self.assertIn(
            "Archive drift appears limited to the outer container or compression bytes",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Archive drift classification: outer-container-drift",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Likely cause: compression or outer-container bytes changed while extracted members stayed stable",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Source artifact hint: this often points to gzip or outer tarball container settings rather than source-tree content drift",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Top-level archive entries and member payloads match after shallow inspection",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Inspected 1 saved reproducibility failure(s)", inspect_completed.stderr
        )

    def test_inspect_repro_command_tolerates_missing_source_effective_execution(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_source_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        del report_payload["source_artifact_verification"]["reproducibility"][
            "effective_execution"
        ]
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2),
            encoding="utf-8",
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Source Artifact 1/1", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt source-artifact copies differ",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_tolerates_missing_canonical_recipe(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        del report_payload["secondary_artifact_verifications"][0]["reproducibility"][
            "canonical_recipe"
        ]
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertNotIn("Canonical build command:", inspect_completed.stderr)
        self.assertIn(
            "Build command: sh buildish-release-tooling/rebuild-bootstrap.sh",
            inspect_completed.stderr,
        )
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_tolerates_legacy_bundle_contract_fields(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        del report_payload["inspection_bundle"]["bundle_schema_version"]
        del report_payload["inspection_bundle"]["manifest_relative_path"]
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertNotIn("Bundle schema version:", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_rejects_unsupported_report_and_bundle_schema_versions(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        report_payload["schema_version"] = "99"
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            "unsupported verify-rc report schema version: '99'; supported: 1",
            inspect_completed.stderr,
        )

        report_payload["schema_version"] = "1"
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )
        bundle_manifest_path = fixture.inspection_bundle_path / "inspection-bundle.json"
        bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
        bundle_manifest["schema_version"] = "99"
        bundle_manifest_path.write_text(
            json.dumps(bundle_manifest, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            "unsupported inspection bundle manifest schema version: '99'; supported: 1",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_tolerates_missing_effective_execution(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, verify_completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        del report_payload["secondary_artifact_verifications"][0]["reproducibility"][
            "effective_execution"
        ]
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertNotIn("Build command:", inspect_completed.stderr)
        self.assertNotIn("Build working directory:", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_tolerates_override_without_build_payload(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
        )
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    bootstrap-zip:",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-bootstrap-local.sh",
                ]
            ),
            encoding="utf-8",
        )
        verify_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                "--repro-override-file",
                str(override_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        report_payload["secondary_artifact_verifications"][0]["reproducibility"][
            "override"
        ] = {"applied": True}
        fixture.report_json_path.write_text(
            json.dumps(report_payload, indent=2) + "\n", encoding="utf-8"
        )

        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Recipe source: local-override", inspect_completed.stderr)
        self.assertNotIn("Override fields:", inspect_completed.stderr)
        self.assertIn(
            "Retained staged and rebuilt artifact copies differ",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_reports_override_metadata_for_failed_generic_file_drift(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            include_reproducibility=True,
            drift_reproducibility=True,
        )
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    bootstrap-zip:",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-bootstrap-local.sh",
                ]
            ),
            encoding="utf-8",
        )
        verify_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                "--repro-override-file",
                str(override_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, verify_completed.returncode)
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Recipe source: local-override", inspect_completed.stderr)
        self.assertIn(
            "Build command: sh buildish-release-tooling/rebuild-bootstrap-local.sh",
            inspect_completed.stderr,
        )
        self.assertIn("Override fields: build.command", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
