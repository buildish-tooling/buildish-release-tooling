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

"""Tests for optional vote packages bound to exact candidate manifests."""

import unittest

from buildish_release_tooling.release.core.manifests import ManifestDigestReference
from buildish_release_tooling.release.core.models import (
    CandidateIdentity,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
    ToolingInvocationProvenance,
)
from buildish_release_tooling.release.manifests import CandidateManifestV1, VotePackageV1


class VotePackageTest(unittest.TestCase):
    """Verify voting remains optional and external to lifecycle state transitions."""

    def test_vote_package_binds_one_exact_candidate_manifest_digest(self) -> None:
        commit_sha = "0123456789abcdef0123456789abcdef01234567"
        release = ReleaseIdentity(
            component=ComponentIdentity(id="example", display_name="Example"),
            version="1.2.3",
        )
        candidate_tag = TagIdentity(
            name="v1.2.3-rc1", target_commit=commit_sha, purpose="candidate"
        )
        candidate = CandidateManifestV1(
            release=release,
            candidate=CandidateIdentity(
                release=release, label="rc", number=1, tag=candidate_tag
            ),
            source=SourceRevision(
                repository="https://code.example/example", commit_sha=commit_sha
            ),
            candidate_tag=candidate_tag,
            tooling=ToolingInvocationProvenance(version="0.1.0"),
            created_at="2026-07-31T12:00:00Z",
        )

        vote = VotePackageV1(
            subject="[VOTE] Release Example 1.2.3 based on rc1",
            profile_selector="generic",
            candidate_manifest=ManifestDigestReference(
                uri="https://releases.example/candidate-manifest.json",
                digest="a" * 64,
            ),
            embedded_candidate_manifest=candidate,
            verification_instructions="Verify the referenced candidate manifest and artifacts.",
            opening_template="Please vote on this exact candidate.",
            result_template="The external vote result is: <result>.",
            created_at="2026-07-31T12:05:00Z",
        )

        self.assertEqual("a" * 64, vote.candidate_manifest.digest)
        embedded = vote.embedded_candidate_manifest
        if embedded is None:
            self.fail("expected embedded candidate manifest")
        self.assertEqual("candidate-manifest", embedded.kind)
        self.assertNotIn("quorum", vote.model_dump(mode="json"))
