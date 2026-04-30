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

"""Unit tests for Phase 1 verify-rc helpers."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.verification.common import SignatureVerification
from apache_buildish_release_tooling.release.verification.phase1 import _report_markdown
from apache_buildish_release_tooling.release.verification.rebuild import ReproducibilityModeDecision


class VerifyRcPhase1ReportTest(unittest.TestCase):
    """Keep report rendering strict when verification kinds evolve."""

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
                component_id="buildish-example",
                version="1.2.3",
                rc_tag="v1.2.3-rc0",
                source_commit_sha="0123456789abcdef0123456789abcdef01234567",
                source_date_epoch=1714032000,
                source_repository_url="https://github.com/apache/buildish-example.git",
                manifest_url="https://dist.apache.org/example/rc-vote-manifest.json",
                keys_url="https://downloads.apache.org/incubator/buildish/KEYS",
                verdict="verified",
                failures=[],
                manifest_signature=signature,
                source_artifact_filename="apache-buildish-example-1.2.3-incubating-src.tar.gz",
                source_artifact_url="https://dist.apache.org/example/apache-buildish-example-1.2.3-incubating-src.tar.gz",
                source_artifact_signature=signature,
                actual_source_sha512="f" * 128,
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
                    {
                        "artifact_id": "odd-artifact",
                        "kind": "mystery-kind",
                    }
                ],
            )
