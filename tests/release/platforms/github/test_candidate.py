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

"""Unit tests for GitHub candidate artifact identity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from buildish_release_tooling.release.core.models import (
    CandidateIdentity,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.state import CandidateReleaseState
from buildish_release_tooling.release.platforms.github.candidate import (
    artifact_references_from_paths,
    candidate_state_with_local_artifacts,
)


class GitHubCandidateArtifactTest(unittest.TestCase):
    """Verify candidate asset inventories are deterministic and exact."""

    def test_asset_argument_order_does_not_change_candidate_inventory(self) -> None:
        commit = "0123456789abcdef0123456789abcdef01234567"
        release = ReleaseIdentity(
            component=ComponentIdentity(id="example", display_name="Example"),
            version="1.2.3",
        )
        candidate_tag = TagIdentity(
            name="v1.2.3-rc1",
            target_commit=commit,
            purpose="candidate",
        )
        state = CandidateReleaseState(
            release=release,
            source=SourceRevision(
                repository="https://github.com/buildish-tooling/example.git",
                commit_sha=commit,
                source_ref="main",
            ),
            source_date_epoch=1714032000,
            candidate=CandidateIdentity(
                release=release,
                label="rc",
                number=1,
                tag=candidate_tag,
            ),
            final_tag_identity=TagIdentity(
                name="v1.2.3",
                target_commit=commit,
                purpose="final",
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "a.zip"
            second = root / "b.zip"
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            expected = artifact_references_from_paths([second, first])
            bound = state.model_copy(update={"artifacts": expected})

            actual = candidate_state_with_local_artifacts(bound, [second, first])

        self.assertEqual(["a.zip", "b.zip"], [item.logical_name for item in actual.artifacts])


if __name__ == "__main__":
    unittest.main()
