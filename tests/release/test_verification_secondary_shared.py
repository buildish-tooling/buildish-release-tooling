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

"""Unit tests for tolerant secondary-artifact manifest readers."""

from __future__ import annotations

import unittest

from apache_buildish_release_tooling.release.contracts import GenericFileSecondaryArtifact
from apache_buildish_release_tooling.release.verification.secondary.shared import (
    MalformedSecondaryArtifactEntry,
    secondary_artifact_entries,
)


class SecondarySharedTest(unittest.TestCase):
    """Keep tolerant manifest-entry handling explicit and typed."""

    def test_secondary_artifact_entries_reject_missing_vote_materials(self) -> None:
        with self.assertRaisesRegex(ValueError, "manifest is missing vote_materials"):
            secondary_artifact_entries(
                {},
                source="https://example.invalid/rc-vote-manifest.json",
            )

    def test_secondary_artifact_entries_reject_non_list_secondary_artifacts(self) -> None:
        with self.assertRaisesRegex(
            Exception,
            "vote_materials.secondary_artifacts",
        ):
            secondary_artifact_entries(
                {
                    "vote_materials": {
                        "secondary_artifacts": "not-a-list",
                    }
                },
                source="https://example.invalid/rc-vote-manifest.json",
            )

    def test_secondary_artifact_entries_wrap_malformed_entries(self) -> None:
        entries = secondary_artifact_entries(
            {
                "vote_materials": {
                    "secondary_artifacts": [
                        {
                            "artifact_id": "broken-artifact",
                            "kind": "generic-file",
                        }
                    ]
                }
            },
            source="https://example.invalid/rc-vote-manifest.json",
        )

        self.assertEqual(1, len(entries))
        self.assertIsInstance(entries[0], MalformedSecondaryArtifactEntry)
        malformed_entry = entries[0]
        if not isinstance(malformed_entry, MalformedSecondaryArtifactEntry):
            self.fail("expected malformed secondary artifact wrapper")
        self.assertEqual("broken-artifact", malformed_entry.artifact_id)
        self.assertEqual("generic-file", malformed_entry.declared_kind)

    def test_secondary_artifact_entries_validate_supported_entries(self) -> None:
        entries = secondary_artifact_entries(
            {
                "vote_materials": {
                    "secondary_artifacts": [
                        {
                            "artifact_id": "bootstrap-zip",
                            "kind": "generic-file",
                            "filename": "buildish-example-bootstrap.zip",
                            "uri": "https://example.invalid/buildish-example-bootstrap.zip",
                            "checksums": {
                                "sha512": {
                                    "value": "a" * 128,
                                }
                            },
                            "signatures": [],
                        }
                    ]
                }
            },
            source="https://example.invalid/rc-vote-manifest.json",
        )

        self.assertEqual(1, len(entries))
        self.assertIsInstance(entries[0], GenericFileSecondaryArtifact)
