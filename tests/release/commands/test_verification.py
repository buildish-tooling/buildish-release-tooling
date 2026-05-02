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

"""Read-only verify-rc command integration tests."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
import io
import tarfile
import zipfile

from apache_buildish_release_tooling.release.artifact_registration.kinds.maven_repository import (
    build_maven_repository_registration,
)
from apache_buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    build_oci_image_registration,
)
from apache_buildish_release_tooling.release.artifact_registration.kinds.python_distribution import (
    build_python_distribution_registration,
)
from apache_buildish_release_tooling.release.gpg_signing import _effective_home, secret_key_fingerprint
from apache_buildish_release_tooling.release.source_artifact import create_from_git

from tests.release.commands.support import (
    Path,
    ReleaseCommandsIntegrationTestSupport,
    _read_simple_github_outputs,
    base64,
    cleanup_sandbox,
    cli_env,
    command_available,
    create_build_test_sandbox,
    create_fake_docker_launcher,
    git_create_annotated_tag,
    git_rev_parse,
    hashlib,
    init_git_origin_and_clone,
    json,
    os,
    run_quiet,
    run_cli,
)


@dataclass(frozen=True)
class VerificationFixture:
    """Reusable signed verification input set for one verify-rc integration test."""

    config_path: Path
    keys_url: str
    manifest_url: str
    manifest_output_path: Path
    inspection_bundle_path: Path
    origin_dir: Path
    log_path: Path
    report_json_path: Path
    report_md_path: Path
    source_commit_sha: str
    source_date_epoch: int
    work_dir: Path
    extra_env: dict[str, str]
    prepend_dirs: tuple[Path, ...]


def _write_zip_archive(
    archive_path: Path,
    *,
    member_name: str,
    payload: bytes,
    timestamp: tuple[int, int, int, int, int, int],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        zip_info = zipfile.ZipInfo(member_name, date_time=timestamp)
        zip_info.compress_type = zipfile.ZIP_DEFLATED
        zip_info.external_attr = 0o100644 << 16
        archive.writestr(zip_info, payload)


def _write_tgz_archive(
    archive_path: Path,
    *,
    member_name: str,
    payload: bytes,
    mtime: int,
    mode: int = 0o644,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="w:gz") as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        info.mtime = mtime
        info.mode = mode
        archive.addfile(info, io.BytesIO(payload))


class VerificationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """End-to-end coverage for the Phase 1a verify-rc command."""

    @staticmethod
    def _repro_shape(payload: dict[str, object] | None) -> dict[str, object] | None:
        if payload is None:
            return None
        canonical_recipe = payload.get("canonical_recipe")
        effective_execution = payload.get("effective_execution")
        override = payload.get("override")
        return {
            "keys": list(payload),
            "verdict": payload.get("verdict"),
            "profile_id": payload.get("profile_id"),
            "comparison_mode": payload.get("comparison_mode"),
            "canonical_recipe_keys": list(canonical_recipe) if isinstance(canonical_recipe, dict) else None,
            "effective_execution_keys": (
                list(effective_execution) if isinstance(effective_execution, dict) else None
            ),
            "override_keys": list(override) if isinstance(override, dict) else None,
            "override_applied": override.get("applied") if isinstance(override, dict) else None,
        }

    def _report_shape(self, payload: dict[str, object]) -> dict[str, object]:
        source_verification = payload["source_artifact_verification"]
        if not isinstance(source_verification, dict):
            self.fail("source_artifact_verification must be an object")
        secondary_verifications = payload["secondary_artifact_verifications"]
        if not isinstance(secondary_verifications, list):
            self.fail("secondary_artifact_verifications must be a list")
        failures = payload["failures"]
        if not isinstance(failures, list):
            self.fail("failures must be a list")
        inspection_bundle = payload.get("inspection_bundle")
        if inspection_bundle is not None and not isinstance(inspection_bundle, dict):
            self.fail("inspection_bundle must be an object when present")
        return {
            "top_level_keys": list(payload),
            "verdict": payload["verdict"],
            "failure_count": len(failures),
            "inspection_bundle_keys": list(inspection_bundle) if inspection_bundle is not None else None,
            "source_repro": self._repro_shape(source_verification.get("reproducibility")),
            "secondary_repro": {
                verification["artifact_id"]: self._repro_shape(verification.get("reproducibility"))
                for verification in secondary_verifications
                if isinstance(verification, dict)
            },
        }

    def test_verify_rc_command_reports_progress_for_successful_run(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        self.assertIn(f"SOURCE_DATE_EPOCH: {fixture.source_date_epoch}", completed.stderr)
        self.assertIn("✓ Verified manifest signature: ", completed.stderr)
        self.assertIn("✓ Verified rc_tag binding: v1.2.3-rc0 -> ", completed.stderr)
        self.assertIn("✓ Verified staged source SHA512: ", completed.stderr)
        self.assertIn("✓ Verified source artifact signature: ", completed.stderr)
        self.assertIn("• Enumerating live repository from ", completed.stderr)
        self.assertIn("✓ Verified maven repository inventory: ", completed.stderr)
        self.assertIn("Outcome\n-------", completed.stderr)
        self.assertIn("✓ Verified RC: buildish-example 1.2.3 (v1.2.3-rc0)", completed.stderr)
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
                "--allow-non-production-release-targets",
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
                "--allow-non-production-release-targets",
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
            json.loads(mixed_failure_fixture.report_json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual("failed", mixed_failure_shape["verdict"])
        self.assertEqual(8, mixed_failure_shape["failure_count"])
        self.assertEqual(
            ["relative_path_from_report", "bundle_schema_version", "manifest_relative_path"],
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

        full_repro_fixture = self._prepare_verification_fixture(
            sandbox_dir / "full-repro",
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
        )
        full_repro_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(full_repro_fixture.config_path),
                "--allow-non-production-release-targets",
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
        self.assertEqual(0, full_repro_completed.returncode, msg=full_repro_completed.stderr)
        full_repro_shape = self._report_shape(
            json.loads(full_repro_fixture.report_json_path.read_text(encoding="utf-8"))
        )
        self.assertEqual("verified", full_repro_shape["verdict"])
        self.assertEqual(
            ["relative_path_from_report", "bundle_schema_version", "manifest_relative_path"],
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

        override_fixture = self._prepare_verification_fixture(
            sandbox_dir / "override",
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
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
                "--allow-non-production-release-targets",
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
        self.assertEqual(0, override_completed.returncode, msg=override_completed.stderr)
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

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        self.assertIn("\x1b[32m✓ Verified RC: buildish-example 1.2.3 (v1.2.3-rc0)\x1b[0m", completed.stderr)
        self.assertNotIn("\x1b[", fixture.log_path.read_text(encoding="utf-8"))

    def test_verify_rc_command_verifies_manifest_source_and_rc_tag_binding(self) -> None:
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("verified", report_payload["verdict"])
        self.assertEqual(fixture.source_date_epoch, report_payload["source_date_epoch"])
        self.assertTrue(report_payload["manifest_verification"]["rc_tag_matches_source_commit_sha"])
        self.assertTrue(report_payload["source_artifact_verification"]["matches_source_commit_sha"])
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
        self.assertEqual(str(fixture.source_date_epoch), github_outputs["source_date_epoch"])

    def test_verify_rc_command_verifies_generic_secondary_artifact_with_openpgp(self) -> None:
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("verified", report_payload["verdict"])
        self.assertEqual(1, len(report_payload["secondary_artifact_verifications"]))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("generic-file-with-openpgp", secondary_verification["kind"])
        self.assertEqual("verified", secondary_verification["verdict"])
        self.assertEqual("sha512", secondary_verification["checksum"]["algorithm"])
        self.assertEqual(1, len(secondary_verification["signatures"]))
        self.assertIn("Secondary artifact verification", fixture.report_md_path.read_text(encoding="utf-8"))

    def test_verify_rc_command_verifies_generic_file_reproducibility_in_full_mode(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
        )
        completed = run_cli(
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
        self.assertIn("Verified rebuilt artifact matches staged bytes", completed.stderr)
        self.assertIn("Recipe source: canonical-profile", completed.stderr)
        self.assertIn("Build command: sh buildish-release-tooling/rebuild-bootstrap.sh", completed.stderr)
        self.assertIn("Build working directory: .", completed.stderr)
        self.assertIn(
            "Injected environment keys: BUILDISH_PROJECT_ROOT, BUILDISH_SOURCE_DATE_EPOCH, BUILDISH_WORK_DIR, SOURCE_DATE_EPOCH, TMPDIR",
            completed.stderr,
        )
        self.assertNotIn("Override fields:", completed.stderr)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
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
        self.assertEqual("full", report_payload["reproducibility_execution"]["requested_mode"])
        self.assertEqual("full", report_payload["reproducibility_execution"]["effective_mode"])
        self.assertTrue(report_payload["reproducibility_execution"]["build_checks_attempted"])
        self.assertEqual(
            os.path.relpath(fixture.inspection_bundle_path, start=fixture.report_json_path.parent),
            report_payload["inspection_bundle"]["relative_path_from_report"],
        )
        self.assertEqual("1", report_payload["inspection_bundle"]["bundle_schema_version"])
        self.assertEqual(
            "inspection-bundle.json",
            report_payload["inspection_bundle"]["manifest_relative_path"],
        )
        bundle_manifest = json.loads(
            (fixture.inspection_bundle_path / "inspection-bundle.json").read_text(encoding="utf-8")
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
        source_reproducibility = report_payload["source_artifact_verification"]["reproducibility"]
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
        self.assertEqual("source-artifact-from-git", source_reproducibility["profile_id"])
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
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])
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
            reproducibility["effective_execution"]["build"]["injected_environment_keys"],
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
        self.assertIn("Source rebuild command: `internal:create-from-git`", report_markdown)
        self.assertIn("Execution backend: `host-direct`", report_markdown)
        self.assertIn("Build command: `sh buildish-release-tooling/rebuild-bootstrap.sh`", report_markdown)
        self.assertIn("Build working directory: `.`", report_markdown)

    def test_verify_rc_command_uses_local_repro_override_file_for_generic_file(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        reproducibility = report_payload["secondary_artifact_verifications"][0]["reproducibility"]
        self.assertEqual(True, reproducibility["override"]["applied"])
        self.assertEqual(
            ["sh", "buildish-release-tooling/rebuild-bootstrap-local.sh"],
            reproducibility["override"]["build"]["command"],
        )

    def test_verify_rc_command_does_not_report_override_env_values(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
                "--allow-non-production-release-targets",
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
        reproducibility = json.loads(report_json)["secondary_artifact_verifications"][0]["reproducibility"]
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        reproducibility = report_payload["secondary_artifact_verifications"][0]["reproducibility"]
        self.assertEqual(False, reproducibility["override"]["applied"])

    def test_verify_rc_command_applies_one_override_to_two_artifacts_sharing_profile(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            include_second_generic_file_shared_profile=True,
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual(2, len(report_payload["secondary_artifact_verifications"]))
        for secondary_verification in report_payload["secondary_artifact_verifications"]:
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

    def test_verify_rc_command_rejects_repro_override_file_without_component_config(self) -> None:
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
                    "        command: [\"./buildish-release-tooling/rebuild-bootstrap-local.sh\"]",
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
        self.assertIn("--repro-override-file requires --component-config", completed.stderr)

    def test_verify_rc_command_rejects_repro_override_file_with_unknown_profile_id(self) -> None:
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
                "        command: [\"./buildish-release-tooling/rebuild-bootstrap.sh\"]",
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
                    "        command: [\"./buildish-release-tooling/rebuild-bootstrap-local.sh\"]",
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
                "        command: [\"./buildish-release-tooling/rebuild-bootstrap.sh\"]",
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

    def test_verify_rc_command_reports_generic_file_reproducibility_drift_in_full_mode(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
        )
        completed = run_cli(
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("generic-file reproducibility output does not match the staged artifact bytes", completed.stderr)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
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

    def test_inspect_repro_command_reports_saved_generic_file_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
        self.assertIn("Build command: sh buildish-release-tooling/rebuild-bootstrap.sh", inspect_completed.stderr)
        self.assertIn("Build working directory: .", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertIn(
            "Retained evidence: comparison-metadata, staged-artifact, rebuilt-artifact",
            inspect_completed.stderr,
        )
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)
        self.assertIn("Drift classification: text-content-drift", inspect_completed.stderr)
        self.assertIn("Size delta bytes: 0", inspect_completed.stderr)
        self.assertIn("Unified text diff", inspect_completed.stderr)
        self.assertIn("Outcome", inspect_completed.stderr)
        self.assertIn("Inspected 1 saved reproducibility failure(s)", inspect_completed.stderr)

    def test_inspect_repro_command_can_emit_machine_readable_json(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
                "--json",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        payload = json.loads(inspect_completed.stdout)
        self.assertEqual("inspect-repro", payload["report_type"])
        self.assertEqual("1", payload["schema_version"])
        self.assertEqual("1", payload["verify_rc_report_schema_version"])
        self.assertEqual("1", payload["bundle_schema_version"])
        self.assertEqual("buildish-example", payload["component_id"])
        self.assertEqual("v1.2.3-rc0", payload["rc_tag"])
        self.assertTrue(payload["build_checks_attempted"])
        self.assertFalse(payload["summary_only"])
        self.assertEqual([], payload["selected_artifact_ids"])
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
        self.assertEqual("bootstrap-zip", target["profile_id"])
        self.assertEqual("canonical-profile", target["recipe_source"])
        self.assertIn("comparison-metadata", target["evidence_labels"])

    def test_inspect_repro_command_can_filter_to_selected_artifact_ids(self) -> None:
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
                "--artifact-id",
                "bootstrap-zip",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Selected artifact ids: bootstrap-zip", inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 1", inspect_completed.stderr)
        self.assertIn("Failure target: bootstrap-zip [generic-file] byte-mismatch", inspect_completed.stderr)
        self.assertNotIn("Source Artifact 1/1", inspect_completed.stderr)
        self.assertIn("Artifact 1/1: bootstrap-zip", inspect_completed.stderr)

    def test_inspect_repro_command_summary_only_skips_per_artifact_analysis(self) -> None:
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
                "--summary-only",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Reproducibility failures: 2", inspect_completed.stderr)
        self.assertIn("Failure target: source-artifact [source-artifact] byte-mismatch", inspect_completed.stderr)
        self.assertIn("Failure target: bootstrap-zip [generic-file] byte-mismatch", inspect_completed.stderr)
        self.assertIn("Summary-only mode requested; skipping per-artifact inspection", inspect_completed.stderr)
        self.assertIn("Summarized 2 saved reproducibility failure(s)", inspect_completed.stderr)
        self.assertNotIn("Unified text diff", inspect_completed.stderr)
        self.assertNotIn("Artifact 1/2:", inspect_completed.stderr)

    def test_inspect_repro_command_summary_only_lists_all_targets_for_mixed_failures(self) -> None:
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
            include_oci_image=True,
            include_oci_image_reproducibility=True,
            drift_oci_image_reproducibility_platform=True,
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
                "--summary-only",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
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
        self.assertIn("Failure target: source-artifact [source-artifact] byte-mismatch", inspect_completed.stderr)
        self.assertIn("Failure target: bootstrap-zip [generic-file] byte-mismatch", inspect_completed.stderr)
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

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
                "--artifact-id",
                "does-not-exist",
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, inspect_completed.returncode)
        self.assertIn(
            "requested inspect-repro artifact ids did not match any retained reproducibility failures: does-not-exist; available: bootstrap-zip",
            inspect_completed.stderr,
        )

    def test_inspect_repro_command_reports_shallow_archive_drift_for_generic_file(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
            archive_generic_file_reproducibility=True,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: zip", inspect_completed.stderr)
        self.assertIn("Archive drift classification: entry-content-drift", inspect_completed.stderr)
        self.assertIn("Archive member-content mismatches", inspect_completed.stderr)
        self.assertIn(
            "Likely cause: one or more top-level archive member payloads changed",
            inspect_completed.stderr,
        )
        self.assertIn("bootstrap.txt", inspect_completed.stderr)

    def test_verify_rc_persists_shallow_archive_analysis_for_archive_backed_generic_file(self) -> None:
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        reproducibility = report_payload["secondary_artifact_verifications"][0]["reproducibility"]
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
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(reproducibility["archive_analysis"], metadata_payload["archive_analysis"])

    def test_inspect_repro_command_reports_saved_source_artifact_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            drift_source_artifact=True,
        )
        verify_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--progress",
                "on",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        source_reproducibility = report_payload["source_artifact_verification"]["reproducibility"]
        self.assertEqual(
            {"comparison-metadata", "staged-artifact", "rebuilt-artifact"},
            {evidence["label"] for evidence in source_reproducibility["evidence"]},
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
        self.assertIn("Failure kinds: source-artifact=1", inspect_completed.stderr)
        self.assertIn("Source Artifact 1/1", inspect_completed.stderr)
        self.assertIn("Kind: source-artifact", inspect_completed.stderr)
        self.assertIn("Recipe source: verifier-internal", inspect_completed.stderr)
        self.assertIn("Build command: internal:create-from-git", inspect_completed.stderr)
        self.assertIn("Failure class: byte-mismatch", inspect_completed.stderr)
        self.assertIn(
            "Retained evidence: comparison-metadata, staged-artifact, rebuilt-artifact",
            inspect_completed.stderr,
        )
        self.assertIn("Retained staged and rebuilt source-artifact copies differ", inspect_completed.stderr)
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: tar", inspect_completed.stderr)
        self.assertIn(
            "Archive drift appears limited to the outer container or compression bytes",
            inspect_completed.stderr,
        )
        self.assertIn("Archive drift classification: outer-container-drift", inspect_completed.stderr)
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
        self.assertIn("Inspected 1 saved reproducibility failure(s)", inspect_completed.stderr)

    def test_inspect_repro_command_tolerates_missing_source_effective_execution(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            drift_source_artifact=True,
        )
        verify_completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--progress",
                "on",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        del report_payload["source_artifact_verification"]["reproducibility"]["effective_execution"]
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
        self.assertIn("Retained staged and rebuilt source-artifact copies differ", inspect_completed.stderr)

    def test_inspect_repro_command_tolerates_missing_canonical_recipe(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        del report_payload["secondary_artifact_verifications"][0]["reproducibility"]["canonical_recipe"]
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

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
        self.assertIn("Build command: sh buildish-release-tooling/rebuild-bootstrap.sh", inspect_completed.stderr)
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)

    def test_inspect_repro_command_tolerates_legacy_bundle_contract_fields(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        del report_payload["inspection_bundle"]["bundle_schema_version"]
        del report_payload["inspection_bundle"]["manifest_relative_path"]
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

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
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)

    def test_inspect_repro_command_rejects_unsupported_report_and_bundle_schema_versions(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        report_payload["schema_version"] = "99"
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

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
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
        bundle_manifest_path = fixture.inspection_bundle_path / "inspection-bundle.json"
        bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
        bundle_manifest["schema_version"] = "99"
        bundle_manifest_path.write_text(json.dumps(bundle_manifest, indent=2) + "\n", encoding="utf-8")

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

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, verify_completed.returncode)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        del report_payload["secondary_artifact_verifications"][0]["reproducibility"]["effective_execution"]
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

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
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)

    def test_inspect_repro_command_tolerates_override_without_build_payload(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        report_payload["secondary_artifact_verifications"][0]["reproducibility"]["override"] = {
            "applied": True
        }
        fixture.report_json_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

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
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)

    def test_inspect_repro_command_reports_override_metadata_for_failed_generic_file_drift(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            include_generic_file_reproducibility=True,
            drift_generic_file_reproducibility=True,
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

    def test_verify_rc_command_fails_closed_when_secondary_artifact_digest_mismatches(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            mismatched_secondary_digest=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("secondary artifact checksum does not match the signed manifest", completed.stderr)

    def test_verify_rc_command_continues_when_secondary_entry_metadata_is_malformed(self) -> None:
        for case in ("missing-artifact-id", "missing-kind"):
            with self.subTest(case=case):
                sandbox_dir = create_build_test_sandbox()
                self.addCleanup(cleanup_sandbox, sandbox_dir)

                fixture = self._prepare_verification_fixture(
                    sandbox_dir,
                    secondary_kind="generic-file",
                    include_python_distribution=True,
                    malformed_secondary_missing_artifact_id=(case == "missing-artifact-id"),
                    malformed_secondary_missing_kind=(case == "missing-kind"),
                )
                completed = run_cli(
                    [
                        "verify-rc",
                        "--component-config",
                        str(fixture.config_path),
                        "--allow-non-production-release-targets",
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
                report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
                self.assertEqual("failed", report_payload["verdict"])
                self.assertEqual(2, len(report_payload["secondary_artifact_verifications"]))
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
                    report_payload["secondary_artifact_verifications"][1]["artifact_id"],
                )
                if case == "missing-artifact-id":
                    self.assertIn("manifest field artifact_id must be a non-empty string", completed.stderr)
                else:
                    self.assertIn("manifest field kind must be a non-empty string", completed.stderr)

    def test_verify_rc_command_reports_progress_for_failed_run(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            secondary_kind="generic-file",
            mismatched_secondary_digest=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        self.assertIn("secondary artifact checksum does not match the signed manifest", completed.stderr)
        self.assertNotIn("progress:", completed.stderr)
        self.assertNotIn("+ git", completed.stderr)
        self.assertNotIn("+ gpg", completed.stderr)

    def test_verify_rc_command_reports_missing_source_and_secondary_files_without_crashing(self) -> None:
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
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

    def test_verify_rc_command_omits_source_reproducibility_without_rebuilt_source_artifact(self) -> None:
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertIsNone(report_payload["source_artifact_verification"]["reproducibility"])

    def test_verify_rc_command_progress_off_still_summarizes_missing_file_failures(self) -> None:
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
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("verified", report_payload["secondary_artifact_verifications"][1]["verdict"])

    def test_verify_rc_command_emits_low_level_output_to_stderr_in_verbose_mode(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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

    def test_verify_rc_command_collects_independent_failures_before_exiting(self) -> None:
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
                "--allow-non-production-release-targets",
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
        self.assertIn("secondary artifact checksum does not match the signed manifest", completed.stderr)
        self.assertIn("python-distribution file is not present in the declared simple index", completed.stderr)
        self.assertTrue(fixture.report_json_path.is_file())
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("failed", report_payload["verdict"])
        self.assertEqual(2, len(report_payload["failures"]))
        failed_artifacts = [
            verification["artifact_id"]
            for verification in report_payload["secondary_artifact_verifications"]
            if verification["verdict"] == "failed"
        ]
        self.assertEqual(["bootstrap-zip", "pypi-wheel"], failed_artifacts)

    def test_verify_rc_command_collects_multiple_safe_failures_within_and_across_artifacts(self) -> None:
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
                "--allow-non-production-release-targets",
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
        self.assertIn("staged source artifact checksum does not match the signed manifest", completed.stderr)
        self.assertIn("source artifact .sha512 sidecar does not match the downloaded bytes", completed.stderr)
        self.assertIn("staged source artifact does not match the declared source_commit_sha", completed.stderr)
        self.assertIn("npm-package checksum does not match the signed manifest", completed.stderr)
        self.assertIn("npm-package integrity does not match the downloaded tarball bytes", completed.stderr)
        self.assertIn("live maven repository checksum does not match the signed inventory", completed.stderr)
        self.assertIn("BAD signature from", completed.stderr)

        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("failed", report_payload["verdict"])
        self.assertGreaterEqual(len(report_payload["failures"]), 8)
        source_reproducibility = report_payload["source_artifact_verification"]["reproducibility"]
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
        self.assertIn("staged source artifact checksum does not match the signed manifest", report_markdown)
        self.assertIn("Source reproducibility failure class: `byte-mismatch`", report_markdown)
        self.assertIn("npm-package integrity does not match the downloaded tarball bytes", report_markdown)
        self.assertIn("live maven repository checksum does not match the signed inventory", report_markdown)

    def test_verify_rc_command_verifies_maven_repository_secondary_artifact(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("maven-repository", secondary_verification["kind"])
        self.assertTrue(secondary_verification["live_repository"]["matches_signed_inventory"])
        self.assertEqual(1, len(secondary_verification["live_repository"]["signature_verifications"]))

    def test_verify_rc_command_verifies_python_distribution_secondary_artifact(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("python-distribution", secondary_verification["kind"])
        self.assertTrue(secondary_verification["index_resolution"]["sha256_matches_index"])
        self.assertEqual("simple-json", secondary_verification["index_resolution"]["found_via"])

    def test_verify_rc_command_fails_closed_when_python_distribution_is_missing_from_index(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
            missing_python_index_entry=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("python-distribution file is not present in the declared simple index", completed.stderr)

    def test_verify_rc_command_verifies_python_distribution_reproducibility_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
            include_python_distribution_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual("pypi-wheel", secondary_verification["reproducibility"]["profile_id"])
        self.assertEqual(
            ["dist/example-1.2.3-py3-none-any.whl"],
            secondary_verification["reproducibility"]["effective_execution"]["build"]["output_paths"],
        )

    def test_verify_rc_command_reports_python_distribution_reproducibility_drift_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
            include_python_distribution_reproducibility=True,
            drift_python_distribution_reproducibility=True,
            archive_python_distribution_reproducibility=True,
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

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "python-distribution reproducibility output does not match the staged artifact bytes",
            completed.stderr,
        )
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "byte-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_python_distribution_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_python_distribution=True,
            include_python_distribution_reproducibility=True,
            drift_python_distribution_reproducibility=True,
            archive_python_distribution_reproducibility=True,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: pypi-wheel", inspect_completed.stderr)
        self.assertIn("Project: example", inspect_completed.stderr)
        self.assertIn("Version: 1.2.3", inspect_completed.stderr)
        self.assertIn("Distribution type: wheel", inspect_completed.stderr)
        self.assertIn("Simple index:", inspect_completed.stderr)
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)
        self.assertIn("Drift classification: size-and-binary-drift", inspect_completed.stderr)
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: zip", inspect_completed.stderr)
        self.assertIn("Archive drift classification: mixed-entry-drift", inspect_completed.stderr)
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

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("npm-package", secondary_verification["kind"])
        self.assertTrue(secondary_verification["registry_resolution"]["tarball_url_matches_manifest"])
        self.assertTrue(secondary_verification["registry_resolution"]["integrity_matches_manifest"])

    def test_verify_rc_command_fails_closed_when_npm_registry_integrity_drifts(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
            drift_npm_registry_integrity=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("npm-package registry integrity does not match the signed manifest", completed.stderr)

    def test_verify_rc_command_verifies_npm_package_reproducibility_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
            include_npm_package_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "npm-package-main",
            secondary_verification["reproducibility"]["profile_id"],
        )
        self.assertEqual(
            ["dist/buildish-example-1.2.3.tgz"],
            secondary_verification["reproducibility"]["effective_execution"]["build"]["output_paths"],
        )

    def test_verify_rc_command_reports_npm_package_reproducibility_drift_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
            include_npm_package_reproducibility=True,
            drift_npm_package_reproducibility=True,
            archive_npm_package_reproducibility=True,
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

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "npm-package reproducibility output does not match the staged artifact bytes",
            completed.stderr,
        )
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "byte-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_npm_package_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_npm_package=True,
            include_npm_package_reproducibility=True,
            drift_npm_package_reproducibility=True,
            archive_npm_package_reproducibility=True,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: npm-package-main", inspect_completed.stderr)
        self.assertIn("Package: @apache/buildish-example", inspect_completed.stderr)
        self.assertIn("Version: 1.2.3", inspect_completed.stderr)
        self.assertIn("Declared integrity: sha512-", inspect_completed.stderr)
        self.assertIn("Registry URL:", inspect_completed.stderr)
        self.assertIn("Retained staged and rebuilt artifact copies differ", inspect_completed.stderr)
        self.assertIn("Drift classification: size-and-binary-drift", inspect_completed.stderr)
        self.assertIn("Shallow archive comparison", inspect_completed.stderr)
        self.assertIn("Archive format: tar", inspect_completed.stderr)
        self.assertIn("Archive drift classification: mixed-entry-drift", inspect_completed.stderr)
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

    def test_verify_rc_command_fails_closed_when_maven_repository_drifts_from_inventory(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            drift_maven_repository=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("live maven repository checksum does not match the signed inventory", completed.stderr)

    def test_verify_rc_command_verifies_maven_repository_reproducibility_in_full_mode(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            include_maven_repository_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual("maven-staging", secondary_verification["reproducibility"]["profile_id"])
        metadata_reference = next(
            reference
            for reference in secondary_verification["reproducibility"]["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(encoding="utf-8")
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
            secondary_verification["reproducibility"]["effective_execution"]["build"]["output_paths"],
        )

    def test_verify_rc_command_verifies_maven_repository_reproducibility_with_unrelated_local_repo_files(
        self,
    ) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            include_maven_repository_reproducibility=True,
            include_unrelated_local_maven_repository_files=True,
            omit_maven_repository_sidecar_path_rules=True,
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
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])

    def test_verify_rc_command_reports_maven_repository_reproducibility_drift_in_full_mode(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_maven_repository=True,
            include_maven_repository_reproducibility=True,
            drift_maven_repository_reproducibility=True,
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

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "maven-repository reproducibility exact-bytes comparison failed",
            completed.stderr,
        )
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
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
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(encoding="utf-8")
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

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: maven-staging-main", inspect_completed.stderr)
        self.assertIn("Verified comparable paths: 1", inspect_completed.stderr)
        self.assertIn("Failed comparable paths: 1", inspect_completed.stderr)
        self.assertIn("Failed by mode: exact-bytes=1", inspect_completed.stderr)
        self.assertIn("Failed by category: metadata-text=1", inspect_completed.stderr)
        self.assertIn("Failed by repository directory: org/example/app/1.0.0=1", inspect_completed.stderr)
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
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("manifest field rc_tag must be a non-empty string", completed.stderr)

    def test_verify_rc_command_fails_closed_when_rc_tag_resolves_to_different_commit(self) -> None:
        if not command_available("gpg"):
            self.skipTest("gpg is required for verify-rc integration coverage")
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(sandbox_dir, mismatched_source_commit_sha=True)
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("manifest rc_tag does not resolve to the declared source_commit_sha", completed.stderr)

    def test_verify_rc_command_verifies_oci_image_secondary_artifact(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("oci-image", secondary_verification["kind"])
        self.assertTrue(secondary_verification["inspection"]["digest_matches_manifest"])
        self.assertTrue(secondary_verification["inspection"]["platform_digests_match"])

    def test_verify_rc_command_fails_closed_when_oci_image_platform_digest_drifts(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            drift_oci_image=True,
        )
        completed = run_cli(
            [
                "verify-rc",
                "--component-config",
                str(fixture.config_path),
                "--allow-non-production-release-targets",
                "--work-dir",
                str(fixture.work_dir),
                fixture.manifest_url,
                fixture.keys_url,
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("oci-image platform digests do not match the signed manifest", completed.stderr)

    def test_verify_rc_command_verifies_oci_image_reproducibility_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            include_oci_image_reproducibility=True,
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
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("verified", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual("oci-main-image", secondary_verification["reproducibility"]["profile_id"])
        self.assertEqual(
            [".buildish-out/oci-image-rebuilt.marker"],
            secondary_verification["reproducibility"]["effective_execution"]["build"]["output_paths"],
        )
        metadata_reference = next(
            reference
            for reference in secondary_verification["reproducibility"]["evidence"]
            if reference["label"] == "comparison-metadata"
        )
        metadata_payload = json.loads(
            (fixture.inspection_bundle_path / metadata_reference["path"]).read_text(encoding="utf-8")
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

    def test_verify_rc_command_reports_oci_image_reproducibility_drift_in_full_mode(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            include_oci_image_reproducibility=True,
            drift_oci_image_reproducibility=True,
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

        self.assertEqual(1, completed.returncode)
        self.assertIn(
            "oci-image reproducibility digest does not match the signed manifest",
            completed.stderr,
        )
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        secondary_verification = report_payload["secondary_artifact_verifications"][0]
        self.assertEqual("failed", secondary_verification["reproducibility"]["verdict"])
        self.assertEqual(
            "digest-mismatch",
            secondary_verification["reproducibility"]["failure_class"],
        )

    def test_inspect_repro_command_reports_saved_oci_image_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            include_oci_image_reproducibility=True,
            drift_oci_image_reproducibility=True,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Artifact 1/1: ghcr-main-image", inspect_completed.stderr)
        self.assertIn("Top-level image digest differs from the signed manifest", inspect_completed.stderr)
        self.assertIn("Platform digests matched the signed manifest", inspect_completed.stderr)
        self.assertIn("Drift classification: metadata-only", inspect_completed.stderr)
        self.assertIn("Likely OCI index/config metadata drift", inspect_completed.stderr)
        self.assertIn("Rebuilt digest", inspect_completed.stderr)

    def test_inspect_repro_command_reports_saved_oci_image_platform_drift(self) -> None:
        sandbox_dir = create_build_test_sandbox()
        self.addCleanup(cleanup_sandbox, sandbox_dir)

        fixture = self._prepare_verification_fixture(
            sandbox_dir,
            include_oci_image=True,
            include_oci_image_reproducibility=True,
            drift_oci_image_reproducibility_platform=True,
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
                str(fixture.report_json_path),
            ],
            cwd=fixture.origin_dir,
            env=self._fixture_cli_env(fixture),
        )

        self.assertEqual(0, inspect_completed.returncode, msg=inspect_completed.stderr)
        self.assertIn("Platform digests differ from the signed manifest", inspect_completed.stderr)
        self.assertIn("Changed platform count: 1", inspect_completed.stderr)
        self.assertIn("Platform drift summary: changed=1 missing=0 unexpected=0", inspect_completed.stderr)
        self.assertIn("Drift classification: top-level-and-platform-payload", inspect_completed.stderr)
        self.assertIn("Changed platform: linux/arm64", inspect_completed.stderr)
        self.assertIn("Platform payload drift is present", inspect_completed.stderr)
        self.assertIn(
            "OCI hint: compare the rebuilt platform images above before reviewing top-level manifest/index metadata",
            inspect_completed.stderr,
        )

    def _prepare_verification_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_rc_tag: bool = True,
        mismatched_source_commit_sha: bool = False,
        drift_source_artifact: bool = False,
        missing_source_artifact: bool = False,
        secondary_kind: str | None = None,
        mismatched_secondary_digest: bool = False,
        missing_secondary_artifact: bool = False,
        malformed_secondary_missing_artifact_id: bool = False,
        malformed_secondary_missing_kind: bool = False,
        include_maven_repository: bool = False,
        drift_maven_repository: bool = False,
        include_maven_repository_reproducibility: bool = False,
        drift_maven_repository_reproducibility: bool = False,
        include_unrelated_local_maven_repository_files: bool = False,
        omit_maven_repository_sidecar_path_rules: bool = False,
        include_python_distribution: bool = False,
        missing_python_index_entry: bool = False,
        include_python_distribution_reproducibility: bool = False,
        drift_python_distribution_reproducibility: bool = False,
        archive_python_distribution_reproducibility: bool = False,
        include_npm_package: bool = False,
        drift_npm_registry_integrity: bool = False,
        drift_npm_tarball: bool = False,
        missing_npm_tarball: bool = False,
        include_npm_package_reproducibility: bool = False,
        drift_npm_package_reproducibility: bool = False,
        archive_npm_package_reproducibility: bool = False,
        include_oci_image: bool = False,
        drift_oci_image: bool = False,
        include_oci_image_reproducibility: bool = False,
        drift_oci_image_reproducibility: bool = False,
        drift_oci_image_reproducibility_platform: bool = False,
        include_generic_file_reproducibility: bool = False,
        drift_generic_file_reproducibility: bool = False,
        archive_generic_file_reproducibility: bool = False,
        include_second_generic_file_shared_profile: bool = False,
        extra_verify_rc_profile_lines: tuple[str, ...] = (),
    ) -> VerificationFixture:
        origin_dir, _clone_dir = init_git_origin_and_clone(sandbox_dir)
        component_id = "buildish-example"
        version = "1.2.3"
        rc_tag = "v1.2.3-rc0"
        stage_dir = (
            sandbox_dir
            / "dist"
            / "dev"
            / "incubator"
            / "buildish"
            / component_id
            / f"{version}-rc0"
        )
        release_dir = sandbox_dir / "dist" / "release" / "incubator" / "buildish"
        release_dir.mkdir(parents=True, exist_ok=True)
        keys_path = release_dir / "KEYS"
        config_path = sandbox_dir / "component.yaml"
        work_dir = sandbox_dir / "verify-work"
        log_path = sandbox_dir / "verify.log"
        report_json_path = sandbox_dir / "verify-report.json"
        report_md_path = sandbox_dir / "verify-report.md"
        inspection_bundle_path = sandbox_dir / "verify-inspection-bundle"
        manifest_output_path = sandbox_dir / "verify-rc-command.json"
        gpg_home = sandbox_dir / "gpg-home"
        extra_env: dict[str, str] = {}
        prepend_dirs: tuple[Path, ...] = ()
        gpg_home.mkdir(parents=True, exist_ok=True)
        gpg_home.chmod(0o700)
        effective_gpg_home = _effective_home(gpg_home)
        verify_rc_line_list: list[str] = []
        if include_generic_file_reproducibility:
            verify_rc_line_list.extend(
                [
                    "    bootstrap-zip:",
                    f"      kind: {secondary_kind}",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-bootstrap.sh",
                    "        output_globs:",
                    "          - dist/buildish-example-bootstrap.zip",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if include_python_distribution_reproducibility:
            verify_rc_line_list.extend(
                [
                    "    pypi-wheel:",
                    "      kind: python-distribution",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-wheel.sh",
                    "        output_globs:",
                    "          - dist/example-1.2.3-py3-none-any.whl",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if include_npm_package_reproducibility:
            verify_rc_line_list.extend(
                [
                    "    npm-package-main:",
                    "      kind: npm-package",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-npm-package.sh",
                    "        output_globs:",
                    "          - dist/buildish-example-1.2.3.tgz",
                    "      comparison:",
                    "        mode: exact-bytes",
                ]
            )
        if include_maven_repository_reproducibility:
            verify_rc_line_list.extend(
                [
                    "    maven-staging:",
                    "      kind: maven-repository",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-maven-staging.sh",
                    "        output_globs:",
                    "          - .buildish-out/m2repo/**",
                    "      comparison:",
                    "        mode: repository-tree",
                    "        repository_dir: .buildish-out/m2repo",
                    "        require_signatures: true",
                    "        path_rules:",
                    "          - pattern: .+\\.(jar|war|zip)$",
                    "            mode: content-only",
                    "          - pattern: .+\\.(pom|module)$",
                    "            mode: exact-bytes",
                    "          - pattern: ^.*/maven-metadata\\.xml(\\..+)?$",
                    "            mode: remote-only",
                ]
            )
            if not omit_maven_repository_sidecar_path_rules:
                verify_rc_line_list.extend(
                    [
                        "          - pattern: .+\\.(asc|sha512|md5)$",
                        "            mode: remote-only",
                    ]
                )
        if include_oci_image_reproducibility:
            verify_rc_line_list.extend(
                [
                    "    oci-main-image:",
                    "      kind: oci-image",
                    "      build:",
                    "        command:",
                    "          - sh",
                    "          - buildish-release-tooling/rebuild-oci-image.sh",
                    "        output_globs:",
                    "          - .buildish-out/oci-image-rebuilt.marker",
                    "      comparison:",
                    "        mode: platform-digest",
                    "        image_ref: ghcr.io/apache/buildish-example:rebuild-local",
                ]
            )
        if extra_verify_rc_profile_lines:
            verify_rc_line_list.extend(extra_verify_rc_profile_lines)
        verify_rc_lines = (
            ("verify_rc:", "  profiles:", *verify_rc_line_list)
            if verify_rc_line_list
            else ()
        )

        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=(stage_dir.parent).as_uri(),
            release_base_url=(release_dir / component_id).as_uri(),
            verify_rc_lines=verify_rc_lines,
        )

        if include_generic_file_reproducibility:
            rebuild_script = origin_dir / "buildish-release-tooling" / "rebuild-bootstrap.sh"
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if archive_generic_file_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from pathlib import Path",
                            "import zipfile",
                            "archive_path = Path('dist/buildish-example-bootstrap.zip')",
                            "payload = b'bootstrap zip bytes\\n'",
                            (
                                "payload = b'bootstrap zip drift\\n'"
                                if drift_generic_file_reproducibility
                                else "payload = payload"
                            ),
                            "with zipfile.ZipFile(archive_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                            "    info = zipfile.ZipInfo('bootstrap.txt', date_time=(2026, 4, 30, 12, 0, 1))",
                            "    info.compress_type = zipfile.ZIP_DEFLATED",
                            "    info.external_attr = 0o100644 << 16",
                            "    archive.writestr(info, payload)",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'bootstrap zip bytes\\n' > dist/buildish-example-bootstrap.zip"
                                if not drift_generic_file_reproducibility
                                else "printf 'bootstrap zip drift\\n' > dist/buildish-example-bootstrap.zip"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            local_override_script = origin_dir / "buildish-release-tooling" / "rebuild-bootstrap-local.sh"
            local_override_script.write_text(rebuild_script.read_text(encoding="utf-8"), encoding="utf-8")
            local_override_script.chmod(0o755)
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "add",
                    "buildish-release-tooling/rebuild-bootstrap.sh",
                    "buildish-release-tooling/rebuild-bootstrap-local.sh",
                ],
                check=True,
            )
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "add bootstrap rebuild script"],
                check=True,
            )
        if include_python_distribution_reproducibility:
            rebuild_script = origin_dir / "buildish-release-tooling" / "rebuild-wheel.sh"
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if archive_python_distribution_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from pathlib import Path",
                            "import zipfile",
                            "archive_path = Path('dist/example-1.2.3-py3-none-any.whl')",
                            "payload = b'wheel payload\\n'",
                            (
                                "payload = b'wheel payload drift\\n'"
                                if drift_python_distribution_reproducibility
                                else "payload = payload"
                            ),
                            "with zipfile.ZipFile(archive_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                            "    info = zipfile.ZipInfo('example/__init__.py', date_time=(2026, 4, 30, 12, 0, 1))",
                            "    info.compress_type = zipfile.ZIP_DEFLATED",
                            "    info.external_attr = 0o100644 << 16",
                            "    archive.writestr(info, payload)",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'wheel payload\\n' > dist/example-1.2.3-py3-none-any.whl"
                                if not drift_python_distribution_reproducibility
                                else "printf 'wheel payload drift\\n' > dist/example-1.2.3-py3-none-any.whl"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            run_quiet(
                ["git", "-C", str(origin_dir), "add", "buildish-release-tooling/rebuild-wheel.sh"],
                check=True,
            )
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "add wheel rebuild script"],
                check=True,
            )
        if include_npm_package_reproducibility:
            rebuild_script = origin_dir / "buildish-release-tooling" / "rebuild-npm-package.sh"
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            if archive_npm_package_reproducibility:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            "python - <<'PY'",
                            "from io import BytesIO",
                            "from pathlib import Path",
                            "import tarfile",
                            "archive_path = Path('dist/buildish-example-1.2.3.tgz')",
                            "payload = b'npm package payload\\n'",
                            (
                                "payload = b'npm package payload drift\\n'"
                                if drift_npm_package_reproducibility
                                else "payload = payload"
                            ),
                            "with tarfile.open(archive_path, mode='w:gz') as archive:",
                            "    info = tarfile.TarInfo('package/package.json')",
                            "    info.size = len(payload)",
                            "    info.mtime = 1714435201",
                            "    info.mode = 0o644",
                            "    archive.addfile(info, BytesIO(payload))",
                            "PY",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                rebuild_script.write_text(
                    "\n".join(
                        [
                            "#!/usr/bin/env sh",
                            "set -eu",
                            "mkdir -p dist",
                            (
                                "printf 'npm package payload\\n' > dist/buildish-example-1.2.3.tgz"
                                if not drift_npm_package_reproducibility
                                else "printf 'npm package payload drift\\n' > dist/buildish-example-1.2.3.tgz"
                            ),
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            rebuild_script.chmod(0o755)
            run_quiet(
                ["git", "-C", str(origin_dir), "add", "buildish-release-tooling/rebuild-npm-package.sh"],
                check=True,
            )
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "add npm rebuild script"],
                check=True,
            )
        if include_maven_repository_reproducibility:
            rebuild_script = origin_dir / "buildish-release-tooling" / "rebuild-maven-staging.sh"
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            rebuild_script.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env sh",
                        "set -eu",
                        "repo_root=.buildish-out/m2repo/org/example/app/1.0.0",
                        "mkdir -p \"$repo_root\"",
                        "python - <<'PY'",
                        "from pathlib import Path",
                        "import zipfile",
                        "repo_root = Path('.buildish-out/m2repo/org/example/app/1.0.0')",
                        "jar_path = repo_root / 'app-1.0.0.jar'",
                        "with zipfile.ZipFile(jar_path, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:",
                        "    info = zipfile.ZipInfo('app.txt', date_time=(2026, 4, 30, 12, 0, 2))",
                        "    info.compress_type = zipfile.ZIP_DEFLATED",
                        "    archive.writestr(info, b'jar payload\\n')",
                        "PY",
                        (
                            "printf '<project>drift</project>\\n' > \"$repo_root/app-1.0.0.pom\""
                            if drift_maven_repository_reproducibility
                            else "printf '<project>stable</project>\\n' > \"$repo_root/app-1.0.0.pom\""
                        ),
                        (
                            "\n".join(
                                [
                                    "extra_root=.buildish-out/m2repo/com/example/dependency/2.0.0",
                                    "mkdir -p \"$extra_root\"",
                                    "printf 'dependency bytes\\n' > \"$extra_root/dependency-2.0.0.jar\"",
                                ]
                            )
                            if include_unrelated_local_maven_repository_files
                            else ""
                        ),
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rebuild_script.chmod(0o755)
            run_quiet(
                ["git", "-C", str(origin_dir), "add", "buildish-release-tooling/rebuild-maven-staging.sh"],
                check=True,
            )
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "add maven rebuild script"],
                check=True,
            )
        if include_oci_image_reproducibility:
            rebuild_script = origin_dir / "buildish-release-tooling" / "rebuild-oci-image.sh"
            rebuild_script.parent.mkdir(parents=True, exist_ok=True)
            rebuilt_top_level_digest = "sha256:" + (
                ("e5" if drift_oci_image_reproducibility or drift_oci_image_reproducibility_platform else "d4")
                * 32
            )
            rebuilt_amd64_digest = "sha256:" + ("a1" * 32)
            rebuilt_arm64_digest = "sha256:" + (
                ("c3" if drift_oci_image_reproducibility_platform else "b2") * 32
            )
            rebuild_script.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env sh",
                        "set -eu",
                        "mkdir -p .buildish-out",
                        "printf 'rebuilt\\n' > .buildish-out/oci-image-rebuilt.marker",
                        "cat > \"$FAKE_DOCKER_STATE_DIR/imagetools-inspect-response.json\" <<'JSON'",
                        json.dumps(
                            {
                                "schemaVersion": 2,
                                "mediaType": "application/vnd.oci.image.index.v1+json",
                                "digest": rebuilt_top_level_digest,
                                "manifests": [
                                    {
                                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                        "digest": rebuilt_amd64_digest,
                                        "platform": {"architecture": "amd64", "os": "linux"},
                                    },
                                    {
                                        "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                        "digest": rebuilt_arm64_digest,
                                        "platform": {"architecture": "arm64", "os": "linux"},
                                    },
                                ],
                            }
                        ),
                        "JSON",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            rebuild_script.chmod(0o755)
            run_quiet(
                ["git", "-C", str(origin_dir), "add", "buildish-release-tooling/rebuild-oci-image.sh"],
                check=True,
            )
            run_quiet(
                ["git", "-C", str(origin_dir), "commit", "-m", "add oci rebuild script"],
                check=True,
            )

        source_commit_sha = git_rev_parse(origin_dir, "HEAD")
        git_create_annotated_tag(origin_dir, rc_tag)
        if mismatched_source_commit_sha:
            (origin_dir / "README.txt").write_text("root\nsecond\n", encoding="utf-8")
            run_quiet(["git", "-C", str(origin_dir), "add", "README.txt"], check=True)
            run_quiet(["git", "-C", str(origin_dir), "commit", "-m", "second commit"], check=True)
            source_commit_sha = git_rev_parse(origin_dir, "HEAD")
        source_date_epoch = int(
            run_quiet(
                [
                    "git",
                    "-C",
                    str(origin_dir),
                    "show",
                    "-s",
                    "--format=%ct",
                    source_commit_sha,
                ],
                check=True,
            ).stdout.strip()
        )

        run_quiet(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-gen-key",
                "Release Tooling Tests <release-tooling-tests@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            ],
            env={**os.environ, "GNUPGHOME": str(effective_gpg_home)},
            check=True,
        )
        keys_path.write_text(
            run_quiet(
                [
                    "gpg",
                    "--armor",
                    "--export",
                    "Release Tooling Tests <release-tooling-tests@example.invalid>",
                ],
                env={**os.environ, "GNUPGHOME": str(effective_gpg_home)},
                check=True,
            ).stdout,
            encoding="utf-8",
        )

        stage_dir.mkdir(parents=True, exist_ok=True)
        source_artifact_name = f"apache-{component_id}-{version}-incubating-src.tar.gz"
        source_artifact_path = stage_dir / source_artifact_name
        create_from_git(
            origin_dir,
            source_commit_sha,
            f"apache-{component_id}-{version}-incubating-src/",
            source_artifact_path,
        )
        source_artifact_sha512 = hashlib.sha512(source_artifact_path.read_bytes()).hexdigest()
        source_artifact_sha512_path = stage_dir / f"{source_artifact_name}.sha512"
        source_artifact_sha512_path.write_text(
            f"{source_artifact_sha512}  {source_artifact_name}\n",
            encoding="utf-8",
        )
        source_artifact_signature_path = stage_dir / f"{source_artifact_name}.asc"
        self._detached_sign(effective_gpg_home, source_artifact_path, source_artifact_signature_path)
        if drift_source_artifact:
            source_artifact_path.write_bytes(source_artifact_path.read_bytes() + b"drift\n")
        if missing_source_artifact:
            source_artifact_path.unlink()
        secondary_artifacts: list[dict[str, object]] = []
        if secondary_kind is not None:
            secondary_name = "buildish-example-bootstrap.zip"
            secondary_path = stage_dir / secondary_name
            if archive_generic_file_reproducibility:
                _write_zip_archive(
                    secondary_path,
                    member_name="bootstrap.txt",
                    payload=b"bootstrap zip bytes\n",
                    timestamp=(2026, 4, 30, 12, 0, 1),
                )
            else:
                secondary_path.write_bytes(b"bootstrap zip bytes\n")
            secondary_sha512 = hashlib.sha512(secondary_path.read_bytes()).hexdigest()
            secondary_sha512_path = stage_dir / f"{secondary_name}.sha512"
            secondary_sha512_path.write_text(
                f"{secondary_sha512}  {secondary_name}\n",
                encoding="utf-8",
            )
            secondary_signature_path = stage_dir / f"{secondary_name}.asc"
            self._detached_sign(effective_gpg_home, secondary_path, secondary_signature_path)
            manifest_secondary_sha512 = secondary_sha512
            if mismatched_secondary_digest:
                manifest_secondary_sha512 = ("0" * 127) + "1"
            secondary_artifact: dict[str, object] = {
                "artifact_id": "bootstrap-zip",
                "kind": secondary_kind,
                "filename": secondary_name,
                "uri": secondary_path.as_uri(),
                "checksums": {
                    "sha512": {
                        "value": manifest_secondary_sha512,
                        "uri": secondary_sha512_path.as_uri(),
                    }
                },
                "signatures": [
                    {
                        "type": "openpgp-detached-ascii-armored",
                        "uri": secondary_signature_path.as_uri(),
                    }
                ],
            }
            if include_generic_file_reproducibility:
                secondary_artifact["reproducibility"] = {
                    "profile_id": "bootstrap-zip",
                }
            if malformed_secondary_missing_artifact_id:
                secondary_artifact.pop("artifact_id")
            if malformed_secondary_missing_kind:
                secondary_artifact.pop("kind")
            secondary_artifacts.append(secondary_artifact)
            if include_second_generic_file_shared_profile:
                second_secondary_name = "buildish-example-bootstrap-alt.zip"
                second_secondary_path = stage_dir / second_secondary_name
                second_secondary_path.write_bytes(b"bootstrap zip bytes\n")
                second_secondary_sha512 = hashlib.sha512(second_secondary_path.read_bytes()).hexdigest()
                second_secondary_sha512_path = stage_dir / f"{second_secondary_name}.sha512"
                second_secondary_sha512_path.write_text(
                    f"{second_secondary_sha512}  {second_secondary_name}\n",
                    encoding="utf-8",
                )
                second_secondary_signature_path = stage_dir / f"{second_secondary_name}.asc"
                self._detached_sign(
                    effective_gpg_home,
                    second_secondary_path,
                    second_secondary_signature_path,
                )
                secondary_artifacts.append(
                    {
                        "artifact_id": "bootstrap-zip-alt",
                        "kind": secondary_kind,
                        "filename": second_secondary_name,
                        "uri": second_secondary_path.as_uri(),
                        "checksums": {
                            "sha512": {
                                "value": second_secondary_sha512,
                                "uri": second_secondary_sha512_path.as_uri(),
                            }
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": second_secondary_signature_path.as_uri(),
                            }
                        ],
                        "reproducibility": {
                            "profile_id": "bootstrap-zip",
                        },
                    }
                )
            if missing_secondary_artifact:
                secondary_path.unlink()
        if include_maven_repository:
            staging_repository_id = "orgapacheexample-1234"
            repository_root = sandbox_dir / staging_repository_id
            repository_root.mkdir(parents=True, exist_ok=True)
            artifact_relative_path = Path("org/example/app/1.0.0/app-1.0.0.jar")
            artifact_path = repository_root / artifact_relative_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            if include_maven_repository_reproducibility:
                _write_zip_archive(
                    artifact_path,
                    member_name="app.txt",
                    payload=b"jar payload\n",
                    timestamp=(2026, 4, 30, 12, 0, 1),
                )
                pom_path = artifact_path.with_name("app-1.0.0.pom")
                pom_path.write_text("<project>stable</project>\n", encoding="utf-8")
                metadata_path = repository_root / "org/example/app/maven-metadata.xml"
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_text("<metadata/>\n", encoding="utf-8")
            else:
                artifact_path.write_bytes(b"jar-bytes\n")
            artifact_sha512 = hashlib.sha512(artifact_path.read_bytes()).hexdigest()
            artifact_sha512_path = artifact_path.with_name(f"{artifact_path.name}.sha512")
            artifact_sha512_path.write_text(
                f"{artifact_sha512}  {artifact_path.name}\n",
                encoding="utf-8",
            )
            artifact_signature_path = artifact_path.with_name(f"{artifact_path.name}.asc")
            self._detached_sign(effective_gpg_home, artifact_path, artifact_signature_path)
            repository_bundle_dir = sandbox_dir / "maven-bundle"
            repository_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_maven_repository_registration(
                Namespace(
                    artifact_id="maven-staging-main",
                    staging_repository_id=staging_repository_id,
                    base_url=f"{repository_root.as_uri()}/",
                    inventory_workers=None,
                    progress="off",
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                repository_bundle_dir,
            )
            maven_artifact = registration.secondary_artifact.model_dump(mode="json", exclude_none=True)
            inventory = dict(maven_artifact["inventory"])
            inventory_filename = inventory["filename"]
            inventory["uri"] = (repository_bundle_dir / inventory_filename).as_uri()
            maven_artifact["inventory"] = inventory
            if include_maven_repository_reproducibility:
                maven_artifact["reproducibility"] = {
                    "profile_id": "maven-staging",
                }
            secondary_artifacts.append(maven_artifact)
            if drift_maven_repository:
                artifact_path.write_bytes(b"jar-drift\n")
        if include_python_distribution:
            distribution_dir = sandbox_dir / "pypi-files"
            distribution_dir.mkdir(parents=True, exist_ok=True)
            distribution_path = distribution_dir / "example-1.2.3-py3-none-any.whl"
            if archive_python_distribution_reproducibility:
                _write_zip_archive(
                    distribution_path,
                    member_name="example/__init__.py",
                    payload=b"wheel payload\n",
                    timestamp=(2026, 4, 30, 12, 0, 1),
                )
            else:
                distribution_path.write_bytes(b"wheel payload\n")
            distribution_bundle_dir = sandbox_dir / "python-bundle"
            distribution_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_python_distribution_registration(
                Namespace(
                    artifact_id="pypi-wheel",
                    file=str(distribution_path),
                    filename=None,
                    uri=distribution_path.as_uri(),
                    index_url=(sandbox_dir / "simple").as_uri() + "/",
                    project_name="example",
                    package_version="1.2.3",
                    sha256=None,
                    sha256_uri=None,
                    attestation_repository=None,
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                distribution_bundle_dir,
            )
            python_artifact = registration.secondary_artifact.model_dump(
                mode="json",
                exclude_none=True,
            )
            simple_project_dir = sandbox_dir / "simple" / "example"
            simple_project_dir.mkdir(parents=True, exist_ok=True)
            simple_index_path = simple_project_dir / "index.json"
            simple_index_payload = {
                "files": [] if missing_python_index_entry else [
                    {
                        "filename": python_artifact["filename"],
                        "url": python_artifact["uri"],
                        "hashes": {
                            "sha256": python_artifact["checksums"]["sha256"]["value"],
                        },
                    }
                ]
            }
            simple_index_path.write_text(
                json.dumps(simple_index_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            if include_python_distribution_reproducibility:
                python_artifact["reproducibility"] = {
                    "profile_id": "pypi-wheel",
                }
            secondary_artifacts.append(python_artifact)
        if include_npm_package:
            artifact_file_path = sandbox_dir / "npm-dist" / "buildish-example-1.2.3.tgz"
            artifact_file_path.parent.mkdir(parents=True, exist_ok=True)
            if archive_npm_package_reproducibility:
                _write_tgz_archive(
                    artifact_file_path,
                    member_name="package/package.json",
                    payload=b"npm package payload\n",
                    mtime=1714435201,
                )
            else:
                artifact_file_path.write_bytes(b"npm package payload\n")
            artifact_bytes = artifact_file_path.read_bytes()
            expected_sha512 = hashlib.sha512(artifact_bytes).hexdigest()
            expected_integrity = "sha512-" + base64.b64encode(hashlib.sha512(artifact_bytes).digest()).decode("ascii")
            live_integrity = (
                "sha512-" + base64.b64encode(bytes(64)).decode("ascii")
                if drift_npm_registry_integrity
                else expected_integrity
            )
            registry_root = sandbox_dir / "npm-registry"
            metadata_dir = registry_root / "@apache" / "buildish-example"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            (metadata_dir / "index.json").write_text(
                json.dumps(
                    {
                        "name": "@apache/buildish-example",
                        "versions": {
                            "1.2.3": {
                                "name": "@apache/buildish-example",
                                "version": "1.2.3",
                                "dist": {
                                    "tarball": artifact_file_path.as_uri(),
                                    "integrity": live_integrity,
                                    "signatures": [],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            npm_artifact: dict[str, object] = {
                "artifact_id": "npm-package-main",
                "kind": "npm-package",
                "filename": artifact_file_path.name,
                "uri": artifact_file_path.as_uri(),
                "registry_url": registry_root.as_uri() + "/",
                "package_name": "@apache/buildish-example",
                "version": "1.2.3",
                "integrity": expected_integrity,
                "checksums": {
                    "sha512": {
                        "value": expected_sha512,
                    }
                },
            }
            if include_npm_package_reproducibility:
                npm_artifact["reproducibility"] = {
                    "profile_id": "npm-package-main",
                }
            secondary_artifacts.append(npm_artifact)
            if drift_npm_tarball:
                artifact_file_path.write_bytes(artifact_bytes + b"registry drift\n")
            if missing_npm_tarball:
                artifact_file_path.unlink()
        if include_oci_image:
            docker_path, docker_state_dir = create_fake_docker_launcher(sandbox_dir)
            extra_env["FAKE_DOCKER_STATE_DIR"] = str(docker_state_dir)
            prepend_dirs = (docker_path.parent,)
            top_level_digest = "sha256:" + ("d4" * 32)
            amd64_digest = "sha256:" + ("a1" * 32)
            arm64_digest = "sha256:" + ("b2" * 32)
            live_arm64_digest = "sha256:" + ("c3" * 32) if drift_oci_image else arm64_digest
            (docker_state_dir / "imagetools-inspect-response.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "mediaType": "application/vnd.oci.image.index.v1+json",
                        "digest": top_level_digest,
                        "manifests": [
                            {
                                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                "digest": amd64_digest,
                                "platform": {"architecture": "amd64", "os": "linux"},
                            },
                            {
                                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                                "digest": live_arm64_digest,
                                "platform": {"architecture": "arm64", "os": "linux"},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            oci_bundle_dir = sandbox_dir / "oci-bundle"
            oci_bundle_dir.mkdir(parents=True, exist_ok=True)
            registration = build_oci_image_registration(
                Namespace(
                    artifact_id="ghcr-main-image",
                    image_ref=None,
                    registry="ghcr.io",
                    repository="apache/buildish-example",
                    digest=top_level_digest,
                    platform_digests=[
                        f"linux/amd64={amd64_digest}",
                        f"linux/arm64={arm64_digest}",
                    ],
                    uri=None,
                    role=None,
                    git_commit_sha=None,
                    artifact_origin=None,
                ),
                oci_bundle_dir,
            )
            oci_artifact = registration.secondary_artifact.model_dump(mode="json", exclude_none=True)
            if include_oci_image_reproducibility:
                oci_artifact["reproducibility"] = {
                    "profile_id": "oci-main-image",
                }
            secondary_artifacts.append(oci_artifact)

        manifest_payload: dict[str, object] = {
            "schema_version": "1",
            "manifest_type": "rc-vote",
            "component_id": component_id,
            "version": version,
            "release_line": "1.2.x",
            "release_branch": "release/1.2.x",
            "source_repository_url": origin_dir.as_uri(),
            "source_commit_sha": source_commit_sha,
            "source_date_epoch": source_date_epoch,
            "final_tag": f"v{version}",
            "final_tag_mode": "rc-source-commit",
            "provenance": {"created_at": "2026-04-29T12:00:00Z", "tooling": {}},
            "trust_roots": {
                "asf_keys": {
                    "uri": keys_path.as_uri(),
                    "known_length_bytes": keys_path.stat().st_size,
                    "known_prefix_sha512": hashlib.sha512(keys_path.read_bytes()).hexdigest(),
                }
            },
            "draft_github_release": {
                "repository": "apache/buildish-example",
                "tag": rc_tag,
                "url": f"https://github.com/apache/buildish-example/releases/tag/{rc_tag}",
            },
            "vote_materials": {
                "source_artifacts": [
                    {
                        "role": "asf-source-release",
                        "filename": source_artifact_name,
                        "uri": source_artifact_path.as_uri(),
                        "artifact_origin": "source-commit",
                        "git_commit_sha": source_commit_sha,
                        "checksums": {
                            "sha512": {
                                "value": source_artifact_sha512,
                                "uri": source_artifact_sha512_path.as_uri(),
                            }
                        },
                        "signatures": [
                            {
                                "type": "openpgp-detached-ascii-armored",
                                "uri": source_artifact_signature_path.as_uri(),
                            }
                        ],
                    }
                ],
                "secondary_artifacts": secondary_artifacts,
            },
            "verification": {
                "staging_svn_url": f"{stage_dir.as_uri()}/",
            },
        }
        if include_rc_tag:
            manifest_payload["rc_tag"] = rc_tag

        manifest_path = stage_dir / "rc-vote-manifest.json"
        manifest_text = json.dumps(manifest_payload, indent=2) + "\n"
        manifest_path.write_text(manifest_text, encoding="utf-8")
        manifest_sha512 = hashlib.sha512(manifest_text.encode("utf-8")).hexdigest()
        manifest_sha512_path = stage_dir / "rc-vote-manifest.json.sha512"
        manifest_sha512_path.write_text(
            f"{manifest_sha512}  rc-vote-manifest.json\n",
            encoding="utf-8",
        )
        manifest_signature_path = stage_dir / "rc-vote-manifest.json.asc"
        self._detached_sign(effective_gpg_home, manifest_path, manifest_signature_path)

        return VerificationFixture(
            config_path=config_path,
            keys_url=keys_path.as_uri(),
            manifest_url=manifest_path.as_uri(),
            manifest_output_path=manifest_output_path,
            inspection_bundle_path=inspection_bundle_path,
            origin_dir=origin_dir,
            log_path=log_path,
            report_json_path=report_json_path,
            report_md_path=report_md_path,
            source_commit_sha=source_commit_sha,
            source_date_epoch=source_date_epoch,
            work_dir=work_dir,
            extra_env=extra_env,
            prepend_dirs=prepend_dirs,
        )

    @staticmethod
    def _detached_sign(gpg_home: Path, input_path: Path, output_path: Path) -> None:
        fingerprint = secret_key_fingerprint(gpg_home)
        run_quiet(
            [
                "gpg",
                "--batch",
                "--yes",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--local-user",
                fingerprint,
                "--armor",
                "--detach-sign",
                "--output",
                str(output_path),
                str(input_path),
            ],
            env={**os.environ, "GNUPGHOME": str(gpg_home)},
            check=True,
        )

    @staticmethod
    def _fixture_cli_env(
        fixture: VerificationFixture,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        merged_env = dict(fixture.extra_env)
        if extra_env is not None:
            merged_env.update(extra_env)
        return cli_env(
            fixture.manifest_output_path,
            extra_env=merged_env,
            prepend_dirs=fixture.prepend_dirs,
        )
