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

"""Unit tests for Phase 1 verify-rc helpers."""

from __future__ import annotations

from pathlib import Path
from typing import cast
import unittest

from buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityEffectiveBuildExecutionReport,
    ArtifactReproducibilityEffectiveExecutionReport,
    ArtifactReproducibilityReport,
    SourceArtifactContract,
)
from buildish_release_tooling.release.verification.common import SignatureVerification
from buildish_release_tooling.release.verification.phase1 import (
    _report_markdown,
    _source_artifact_reproducibility_payload,
)
from buildish_release_tooling.release.verification.rebuild import ReproducibilityModeDecision


class VerifyRcPhase1ReportTest(unittest.TestCase):
    """Keep report rendering strict when verification kinds evolve."""

    def test_source_artifact_reproducibility_payload_uses_internal_profile_id(self) -> None:
        source_artifact = SourceArtifactContract.model_validate(
            {
                "role": "asf-source-release",
                "filename": "apache-example-project-1.2.3-incubating-src.tar.gz",
                "uri": "https://dist.apache.org/example/apache-example-project-1.2.3-incubating-src.tar.gz",
                "artifact_origin": "source-commit",
                "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                "checksums": {"sha512": {"value": "a" * 128}},
                "signatures": [
                    {
                        "type": "openpgp-detached-ascii-armored",
                        "uri": "https://dist.apache.org/example/apache-example-project-1.2.3-incubating-src.tar.gz.asc",
                    }
                ],
                "reproducibility": {"profile_id": "source-release"},
            }
        )

        payload = _source_artifact_reproducibility_payload(
            source_artifact=source_artifact,
            source_artifact_path=Path("staged-source.tar.gz"),
            rebuilt_source_artifact_path=Path("rebuilt-source.tar.gz"),
            rebuilt_source_sha512="b" * 128,
            source_artifact_matches_source_commit=True,
            failures=[],
            inspection_bundle_root=None,
        )

        self.assertIsNotNone(payload)
        if payload is None:
            self.fail("expected reproducibility payload")
        self.assertEqual("source-artifact-from-git", payload.profile_id)
        self.assertIsNone(payload.canonical_recipe)

    def test_source_artifact_reproducibility_payload_is_none_without_rebuild_or_failures(self) -> None:
        source_artifact = SourceArtifactContract.model_validate(
            {
                "role": "asf-source-release",
                "filename": "apache-example-project-1.2.3-incubating-src.tar.gz",
                "uri": "https://dist.apache.org/example/apache-example-project-1.2.3-incubating-src.tar.gz",
                "artifact_origin": "source-commit",
                "git_commit_sha": "0123456789abcdef0123456789abcdef01234567",
                "checksums": {"sha512": {"value": "a" * 128}},
                "signatures": [
                    {
                        "type": "openpgp-detached-ascii-armored",
                        "uri": "https://dist.apache.org/example/apache-example-project-1.2.3-incubating-src.tar.gz.asc",
                    }
                ],
            }
        )

        payload = _source_artifact_reproducibility_payload(
            source_artifact=source_artifact,
            source_artifact_path=None,
            rebuilt_source_artifact_path=None,
            rebuilt_source_sha512=None,
            source_artifact_matches_source_commit=False,
            failures=[],
            inspection_bundle_root=None,
        )

        self.assertIsNone(payload)

    def test_report_markdown_rejects_unknown_secondary_artifact_kind(self) -> None:
        signature = SignatureVerification(
            signer_fingerprint="ABCDEF0123456789",
            signer_user_id=None,
            trust_label=None,
            key_algorithm="ed25519",
            key_size_bits=255,
        )

        with self.assertRaisesRegex(
            ValueError,
            "unsupported secondary artifact kind for markdown reporting: odd-artifact \\(mystery-kind\\)",
        ):
            _report_markdown(
                component_id="example-project",
                version="1.2.3",
                rc_tag="v1.2.3-rc0",
                source_commit_sha="0123456789abcdef0123456789abcdef01234567",
                source_date_epoch=1714032000,
                source_repository_url="https://github.com/apache/example-project.git",
                manifest_url="https://dist.apache.org/example/rc-vote-manifest.json",
                keys_url="https://downloads.apache.org/incubator/example/KEYS",
                verdict="verified",
                failures=[],
                manifest_signature=signature,
                source_artifact_filename="apache-example-project-1.2.3-incubating-src.tar.gz",
                source_artifact_url="https://dist.apache.org/example/apache-example-project-1.2.3-incubating-src.tar.gz",
                source_artifact_signature=signature,
                actual_source_sha512="f" * 128,
                source_artifact_reproducibility=ArtifactReproducibilityReport(
                    profile_id="source-artifact-from-git",
                    verdict="verified",
                    comparison_mode="exact-bytes",
                    canonical_recipe=None,
                    effective_execution=ArtifactReproducibilityEffectiveExecutionReport(
                        backend="host-direct",
                        build=ArtifactReproducibilityEffectiveBuildExecutionReport(
                            command=["internal:create-from-git"],
                            working_directory="source-repository",
                            output_paths=["rebuilt-source.tar.gz"],
                            injected_environment_keys=[],
                        ),
                    ),
                    matches_remote_bytes=True,
                    failure_class=None,
                    evidence=[],
                    issues=[],
                ),
                manifest_issues=[],
                source_artifact_issues=[],
                reproducibility_decision=ReproducibilityModeDecision(
                    requested_mode="integrity-only",
                    effective_mode="integrity-only",
                    prompt_used=False,
                    prompt_confirmed=None,
                    build_checks_allowed=False,
                    build_checks_skipped_reason="disabled",
                ),
                build_checks_attempted=False,
                secondary_artifact_verifications=[
                    cast(
                        AnySecondaryArtifactVerification,
                        {
                            "artifact_id": "odd-artifact",
                            "kind": "mystery-kind",
                        },
                    )
                ],
            )
