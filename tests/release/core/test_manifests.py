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

"""Tests for stable candidate/release manifests and typed promotion evidence."""

import unittest

from buildish_release_tooling.release.core.manifests import (
    ByteIdenticalPromotionEvidence,
    ManifestDigestReference,
    PromotedCandidateReference,
    SameSourceRevisionPromotionEvidence,
)
from buildish_release_tooling.release.core.models import (
    ArtifactReference,
    CandidateIdentity,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
    ToolingInvocationProvenance,
)
from buildish_release_tooling.release.manifests import (
    CandidateManifestV1,
    ReleaseManifestV1,
)


class StableManifestTest(unittest.TestCase):
    """Verify lifecycle manifests encode only selected capabilities and exact evidence."""

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
        self.candidate_tag = TagIdentity(
            name="v1.2.3-rc1",
            target_commit=self.commit_sha,
            purpose="candidate",
        )
        self.candidate = CandidateIdentity(
            release=self.release,
            label="rc",
            number=1,
            tag=self.candidate_tag,
        )
        self.tooling = ToolingInvocationProvenance(
            version="0.1.0", revision="fedcba9876543210"
        )

    def test_candidate_manifest_needs_neither_vote_nor_provider_extension(self) -> None:
        manifest = CandidateManifestV1(
            release=self.release,
            candidate=self.candidate,
            source=self.source,
            candidate_tag=self.candidate_tag,
            tooling=self.tooling,
            created_at="2026-07-31T12:00:00Z",
        )

        payload = manifest.model_dump(mode="json", exclude_none=True)
        self.assertEqual("candidate-manifest", payload["kind"])
        self.assertEqual([], payload["extensions"])
        serialized = str(payload)
        self.assertNotIn("vote", serialized)
        self.assertNotIn("asf_", serialized)
        self.assertNotIn("github_", serialized)

    def test_direct_release_manifest_omits_promoted_candidate_block(self) -> None:
        manifest = ReleaseManifestV1(
            release=self.release,
            source=self.source,
            final_tag=TagIdentity(
                name="v1.2.3", target_commit=self.commit_sha, purpose="final"
            ),
            tooling=self.tooling,
            created_at="2026-07-31T12:05:00Z",
        )

        payload = manifest.model_dump(mode="json")
        self.assertNotIn("promoted_candidate", payload)
        self.assertEqual([], payload["promotion_evidence"])

    def test_promoted_release_uses_explicit_per_artifact_relations(self) -> None:
        digest = "a" * 64
        manifest = ReleaseManifestV1(
            release=self.release,
            source=self.source,
            final_tag=TagIdentity(
                name="v1.2.3", target_commit=self.commit_sha, purpose="final"
            ),
            artifacts=[
                ArtifactReference(
                    kind="binary",
                    logical_name="example.zip",
                    digests={"sha256": digest},
                )
            ],
            promoted_candidate=PromotedCandidateReference(
                candidate=self.candidate,
                manifest=ManifestDigestReference(
                    uri="https://releases.example/candidate-manifest.json",
                    digest="b" * 64,
                ),
            ),
            promotion_evidence=[
                ByteIdenticalPromotionEvidence(
                    artifact_name="example.zip",
                    candidate_digests={"sha256": digest},
                    final_digests={"sha256": digest},
                ),
                SameSourceRevisionPromotionEvidence(
                    artifact_name="source-snapshot",
                    candidate_tag="v1.2.3-rc1",
                    final_tag="v1.2.3",
                    source_commit_sha=self.commit_sha,
                ),
            ],
            tooling=self.tooling,
            created_at="2026-07-31T12:10:00Z",
        )

        relations = [item["relation"] for item in manifest.model_dump()["promotion_evidence"]]
        self.assertEqual(["byte-identical", "same-source-revision"], relations)
