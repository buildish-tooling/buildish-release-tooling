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

"""Reusable provider-neutral runtime state fixtures."""

from buildish_release_tooling.release.core.models import (
    CandidateIdentity,
    ComponentIdentity,
    PublicationReference,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    SourceArtifactPlan,
)


def candidate_release_state() -> CandidateReleaseState:
    """Return one exact candidate state for unit tests."""

    commit_sha = "0123456789abcdef0123456789abcdef01234567"
    release = ReleaseIdentity(
        component=ComponentIdentity(
            id="example-project",
            display_name="Apache Example Project",
        ),
        version="1.2.3",
    )
    return CandidateReleaseState(
        release=release,
        source=SourceRevision(
            repository="https://github.com/apache/example-project",
            commit_sha=commit_sha,
            source_ref="release/1.2.x",
        ),
        source_date_epoch=1714032000,
        candidate=CandidateIdentity(
            release=release,
            label="rc",
            number=2,
            tag=TagIdentity(
                name="v1.2.3-rc2",
                target_commit=commit_sha,
                purpose="candidate",
            ),
        ),
        final_tag_identity=TagIdentity(
            name="v1.2.3",
            target_commit=commit_sha,
            purpose="final",
        ),
        source_artifact=SourceArtifactPlan(
            filename="apache-example-project-1.2.3-incubating-src.tar.gz",
            archive_root="apache-example-project-1.2.3-incubating-src",
        ),
        publications=[
            PublicationReference(
                target_kind="asf-dist-svn-candidate",
                uri=(
                    "https://dist.apache.org/repos/dist/dev/incubator/example/"
                    "example-project/1.2.3-rc2/"
                ),
            )
        ],
    )
