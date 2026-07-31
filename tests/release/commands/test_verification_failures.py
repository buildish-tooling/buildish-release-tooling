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
"""Verify-rc failure handling tests."""

from tests.release.commands.verification_support import (
    VerificationCommandsIntegrationTestBase,
    cleanup_sandbox,
    command_available,
    create_build_test_sandbox,
    json,
    run_cli,
)


class VerificationFailureCommandTest(VerificationCommandsIntegrationTestBase):
    """Verify-rc failure handling tests."""

    def test_verify_rc_command_fails_closed_when_secondary_artifact_digest_mismatches(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            mismatched_digest=True,
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
            "secondary artifact checksum does not match the signed manifest",
            completed.stderr,
        )

    def test_verify_rc_command_continues_when_secondary_entry_metadata_is_malformed(
        self,
    ) -> None:
        for case in ("missing-artifact-id", "missing-kind"):
            with self.subTest(case=case):
                sandbox_dir = create_build_test_sandbox()
                self.addCleanup(cleanup_sandbox, sandbox_dir)

                fixture = self._prepare_verification_fixture(
                    sandbox_dir,
                    secondary_kind="generic-file",
                    include_python_distribution=True,
                    malformed_secondary_missing_artifact_id=(
                        case == "missing-artifact-id"
                    ),
                    malformed_secondary_missing_kind=(case == "missing-kind"),
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
                        fixture.manifest_url,
                        fixture.keys_url,
                    ],
                    cwd=fixture.origin_dir,
                    env=self._fixture_cli_env(fixture),
                )

                self.assertEqual(1, completed.returncode)
                report_payload = json.loads(
                    fixture.report_json_path.read_text(encoding="utf-8")
                )
                self.assertEqual("failed", report_payload["verdict"])
                self.assertEqual(
                    2, len(report_payload["secondary_artifact_verifications"])
                )
                self.assertEqual(
                    "failed",
                    report_payload["secondary_artifact_verifications"][0]["verdict"],
                )
                self.assertEqual(
                    "verified",
                    report_payload["secondary_artifact_verifications"][1]["verdict"],
                )
                self.assertEqual(
                    "pypi-wheel",
                    report_payload["secondary_artifact_verifications"][1][
                        "artifact_id"
                    ],
                )
                if case == "missing-artifact-id":
                    self.assertIn(
                        "manifest field artifact_id must be a non-empty string",
                        completed.stderr,
                    )
                else:
                    self.assertIn(
                        "manifest field kind must be a non-empty string",
                        completed.stderr,
                    )

    def test_verify_rc_command_reports_progress_for_failed_run(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_generic_file_fixture(
            sandbox_dir,
            mismatched_digest=True,
        )
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
                "--log-path",
                str(fixture.log_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn("Verify RC\n=========", completed.stderr)
        self.assertIn("Secondary Artifact 1/1: bootstrap-zip", completed.stderr)
        self.assertIn("Outcome\n-------", completed.stderr)
        self.assertIn("✗ Verification failed with 1 issue(s)", completed.stderr)
        self.assertIn(
            f"  Report JSON: {fixture.work_dir / 'verify-rc-report-buildish-example-v1.2.3-rc0.json'}",
            completed.stderr,
        )
        self.assertIn(
            f"  Report Markdown: {fixture.work_dir / 'verify-rc-report-buildish-example-v1.2.3-rc0.md'}",
            completed.stderr,
        )
        self.assertIn(str(fixture.log_path), completed.stderr)
        self.assertIn(
            "secondary artifact checksum does not match the signed manifest",
            completed.stderr,
        )
        self.assertNotIn("progress:", completed.stderr)
        self.assertNotIn("+ git", completed.stderr)
        self.assertNotIn("+ gpg", completed.stderr)

    def test_verify_rc_command_reports_missing_source_and_secondary_files_without_crashing(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            missing_source_artifact=True,
            secondary_kind="generic-file",
            missing_secondary_artifact=True,
            include_npm_package=True,
            missing_npm_tarball=True,
            include_python_distribution=True,
        )
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("file URI could not be read:", completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        self.assertIn(
            "file URI could not be read:",
            "\n".join(report_payload["source_artifact_verification"]["issues"]),
        )
        secondary_by_id = {
            verification["artifact_id"]: verification
            for verification in report_payload["secondary_artifact_verifications"]
        }
        self.assertEqual("failed", secondary_by_id["bootstrap-zip"]["verdict"])
        self.assertEqual("failed", secondary_by_id["npm-package-main"]["verdict"])
        self.assertEqual("verified", secondary_by_id["pypi-wheel"]["verdict"])

    def test_verify_rc_command_reports_missing_sidecars_without_crashing(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            missing_source_checksum_sidecar=True,
            secondary_kind="generic-file",
            missing_secondary_checksum_sidecar=True,
            include_maven_repository=True,
            missing_maven_inventory=True,
            include_python_distribution=True,
            missing_python_checksum_sidecar=True,
            include_npm_package=True,
            missing_npm_checksum_sidecar=True,
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("file URI could not be read:", completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        self.assertTrue(
            any(
                failure["scope"] == "source-artifact"
                and failure["subject"] == "source artifact checksum sidecar"
                for failure in report_payload["failures"]
            )
        )
        secondary_by_id = {
            verification["artifact_id"]: verification
            for verification in report_payload["secondary_artifact_verifications"]
        }
        self.assertEqual("failed", secondary_by_id["bootstrap-zip"]["verdict"])
        self.assertEqual("failed", secondary_by_id["maven-staging-main"]["verdict"])
        self.assertEqual("failed", secondary_by_id["pypi-wheel"]["verdict"])
        self.assertEqual("failed", secondary_by_id["npm-package-main"]["verdict"])

    def test_verify_rc_command_handles_zero_length_artifacts_without_crashing(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            zero_length_source_artifact=True,
            secondary_kind="generic-file",
            zero_length_secondary_artifact=True,
            include_maven_repository=True,
            zero_length_maven_repository_file=True,
            include_python_distribution=True,
            zero_length_python_distribution=True,
            include_npm_package=True,
            zero_length_npm_tarball=True,
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "staged source artifact does not match the declared source_commit_sha",
            completed.stderr,
        )
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        self.assertEqual(
            "failed", report_payload["source_artifact_verification"]["verdict"]
        )
        secondary_by_id = {
            verification["artifact_id"]: verification
            for verification in report_payload["secondary_artifact_verifications"]
        }
        self.assertEqual("verified", secondary_by_id["bootstrap-zip"]["verdict"])
        self.assertEqual("verified", secondary_by_id["maven-staging-main"]["verdict"])
        self.assertEqual("verified", secondary_by_id["pypi-wheel"]["verdict"])
        self.assertEqual("verified", secondary_by_id["npm-package-main"]["verdict"])

    def test_verify_rc_command_omits_source_reproducibility_without_rebuilt_source_artifact(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            missing_source_artifact=True,
        )
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertIsNone(
            report_payload["source_artifact_verification"]["reproducibility"]
        )

    def test_verify_rc_command_progress_off_still_summarizes_missing_file_failures(
        self,
    ) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            missing_source_artifact=True,
            secondary_kind="generic-file",
            missing_secondary_artifact=True,
            include_python_distribution=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--test-target-mode",
                "--progress",
                "off",
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

        self.assertEqual(1, completed.returncode)
        self.assertIn("verify-rc failed with 2 issue(s):", completed.stderr)
        self.assertIn(str(fixture.report_md_path), completed.stderr)
        self.assertIn(str(fixture.log_path), completed.stderr)
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual(
            "verified", report_payload["secondary_artifact_verifications"][1]["verdict"]
        )

    def test_verify_rc_command_emits_low_level_output_to_stderr_in_verbose_mode(
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
                "--progress",
                "on",
                "--verbose",
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
        self.assertEqual("", completed.stdout)
        self.assertIn("Verify RC\n=========", completed.stderr)
        self.assertIn("+ git clone --quiet", completed.stderr)
        self.assertIn("+ gpg --batch --quiet --import", completed.stderr)
        self.assertIn("stdout | [GNUPG:] VALIDSIG ", completed.stderr)
        self.assertIn(
            f"  Report JSON: {fixture.work_dir / 'verify-rc-report-buildish-example-v1.2.3-rc0.json'}",
            completed.stderr,
        )
        self.assertIn(
            f"  Report Markdown: {fixture.work_dir / 'verify-rc-report-buildish-example-v1.2.3-rc0.md'}",
            completed.stderr,
        )
        self.assertIn("+ git -C ", fixture.log_path.read_text(encoding="utf-8"))

    def test_verify_rc_command_collects_independent_failures_before_exiting(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            mismatched_secondary_digest=True,
            include_python_distribution=True,
            missing_python_index_entry=True,
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
                "--log-path",
                str(fixture.log_path),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertEqual("", completed.stdout)
        self.assertIn(
            "secondary artifact checksum does not match the signed manifest",
            completed.stderr,
        )
        self.assertIn(
            "python-distribution file is not present in the declared simple index",
            completed.stderr,
        )
        self.assertTrue(fixture.report_json_path.is_file())
        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        self.assertEqual(2, len(report_payload["failures"]))
        failed_artifacts = [
            verification["artifact_id"]
            for verification in report_payload["secondary_artifact_verifications"]
            if verification["verdict"] == "failed"
        ]
        self.assertEqual(["bootstrap-zip", "pypi-wheel"], failed_artifacts)

    def test_verify_rc_command_collects_multiple_safe_failures_within_and_across_artifacts(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            drift_maven_repository=True,
            include_npm_package=True,
            drift_npm_tarball=True,
            drift_source_artifact=True,
        )
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

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "staged source artifact checksum does not match the signed manifest",
            completed.stderr,
        )
        self.assertIn(
            "source artifact .sha512 sidecar does not match the downloaded bytes",
            completed.stderr,
        )
        self.assertIn(
            "staged source artifact does not match the declared source_commit_sha",
            completed.stderr,
        )
        self.assertIn(
            "npm-package checksum does not match the signed manifest", completed.stderr
        )
        self.assertIn(
            "npm-package integrity does not match the downloaded tarball bytes",
            completed.stderr,
        )
        self.assertIn(
            "live maven repository checksum does not match the signed inventory",
            completed.stderr,
        )
        self.assertIn("BAD signature from", completed.stderr)

        report_payload = json.loads(
            fixture.report_json_path.read_text(encoding="utf-8")
        )
        self.assertEqual("failed", report_payload["verdict"])
        self.assertGreaterEqual(len(report_payload["failures"]), 8)
        source_reproducibility = report_payload["source_artifact_verification"][
            "reproducibility"
        ]
        self.assertEqual("failed", source_reproducibility["verdict"])
        self.assertEqual("byte-mismatch", source_reproducibility["failure_class"])
        self.assertEqual(False, source_reproducibility["matches_remote_bytes"])
        self.assertEqual(
            [
                "staged source checksum",
                "source artifact checksum sidecar",
                "source artifact signature",
                "source artifact reproducibility",
            ],
            [
                failure["subject"]
                for failure in report_payload["failures"]
                if failure["scope"] == "source-artifact"
            ],
        )
        secondary_by_id = {
            verification["artifact_id"]: verification
            for verification in report_payload["secondary_artifact_verifications"]
        }
        self.assertEqual(
            2,
            len(secondary_by_id["npm-package-main"]["issues"]),
        )
        self.assertGreaterEqual(
            len(secondary_by_id["maven-staging-main"]["issues"]),
            2,
        )
        report_markdown = fixture.report_md_path.read_text(encoding="utf-8")
        self.assertIn(
            "staged source artifact checksum does not match the signed manifest",
            report_markdown,
        )
        self.assertIn(
            "Source reproducibility failure class: `byte-mismatch`", report_markdown
        )
        self.assertIn(
            "npm-package integrity does not match the downloaded tarball bytes",
            report_markdown,
        )
        self.assertIn(
            "live maven repository checksum does not match the signed inventory",
            report_markdown,
        )

    def test_verify_rc_command_fails_closed_when_manifest_omits_rc_tag(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(sandbox_dir, include_rc_tag=False)
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
            "manifest field rc_tag must be a non-empty string", completed.stderr
        )

    def test_verify_rc_command_fails_closed_when_rc_tag_resolves_to_different_commit(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir, mismatched_source_commit_sha=True
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
            "manifest rc_tag does not resolve to the declared source_commit_sha",
            completed.stderr,
        )
