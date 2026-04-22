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
"""Verify-rc command report and contract tests."""

from tests.release.commands.support import _read_simple_github_outputs
from tests.release.commands.verification_support import (
    BundleMetadataShapeCase,
    VerificationCommandsIntegrationTestBase,
    cleanup_sandbox,
    cli_env,
    command_available,
    create_build_test_sandbox,
    json,
    os,
    run_cli,
)


class VerificationCommandContractTest(VerificationCommandsIntegrationTestBase):
    """Verify-rc command report and contract tests."""

    def test_verify_rc_command_reports_progress_for_successful_run(self) -> None:
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
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--report-md",
                str(fixture.report_md_path),
                "--log-path",
                str(fixture.log_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual("", completed.stdout)
        self.assertIn("Verify RC\n=========", completed.stderr)
        self.assertIn("Vote Manifest\n-------------", completed.stderr)
        self.assertIn("Source Artifact\n---------------", completed.stderr)
        self.assertIn("Secondary Artifacts\n-------------------", completed.stderr)
        self.assertIn("Secondary Artifact 1/1: maven-staging-main", completed.stderr)
        self.assertIn(
            f"SOURCE_DATE_EPOCH: {fixture.source_date_epoch}", completed.stderr
        )
        self.assertIn("✓ Verified manifest signature: ", completed.stderr)
        self.assertIn("✓ Verified rc_tag binding: v1.2.3-rc0 -> ", completed.stderr)
        self.assertIn("✓ Verified staged source SHA512: ", completed.stderr)
        self.assertIn("✓ Verified source artifact signature: ", completed.stderr)
        self.assertIn("• Enumerating live repository from ", completed.stderr)
        self.assertIn("✓ Verified maven repository inventory: ", completed.stderr)
        self.assertIn("Outcome\n-------", completed.stderr)
        self.assertIn(
            "✓ Verified RC: buildish-example 1.2.3 (v1.2.3-rc0)", completed.stderr
        )
        self.assertIn("  Report JSON: ", completed.stderr)
        self.assertIn("  Report Markdown: ", completed.stderr)
        self.assertIn(f"  Transcript log: {fixture.log_path}", completed.stderr)
        self.assertNotIn("progress:", completed.stderr)
        self.assertNotIn("+ git", completed.stderr)
        self.assertNotIn("+ gpg", completed.stderr)
        self.assertTrue(fixture.log_path.is_file())
        log_text = fixture.log_path.read_text(encoding="utf-8")
        self.assertIn("Verify RC\n=========", log_text)
        self.assertIn("+ git clone --quiet", log_text)
        self.assertIn("+ gpg --batch --quiet --import", log_text)

    def test_verify_rc_report_shapes_cover_representative_variants(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        success_fixture = self._prepare_verification_fixture(
            sandbox_dir / "success",
            include_maven_repository=True,
        )
        success_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(success_fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(success_fixture.work_dir),
                "--report-json",
                str(success_fixture.report_json_path),
                success_fixture.manifest_url,
                success_fixture.keys_url,
            ],
            cwd=success_fixture.origin_dir,
            env=self._fixture_cli_env(success_fixture),
        )
        self.assertEqual(0, success_completed.returncode, msg=success_completed.stderr)
        success_shape = self._report_shape(
            json.loads(success_fixture.report_json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual(
            {
                "top_level_keys": [
                    "schema_version",
                    "report_type",
                    "component_id",
                    "version",
                    "rc_tag",
                    "source_commit_sha",
                    "source_date_epoch",
                    "source_repository_url",
                    "manifest_url",
                    "keys_url",
                    "verdict",
                    "work_dir",
                    "failures",
                    "manifest_verification",
                    "source_artifact_verification",
                    "reproducibility_execution",
                    "inspection_bundle",
                    "secondary_artifact_verifications",
                ],
                "verdict": "verified",
                "failure_count": 0,
                "inspection_bundle_keys": [
                    "relative_path_from_report",
                    "bundle_schema_version",
                    "manifest_relative_path",
                ],
                "source_repro": {
                    "keys": [
                        "profile_id",
                        "verdict",
                        "comparison_mode",
                        "canonical_recipe",
                        "effective_execution",
                        "override",
                        "matches_remote_bytes",
                        "failure_class",
                        "archive_analysis",
                        "evidence",
                        "issues",
                    ],
                    "verdict": "verified",
                    "profile_id": "source-artifact-from-git",
                    "comparison_mode": "exact-bytes",
                    "canonical_recipe_keys": None,
                    "effective_execution_keys": ["backend", "build"],
                    "override_keys": ["applied", "build"],
                    "override_applied": False,
                },
                "secondary_repro": {"maven-staging-main": None},
            },
            success_shape,
        )

        mixed_failure_fixture = self._prepare_verification_fixture(
            sandbox_dir / "mixed-failure",
            include_maven_repository=True,
            drift_maven_repository=True,
            include_npm_package=True,
            drift_npm_tarball=True,
            drift_source_artifact=True,
        )
        mixed_failure_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(mixed_failure_fixture.config_path),
                "--test-target-mode",
                "--work-dir",
                str(mixed_failure_fixture.work_dir),
                "--report-json",
                str(mixed_failure_fixture.report_json_path),
                mixed_failure_fixture.manifest_url,
                mixed_failure_fixture.keys_url,
            ],
            cwd=mixed_failure_fixture.origin_dir,
            env=self._fixture_cli_env(mixed_failure_fixture),
        )
        self.assertEqual(1, mixed_failure_completed.returncode)
        mixed_failure_shape = self._report_shape(
            json.loads(
                mixed_failure_fixture.report_json_path.read_text(encoding="utf-8")
            )
        )
        self.assertEqual("failed", mixed_failure_shape["verdict"])
        self.assertEqual(8, mixed_failure_shape["failure_count"])
        self.assertEqual(
            [
                "relative_path_from_report",
                "bundle_schema_version",
                "manifest_relative_path",
            ],
            mixed_failure_shape["inspection_bundle_keys"],
        )
        self.assertEqual(
            {
                "keys": [
                    "profile_id",
                    "verdict",
                    "comparison_mode",
                    "canonical_recipe",
                    "effective_execution",
                    "override",
                    "matches_remote_bytes",
                    "failure_class",
                    "archive_analysis",
                    "evidence",
                    "issues",
                ],
                "verdict": "failed",
                "profile_id": "source-artifact-from-git",
                "comparison_mode": "exact-bytes",
                "canonical_recipe_keys": None,
                "effective_execution_keys": ["backend", "build"],
                "override_keys": ["applied", "build"],
                "override_applied": False,
            },
            mixed_failure_shape["source_repro"],
        )
        self.assertEqual(
            {
                "maven-staging-main": None,
                "npm-package-main": None,
            },
            mixed_failure_shape["secondary_repro"],
        )

        full_repro_fixture = self._prepare_generic_file_fixture(
            sandbox_dir / "full-repro",
            include_reproducibility=True,
        )
        full_repro_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(full_repro_fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(full_repro_fixture.work_dir),
                "--report-json",
                str(full_repro_fixture.report_json_path),
                "--inspection-bundle",
                str(full_repro_fixture.inspection_bundle_path),
                full_repro_fixture.manifest_url,
                full_repro_fixture.keys_url,
            ],
            cwd=full_repro_fixture.origin_dir,
            env=self._fixture_cli_env(full_repro_fixture),
        )
        self.assertEqual(
            0, full_repro_completed.returncode, msg=full_repro_completed.stderr
        )
        full_repro_shape = self._report_shape(
            json.loads(full_repro_fixture.report_json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual("verified", full_repro_shape["verdict"])
        self.assertEqual(
            [
                "relative_path_from_report",
                "bundle_schema_version",
                "manifest_relative_path",
            ],
            full_repro_shape["inspection_bundle_keys"],
        )
        full_secondary_repro = full_repro_shape["secondary_repro"]
        if not isinstance(full_secondary_repro, dict):
            self.fail("secondary_repro must be a mapping")
        self.assertEqual(
            {
                "keys": [
                    "profile_id",
                    "verdict",
                    "comparison_mode",
                    "canonical_recipe",
                    "effective_execution",
                    "override",
                    "matches_remote_bytes",
                    "failure_class",
                    "archive_analysis",
                    "evidence",
                    "issues",
                ],
                "verdict": "verified",
                "profile_id": "bootstrap-zip",
                "comparison_mode": "exact-bytes",
                "canonical_recipe_keys": ["build"],
                "effective_execution_keys": ["backend", "build"],
                "override_keys": ["applied", "build"],
                "override_applied": False,
            },
            full_secondary_repro["bootstrap-zip"],
        )

        override_fixture = self._prepare_generic_file_fixture(
            sandbox_dir / "override",
            include_reproducibility=True,
        )
        override_path = sandbox_dir / "override" / "repro-overrides.yaml"
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
                    "",
                ]
            ),
            encoding="utf-8",
        )
        override_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(override_fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--work-dir",
                str(override_fixture.work_dir),
                "--report-json",
                str(override_fixture.report_json_path),
                "--inspection-bundle",
                str(override_fixture.inspection_bundle_path),
                "--repro-override-file",
                str(override_path),
                override_fixture.manifest_url,
                override_fixture.keys_url,
            ],
            cwd=override_fixture.origin_dir,
            env=self._fixture_cli_env(override_fixture),
        )
        self.assertEqual(
            0, override_completed.returncode, msg=override_completed.stderr
        )
        override_shape = self._report_shape(
            json.loads(override_fixture.report_json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual("verified", override_shape["verdict"])
        override_secondary_repro = override_shape["secondary_repro"]
        if not isinstance(override_secondary_repro, dict):
            self.fail("secondary_repro must be a mapping")
        self.assertEqual(
            {
                "keys": [
                    "profile_id",
                    "verdict",
                    "comparison_mode",
                    "canonical_recipe",
                    "effective_execution",
                    "override",
                    "matches_remote_bytes",
                    "failure_class",
                    "archive_analysis",
                    "evidence",
                    "issues",
                ],
                "verdict": "verified",
                "profile_id": "bootstrap-zip",
                "comparison_mode": "exact-bytes",
                "canonical_recipe_keys": ["build"],
                "effective_execution_keys": ["backend", "build"],
                "override_keys": ["applied", "build"],
                "override_applied": True,
            },
            override_secondary_repro["bootstrap-zip"],
        )

    def test_verify_rc_command_colors_human_transcript_but_not_log_file(self) -> None:
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
                "--progress",
                "on",
                "--color",
                "always",
                "--work-dir",
                str(fixture.work_dir),
                "--log-path",
                str(fixture.log_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("\x1b[1mVerify RC\x1b[0m", completed.stderr)
        self.assertIn("\x1b[1;36mVote Manifest\x1b[0m", completed.stderr)
        self.assertIn("\x1b[32m✓ Verified manifest signature: ", completed.stderr)
        self.assertIn(
            "\x1b[32m✓ Verified RC: buildish-example 1.2.3 (v1.2.3-rc0)\x1b[0m",
            completed.stderr,
        )
        self.assertNotIn("\x1b[", fixture.log_path.read_text(encoding="utf-8"))

    def test_verify_rc_bundle_metadata_shapes_cover_artifact_kinds(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        cases = (
            BundleMetadataShapeCase(
                name="source-and-generic",
                build_fixture=lambda case_dir: self._prepare_generic_file_fixture(
                    case_dir,
                    include_reproducibility=True,
                ),
                expected={
                    "source-artifact/reproducibility/metadata.json": {
                        "keys": [
                            "profile_id",
                            "comparison_mode",
                            "failure_class",
                            "archive_analysis",
                            "staged_artifact",
                            "rebuilt_artifact",
                            "matches_remote_bytes",
                            "issues",
                        ],
                        "kind": None,
                        "profile_id": "source-artifact-from-git",
                        "comparison_mode": "exact-bytes",
                        "canonical_recipe_keys": None,
                        "effective_execution_keys": None,
                        "override_keys": None,
                        "override_applied": None,
                        "archive_analysis_keys": [
                            "classification",
                            "raw_bytes_equal",
                            "archive_format",
                            "staged_archive_format",
                            "rebuilt_archive_format",
                            "staged_entry_count",
                            "rebuilt_entry_count",
                            "missing_paths",
                            "unexpected_paths",
                            "entry_order_mismatches",
                            "metadata_mismatches",
                            "content_mismatches",
                        ],
                    },
                    "secondary-artifacts/bootstrap-zip/reproducibility/metadata.json": {
                        "keys": [
                            "artifact_id",
                            "kind",
                            "profile_id",
                            "comparison_mode",
                            "canonical_recipe",
                            "effective_execution",
                            "override",
                            "failure_class",
                            "archive_analysis",
                            "staged_artifact",
                            "rebuilt_outputs",
                            "matches_remote_bytes",
                            "issues",
                        ],
                        "kind": "generic-file",
                        "profile_id": "bootstrap-zip",
                        "comparison_mode": "exact-bytes",
                        "canonical_recipe_keys": ["build"],
                        "effective_execution_keys": ["backend", "build"],
                        "override_keys": ["applied", "build"],
                        "override_applied": False,
                        "archive_analysis_keys": None,
                    },
                },
            ),
            BundleMetadataShapeCase(
                name="python",
                build_fixture=lambda case_dir: (
                    self._prepare_python_distribution_fixture(
                        case_dir,
                        include_reproducibility=True,
                    )
                ),
                expected={
                    "secondary-artifacts/pypi-wheel/reproducibility/metadata.json": {
                        "keys": [
                            "artifact_id",
                            "kind",
                            "profile_id",
                            "comparison_mode",
                            "canonical_recipe",
                            "effective_execution",
                            "override",
                            "failure_class",
                            "archive_analysis",
                            "staged_artifact",
                            "rebuilt_outputs",
                            "matches_remote_bytes",
                            "issues",
                        ],
                        "kind": "python-distribution",
                        "profile_id": "pypi-wheel",
                        "comparison_mode": "exact-bytes",
                        "canonical_recipe_keys": ["build"],
                        "effective_execution_keys": ["backend", "build"],
                        "override_keys": ["applied", "build"],
                        "override_applied": False,
                        "archive_analysis_keys": None,
                    },
                },
            ),
            BundleMetadataShapeCase(
                name="npm",
                build_fixture=lambda case_dir: self._prepare_npm_package_fixture(
                    case_dir,
                    include_reproducibility=True,
                ),
                expected={
                    "secondary-artifacts/npm-package-main/reproducibility/metadata.json": {
                        "keys": [
                            "artifact_id",
                            "kind",
                            "profile_id",
                            "comparison_mode",
                            "canonical_recipe",
                            "effective_execution",
                            "override",
                            "failure_class",
                            "archive_analysis",
                            "staged_artifact",
                            "rebuilt_outputs",
                            "matches_remote_bytes",
                            "issues",
                        ],
                        "kind": "npm-package",
                        "profile_id": "npm-package-main",
                        "comparison_mode": "exact-bytes",
                        "canonical_recipe_keys": ["build"],
                        "effective_execution_keys": ["backend", "build"],
                        "override_keys": ["applied", "build"],
                        "override_applied": False,
                        "archive_analysis_keys": None,
                    },
                },
            ),
            BundleMetadataShapeCase(
                name="maven",
                build_fixture=lambda case_dir: self._prepare_maven_repository_fixture(
                    case_dir,
                    include_reproducibility=True,
                ),
                expected={
                    "secondary-artifacts/maven-staging-main/reproducibility/metadata.json": {
                        "keys": [
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
                        "kind": "maven-repository",
                        "profile_id": "maven-staging",
                        "comparison_mode": "repository-tree",
                        "canonical_recipe_keys": ["build"],
                        "effective_execution_keys": ["backend", "build"],
                        "override_keys": ["applied", "build"],
                        "override_applied": False,
                        "archive_analysis_keys": None,
                    },
                },
            ),
            BundleMetadataShapeCase(
                name="oci",
                build_fixture=lambda case_dir: self._prepare_oci_image_fixture(
                    case_dir,
                    include_reproducibility=True,
                ),
                expected={
                    "secondary-artifacts/ghcr-main-image/reproducibility/metadata.json": {
                        "keys": [
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
                        "kind": "oci-image",
                        "profile_id": "oci-main-image",
                        "comparison_mode": "platform-digest",
                        "canonical_recipe_keys": ["build"],
                        "effective_execution_keys": ["backend", "build"],
                        "override_keys": ["applied", "build"],
                        "override_applied": False,
                        "archive_analysis_keys": None,
                    },
                },
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                case_dir = sandbox_dir / case.name
                case_dir.mkdir(parents=True, exist_ok=True)
                fixture = case.build_fixture(case_dir)
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
                observed_shapes = {
                    metadata_path: self._bundle_metadata_shape(
                        fixture.inspection_bundle_path,
                        metadata_path=metadata_path,
                    )
                    for metadata_path in case.expected
                }
                self.assertEqual(case.expected, observed_shapes)

    def test_verify_rc_report_contract_for_successful_full_multi_artifact_run(
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
            include_python_distribution=True,
            include_python_distribution_reproducibility=True,
            include_npm_package=True,
            include_npm_package_reproducibility=True,
            include_maven_repository=True,
            include_maven_repository_reproducibility=True,
            include_oci_image=True,
            include_oci_image_reproducibility=True,
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
        self.assertEqual("verified", report_payload["verdict"])
        self.assertEqual(5, len(report_payload["secondary_artifact_verifications"]))
        bundle_manifest = json.loads(
            (fixture.inspection_bundle_path / "inspection-bundle.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [
                "source-artifact/reproducibility/metadata.json",
                "secondary-artifacts/bootstrap-zip/reproducibility/metadata.json",
                "secondary-artifacts/maven-staging-main/reproducibility/metadata.json",
                "secondary-artifacts/pypi-wheel/reproducibility/metadata.json",
                "secondary-artifacts/npm-package-main/reproducibility/metadata.json",
                "secondary-artifacts/ghcr-main-image/reproducibility/metadata.json",
            ],
            [artifact["metadata_path"] for artifact in bundle_manifest["artifacts"]],
        )
        secondary_by_id = {
            verification["artifact_id"]: verification
            for verification in report_payload["secondary_artifact_verifications"]
        }
        self.assertEqual(
            "verified", secondary_by_id["bootstrap-zip"]["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "verified", secondary_by_id["pypi-wheel"]["reproducibility"]["verdict"]
        )
        self.assertEqual(
            "verified",
            secondary_by_id["npm-package-main"]["reproducibility"]["verdict"],
        )
        self.assertEqual(
            "verified",
            secondary_by_id["maven-staging-main"]["reproducibility"]["verdict"],
        )
        self.assertEqual(
            "verified", secondary_by_id["ghcr-main-image"]["reproducibility"]["verdict"]
        )

    def test_verify_rc_report_contract_for_override_run_bundle_metadata(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            include_reproducibility=True,
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
                    "        env:",
                    '          LOCAL_ONLY_FLAG: "1"',
                    "",
                ]
            ),
            encoding="utf-8",
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
                "--repro-override-file",
                str(override_path),
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
        self.assertEqual(True, reproducibility["override"]["applied"])
        self.assertEqual(
            ["LOCAL_ONLY_FLAG"],
            reproducibility["override"]["build"]["env_keys"],
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
        self.assertEqual(reproducibility["override"], metadata_payload["override"])
        self.assertEqual(
            ["LOCAL_ONLY_FLAG"],
            metadata_payload["override"]["build"]["env_keys"],
        )

    def test_verify_rc_command_verifies_manifest_source_and_rc_tag_binding(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(sandbox_dir)
        outputs_path = sandbox_dir / "verify-rc.outputs"
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
                "--report-md",
                str(fixture.report_md_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(
                fixture,
                extra_env={"GITHUB_OUTPUT": str(outputs_path)},
            ),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("verified", report_payload["verdict"])
        self.assertEqual(fixture.source_date_epoch, report_payload["source_date_epoch"])
        self.assertTrue(
            report_payload["manifest_verification"]["rc_tag_matches_source_commit_sha"]
        )
        self.assertTrue(
            report_payload["source_artifact_verification"]["matches_source_commit_sha"]
        )
        self.assertEqual(
            fixture.source_commit_sha,
            report_payload["manifest_verification"]["rc_tag_target_commit"],
        )
        self.assertIn(
            f"| SOURCE_DATE_EPOCH | `{fixture.source_date_epoch}` |",
            fixture.report_md_path.read_text(encoding="utf-8"),
        )

        github_outputs = _read_simple_github_outputs(outputs_path)
        self.assertEqual("v1.2.3-rc0", github_outputs["rc_tag"])
        self.assertEqual(fixture.source_commit_sha, github_outputs["source_commit_sha"])
        self.assertEqual(
            str(fixture.source_date_epoch), github_outputs["source_date_epoch"]
        )

    def test_verify_rc_command_verifies_generic_secondary_artifact_with_openpgp(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file-with-openpgp",
        )
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
                "--report-md",
                str(fixture.report_md_path),
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
        self.assertEqual("verified", report_payload["verdict"])
        self.assertEqual(1, len(report_payload["secondary_artifact_verifications"]))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("generic-file-with-openpgp", secondary_verification["kind"])
        self.assertEqual("verified", secondary_verification["verdict"])
        self.assertEqual("sha512", secondary_verification["checksum"]["algorithm"])
        self.assertEqual(1, len(secondary_verification["signatures"]))
        self.assertIn(
            "Secondary artifact verification",
            fixture.report_md_path.read_text(encoding="utf-8"),
        )

    def test_verify_rc_command_verifies_generic_file_reproducibility_in_full_mode(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
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
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--report-md",
                str(fixture.report_md_path),
                "--inspection-bundle",
                str(fixture.inspection_bundle_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("Local Reproducibility", completed.stderr)
        self.assertIn("Requested mode: full", completed.stderr)
        self.assertIn("Effective mode: full", completed.stderr)
        self.assertIn(
            "Verified rebuilt artifact matches staged bytes", completed.stderr
        )
        self.assertIn("Recipe source: canonical-profile", completed.stderr)
        self.assertIn(
            "Build command: sh buildish-release-tooling/rebuild-bootstrap.sh",
            completed.stderr,
        )
        self.assertIn("Build working directory: .", completed.stderr)
        self.assertIn(
            "Injected environment keys: BUILDISH_PROJECT_ROOT, BUILDISH_SOURCE_DATE_EPOCH, BUILDISH_WORK_DIR, SOURCE_DATE_EPOCH, TMPDIR",
            completed.stderr,
        )
        self.assertNotIn("Override fields:", completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            [
                "schema_version",
                "report_type",
                "component_id",
                "version",
                "rc_tag",
                "source_commit_sha",
                "source_date_epoch",
                "source_repository_url",
                "manifest_url",
                "keys_url",
                "verdict",
                "work_dir",
                "failures",
                "manifest_verification",
                "source_artifact_verification",
                "reproducibility_execution",
                "inspection_bundle",
                "secondary_artifact_verifications",
            ],
            list(report_payload),
        )
        self.assertEqual(
            "full", report_payload["reproducibility_execution"]["requested_mode"]
        )
        self.assertEqual(
            "full", report_payload["reproducibility_execution"]["effective_mode"]
        )
        self.assertTrue(
            report_payload["reproducibility_execution"]["build_checks_attempted"]
        )
        self.assertEqual(
            os.path.relpath(
                fixture.inspection_bundle_path, start=fixture.report_json_path.parent
            ),
            report_payload["inspection_bundle"]["relative_path_from_report"],
        )
        self.assertEqual(
            "1", report_payload["inspection_bundle"]["bundle_schema_version"]
        )
        self.assertEqual(
            "inspection-bundle.json",
            report_payload["inspection_bundle"]["manifest_relative_path"],
        )
        bundle_manifest = json.loads(
            (fixture.inspection_bundle_path / "inspection-bundle.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            [
                "schema_version",
                "bundle_type",
                "report_type",
                "report_schema_version",
                "component_id",
                "version",
                "rc_tag",
                "artifacts",
            ],
            list(bundle_manifest),
        )
        self.assertEqual("1", bundle_manifest["schema_version"])
        self.assertEqual("verify-rc-inspection", bundle_manifest["bundle_type"])
        self.assertEqual("verify-rc", bundle_manifest["report_type"])
        self.assertEqual("1", bundle_manifest["report_schema_version"])
        self.assertEqual(
            [
                {
                    "artifact_id": "source-artifact",
                    "kind": "source-artifact",
                    "metadata_path": "source-artifact/reproducibility/metadata.json",
                },
                {
                    "artifact_id": "bootstrap-zip",
                    "kind": "generic-file",
                    "metadata_path": "secondary-artifacts/bootstrap-zip/reproducibility/metadata.json",
                },
            ],
            bundle_manifest["artifacts"],
        )
        source_reproducibility = report_payload["source_artifact_verification"][
            "reproducibility"
        ]
        self.assertEqual(
            [
                "profile_id",
                "verdict",
                "comparison_mode",
                "canonical_recipe",
                "effective_execution",
                "override",
                "matches_remote_bytes",
                "failure_class",
                "archive_analysis",
                "evidence",
                "issues",
            ],
            list(source_reproducibility),
        )
        self.assertEqual("verified", source_reproducibility["verdict"])
        self.assertEqual(
            "source-artifact-from-git", source_reproducibility["profile_id"]
        )
        self.assertEqual("exact-bytes", source_reproducibility["comparison_mode"])
        self.assertEqual(False, source_reproducibility["override"]["applied"])
        self.assertEqual(
            ["internal:create-from-git"],
            source_reproducibility["effective_execution"]["build"]["command"],
        )
        self.assertEqual(
            ["rebuilt-apache-buildish-example-1.2.3-incubating-src.tar.gz"],
            source_reproducibility["effective_execution"]["build"]["output_paths"],
        )
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        reproducibility = secondary_verification["reproducibility"]
        self.assertEqual(
            [
                "profile_id",
                "verdict",
                "comparison_mode",
                "canonical_recipe",
                "effective_execution",
                "override",
                "matches_remote_bytes",
                "failure_class",
                "archive_analysis",
                "evidence",
                "issues",
            ],
            list(reproducibility),
        )
        self.assertEqual(
            "verified", secondary_verification["reproducibility"]["verdict"]
        )
        self.assertEqual("bootstrap-zip", reproducibility["profile_id"])
        self.assertEqual(False, reproducibility["override"]["applied"])
        self.assertEqual(
            ["dist/buildish-example-bootstrap.zip"],
            reproducibility["effective_execution"]["build"]["output_paths"],
        )
        self.assertEqual(
            ["sh", "buildish-release-tooling/rebuild-bootstrap.sh"],
            reproducibility["effective_execution"]["build"]["command"],
        )
        self.assertEqual(
            ".",
            reproducibility["effective_execution"]["build"]["working_directory"],
        )
        self.assertEqual(
            [
                "BUILDISH_PROJECT_ROOT",
                "BUILDISH_SOURCE_DATE_EPOCH",
                "BUILDISH_WORK_DIR",
                "SOURCE_DATE_EPOCH",
                "TMPDIR",
            ],
            reproducibility["effective_execution"]["build"][
                "injected_environment_keys"
            ],
        )
        self.assertEqual(
            ["sh", "buildish-release-tooling/rebuild-bootstrap.sh"],
            reproducibility["canonical_recipe"]["build"]["command"],
        )
        self.assertIn(
            f"  Inspect reproducibility: buildish-release-tooling inspect-repro {fixture.report_json_path}",
            completed.stderr,
        )
        self.assertEqual(
            ["comparison-metadata"],
            [
                evidence["label"]
                for evidence in secondary_verification["reproducibility"]["evidence"]
            ],
        )
        report_markdown = fixture.report_md_path.read_text(encoding="utf-8")
        self.assertIn("Reproducibility verdict: `verified`", report_markdown)
        self.assertIn("Source recipe source: `verifier-internal`", report_markdown)
        self.assertIn("Source reproducibility verdict: `verified`", report_markdown)
        self.assertIn(
            "Source rebuild command: `internal:create-from-git`", report_markdown
        )
        self.assertIn("Execution backend: `host-direct`", report_markdown)
        self.assertIn(
            "Build command: `sh buildish-release-tooling/rebuild-bootstrap.sh`",
            report_markdown,
        )
        self.assertIn("Build working directory: `.`", report_markdown)

    def test_verify_rc_command_uses_local_repro_override_file_for_generic_file(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            include_reproducibility=True,
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
                    "",
                ]
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--report-md",
                str(fixture.report_md_path),
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

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("Recipe source: local-override", completed.stderr)
        self.assertIn("Override fields: build.command", completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        reproducibility = report_payload["secondary_artifact_verifications"][0][
            "reproducibility"
        ]
        self.assertEqual(True, reproducibility["override"]["applied"])
        self.assertEqual(
            ["sh", "buildish-release-tooling/rebuild-bootstrap-local.sh"],
            reproducibility["override"]["build"]["command"],
        )
        self.assertEqual(
            [
                "profile_id",
                "verdict",
                "comparison_mode",
                "canonical_recipe",
                "effective_execution",
                "override",
                "matches_remote_bytes",
                "failure_class",
                "archive_analysis",
                "evidence",
                "issues",
            ],
            list(reproducibility),
        )
        self.assertEqual(
            ["applied", "build"],
            list(reproducibility["override"]),
        )
        self.assertEqual(
            ["command", "working_directory", "output_globs", "env_keys"],
            list(reproducibility["override"]["build"]),
        )

    def test_verify_rc_command_does_not_report_override_env_values(self) -> None:
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
        redaction_probe_value = "probe-value-123"
        redaction_probe_url = "https://user:pass@example.invalid/simple"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    bootstrap-zip:",
                    "      build:",
                    "        env:",
                    f"          MY_TOKEN: {redaction_probe_value}",
                    f"          PIP_INDEX_URL: {redaction_probe_url}",
                ]
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--report-md",
                str(fixture.report_md_path),
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

        self.assertEqual(1, completed.returncode)
        report_json = fixture.report_json_path.read_text(encoding="utf-8")
        report_markdown = fixture.report_md_path.read_text(encoding="utf-8")
        inspect_completed = run_cli(
            [
                "inspect-repro",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        for rendered_text in (
            completed.stderr,
            report_json,
            report_markdown,
            inspect_completed.stderr,
        ):
            self.assertNotIn(redaction_probe_value, rendered_text)
            self.assertNotIn(redaction_probe_url, rendered_text)
        self.assertIn("build.env.MY_TOKEN", completed.stderr)
        self.assertIn("build.env.PIP_INDEX_URL", completed.stderr)
        reproducibility = json.loads(report_json)["secondary_artifact_verifications"][
            0
        ]["reproducibility"]
        self.assertEqual(
            ["MY_TOKEN", "PIP_INDEX_URL"],
            reproducibility["override"]["build"]["env_keys"],
        )

    def test_verify_rc_command_ignores_valid_override_for_unused_profile(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            extra_verify_rc_profile_lines=(
                "    unused-local-profile:",
                "      kind: generic-file",
                "      build:",
                "        command:",
                "          - sh",
                "          - buildish-release-tooling/rebuild-bootstrap-local.sh",
                "        output_globs:",
                "          - dist/buildish-example-bootstrap.zip",
                "      comparison:",
                "        mode: exact-bytes",
            ),
        )
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    unused-local-profile:",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-bootstrap-local.sh",
                ]
            ),
            encoding="utf-8",
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--repro-override-file",
                str(override_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertIn("Recipe source: canonical-profile", completed.stderr)
        self.assertNotIn("Override fields:", completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        reproducibility = report_payload["secondary_artifact_verifications"][0][
            "reproducibility"
        ]
        self.assertEqual(False, reproducibility["override"]["applied"])

    def test_verify_rc_command_applies_one_override_to_two_artifacts_sharing_profile(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            include_reproducibility=True,
            include_second_shared_profile=True,
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
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--mode",
                "full",
                "--progress",
                "on",
                "--work-dir",
                str(fixture.work_dir),
                "--report-json",
                str(fixture.report_json_path),
                "--repro-override-file",
                str(override_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        self.assertEqual(2, completed.stderr.count("Recipe source: local-override"))
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual(2, len(report_payload["secondary_artifact_verifications"]))
        for secondary_verification in report_payload[
            "secondary_artifact_verifications"
        ]:
            reproducibility = secondary_verification["reproducibility"]
            self.assertEqual(True, reproducibility["override"]["applied"])
            self.assertEqual(
                ["sh", "buildish-release-tooling/rebuild-bootstrap-local.sh"],
                reproducibility["override"]["build"]["command"],
            )
            self.assertEqual(
                "bootstrap-zip",
                reproducibility["profile_id"],
            )

    def test_verify_rc_command_rejects_repro_override_file_without_component_config(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    bootstrap-zip:",
                    "      build:",
                    '        command: ["./buildish-release-tooling/rebuild-bootstrap-local.sh"]',
                ]
            ),
            encoding="utf-8",
        )

        completed = run_cli(
            [
                "verify-rc",
                "--repro-override-file",
                str(override_path),
                "https://example.invalid/rc-vote-manifest.json",
                "https://example.invalid/KEYS",
            ],
            cwd=sandbox_dir,
            env=cli_env(sandbox_dir / "cli-manifest.json"),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "--repro-override-file requires --component-config", completed.stderr
        )

    def test_verify_rc_command_rejects_repro_override_file_with_unknown_profile_id(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            verify_rc_lines=(
                "verify_rc:",
                "  profiles:",
                "    bootstrap-zip:",
                "      kind: generic-file",
                "      build:",
                '        command: ["./buildish-release-tooling/rebuild-bootstrap.sh"]',
                "        output_globs:",
                "          - dist/buildish-example-bootstrap.zip",
                "      comparison:",
                "        mode: exact-bytes",
            ),
        )
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    missing-profile:",
                    "      build:",
                    '        command: ["./buildish-release-tooling/rebuild-bootstrap-local.sh"]',
                ]
            ),
            encoding="utf-8",
        )

        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(config_path),
                "--repro-override-file",
                str(override_path),
                "https://example.invalid/rc-vote-manifest.json",
                "https://example.invalid/KEYS",
            ],
            cwd=sandbox_dir,
            env=cli_env(sandbox_dir / "cli-manifest.json"),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("unknown verify_rc profile_id", completed.stderr)

    def test_verify_rc_command_rejects_empty_repro_override_build_block(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)
        config_path = sandbox_dir / "component.yaml"
        self._write_component_config(
            config_path,
            component_id="buildish-example",
            dev_base_url="https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example",
            release_base_url="https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example",
            verify_rc_lines=(
                "verify_rc:",
                "  profiles:",
                "    bootstrap-zip:",
                "      kind: generic-file",
                "      build:",
                '        command: ["./buildish-release-tooling/rebuild-bootstrap.sh"]',
                "        output_globs:",
                "          - dist/buildish-example-bootstrap.zip",
                "      comparison:",
                "        mode: exact-bytes",
            ),
        )
        override_path = sandbox_dir / "repro-overrides.yaml"
        override_path.write_text(
            "\n".join(
                [
                    "verify_rc:",
                    "  profile_overrides:",
                    "    bootstrap-zip:",
                    "      build: {}",
                ]
            ),
            encoding="utf-8",
        )

        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(config_path),
                "--repro-override-file",
                str(override_path),
                "https://example.invalid/rc-vote-manifest.json",
                "https://example.invalid/KEYS",
            ],
            cwd=sandbox_dir,
            env=cli_env(sandbox_dir / "cli-manifest.json"),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("must change at least one build field", completed.stderr)

    def test_verify_rc_command_reports_generic_file_reproducibility_drift_in_full_mode(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture, completed = self._materialize_cached_generic_file_drift_family(
            sandbox_dir
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "generic-file reproducibility output does not match the staged artifact bytes",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual("failed", secondary_verification["verdict"])
        self.assertEqual(
            "byte-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )
        self.assertTrue(fixture.inspection_bundle_path.is_dir())
        self.assertEqual(
            {"comparison-metadata", "staged-artifact", "rebuilt-artifact"},
            {
                evidence["label"]
                for evidence in secondary_verification["reproducibility"]["evidence"]
            },
        )
