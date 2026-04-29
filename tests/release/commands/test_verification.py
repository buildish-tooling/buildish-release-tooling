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

from dataclasses import dataclass

from apache_buildish_release_tooling.release.gpg_signing import _effective_home, secret_key_fingerprint
from apache_buildish_release_tooling.release.source_artifact import create_from_git

from tests.release.commands.support import (
    Path,
    ReleaseCommandsIntegrationTestSupport,
    _read_simple_github_outputs,
    cleanup_sandbox,
    cli_env,
    command_available,
    create_build_test_sandbox,
    git_create_annotated_tag,
    git_rev_parse,
    hashlib,
    init_git_origin_and_clone,
    json,
    os,
    run_cli,
    subprocess,
)


@dataclass(frozen=True)
class VerificationFixture:
    """Reusable signed verification input set for one verify-rc integration test."""

    config_path: Path
    keys_url: str
    manifest_url: str
    manifest_output_path: Path
    origin_dir: Path
    report_json_path: Path
    report_md_path: Path
    source_commit_sha: str
    work_dir: Path


class VerificationCommandsIntegrationTest(ReleaseCommandsIntegrationTestSupport):
    """End-to-end coverage for the Phase 1a verify-rc command."""

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
            env=cli_env(
                fixture.manifest_output_path,
                extra_env={"GITHUB_OUTPUT": str(outputs_path)},
            ),
        )

        self.assertEqual(0, completed.returncode, msg=completed.stderr)
        report_payload = json.loads(fixture.report_json_path.read_text(encoding="utf-8"))
        self.assertEqual("verified", report_payload["verdict"])
        self.assertTrue(report_payload["manifest_verification"]["rc_tag_matches_source_commit_sha"])
        self.assertTrue(report_payload["source_artifact_verification"]["matches_source_commit_sha"])
        self.assertEqual(
            fixture.source_commit_sha,
            report_payload["manifest_verification"]["rc_tag_target_commit"],
        )
        self.assertIn("Verify RC", fixture.report_md_path.read_text(encoding="utf-8"))

        github_outputs = _read_simple_github_outputs(outputs_path)
        self.assertEqual("v1.2.3-rc0", github_outputs["rc_tag"])
        self.assertEqual(fixture.source_commit_sha, github_outputs["source_commit_sha"])

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
            env=cli_env(fixture.manifest_output_path),
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
            env=cli_env(fixture.manifest_output_path),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("secondary artifact checksum does not match the signed manifest", completed.stderr)

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
            env=cli_env(fixture.manifest_output_path),
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
            env=cli_env(fixture.manifest_output_path),
        )

        self.assertEqual(1, completed.returncode)
        self.assertIn("manifest rc_tag does not resolve to the declared source_commit_sha", completed.stderr)

    def _prepare_verification_fixture(
        self,
        sandbox_dir: Path,
        *,
        include_rc_tag: bool = True,
        mismatched_source_commit_sha: bool = False,
        secondary_kind: str | None = None,
        mismatched_secondary_digest: bool = False,
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
        report_json_path = sandbox_dir / "verify-report.json"
        report_md_path = sandbox_dir / "verify-report.md"
        manifest_output_path = sandbox_dir / "verify-rc-command.json"
        gpg_home = sandbox_dir / "gpg-home"
        gpg_home.mkdir(parents=True, exist_ok=True)
        gpg_home.chmod(0o700)
        effective_gpg_home = _effective_home(gpg_home)

        self._write_component_config(
            config_path,
            component_id=component_id,
            dev_base_url=(stage_dir.parent).as_uri(),
            release_base_url=(release_dir / component_id).as_uri(),
        )

        source_commit_sha = git_rev_parse(origin_dir, "HEAD")
        git_create_annotated_tag(origin_dir, rc_tag)
        if mismatched_source_commit_sha:
            (origin_dir / "README.txt").write_text("root\nsecond\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(origin_dir), "add", "README.txt"], check=True)
            subprocess.run(["git", "-C", str(origin_dir), "commit", "-m", "second commit"], check=True)
            source_commit_sha = git_rev_parse(origin_dir, "HEAD")

        subprocess.run(
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
            capture_output=True,
            text=True,
        )
        keys_path.write_text(
            subprocess.run(
                [
                    "gpg",
                    "--armor",
                    "--export",
                    "Release Tooling Tests <release-tooling-tests@example.invalid>",
                ],
                env={**os.environ, "GNUPGHOME": str(effective_gpg_home)},
                check=True,
                capture_output=True,
                text=True,
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
        secondary_artifacts: list[dict[str, object]] = []
        if secondary_kind is not None:
            secondary_name = "buildish-example-bootstrap.zip"
            secondary_path = stage_dir / secondary_name
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
            secondary_artifacts.append(
                {
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
            )

        manifest_payload: dict[str, object] = {
            "schema_version": "1",
            "manifest_type": "rc-vote",
            "component_id": component_id,
            "version": version,
            "release_line": "1.2.x",
            "release_branch": "release/1.2.x",
            "source_repository_url": origin_dir.as_uri(),
            "source_commit_sha": source_commit_sha,
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
            origin_dir=origin_dir,
            report_json_path=report_json_path,
            report_md_path=report_md_path,
            source_commit_sha=source_commit_sha,
            work_dir=work_dir,
        )

    @staticmethod
    def _detached_sign(gpg_home: Path, input_path: Path, output_path: Path) -> None:
        fingerprint = secret_key_fingerprint(gpg_home)
        subprocess.run(
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
            capture_output=True,
            text=True,
        )
