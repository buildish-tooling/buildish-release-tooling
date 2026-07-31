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

"""Tests for provider-neutral direct, candidate, and promotion state."""

import unittest

from pydantic import ValidationError

from buildish_release_tooling.release.core.models import (
    CandidateIdentity,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    PromotionState,
)


class ReleaseStateTest(unittest.TestCase):
    """Verify lifecycle state keeps exact identities without provider coupling."""

    def setUp(self) -> None:
        self.commit_sha = "0123456789abcdef0123456789abcdef01234567"
        self.release = ReleaseIdentity(
            component=ComponentIdentity(id="example", display_name="Example"),
            version="1.2.3",
        )
        self.source = SourceRevision(
            repository="https://code.example/example",
            commit_sha=self.commit_sha,
            source_ref="main",
        )
        self.candidate = CandidateIdentity(
            release=self.release,
            label="rc",
            number=1,
            tag=TagIdentity(
                name="v1.2.3-rc1",
                target_commit=self.commit_sha,
                purpose="candidate",
            ),
        )

    def test_direct_state_serialization_has_no_candidate_fields(self) -> None:
        state = DirectReleaseState(
            release=self.release,
            source=self.source,
            final_tag=TagIdentity(
                name="v1.2.3",
                target_commit=self.commit_sha,
                purpose="final",
            ),
        )

        payload = state.model_dump(mode="json", exclude_none=True)
        self.assertNotIn("candidate", payload)
        self.assertFalse(any(key.startswith(("asf_", "github_")) for key in payload))

    def test_candidate_identity_is_deterministic_and_provider_independent(self) -> None:
        self.assertEqual(
            "example:1.2.3:rc:1:v1.2.3-rc1",
            self.candidate.stable_id,
        )

    def test_promotion_requires_exact_candidate_manifest_digest(self) -> None:
        with self.assertRaisesRegex(ValidationError, "candidate_manifest_digest"):
            PromotionState(
                release=self.release,
                source=self.source,
                candidate=self.candidate,
                candidate_manifest_digest="pending",
                final_tag=TagIdentity(
                    name="v1.2.3",
                    target_commit=self.commit_sha,
                    purpose="final",
                ),
            )

        promoted = PromotionState(
            release=self.release,
            source=self.source,
            candidate=self.candidate,
            candidate_manifest_digest="a" * 64,
            final_tag=TagIdentity(
                name="v1.2.3",
                target_commit=self.commit_sha,
                purpose="final",
            ),
        )
        self.assertEqual("v1.2.3-rc1", promoted.candidate.tag.name)
