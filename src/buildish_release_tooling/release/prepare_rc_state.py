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

"""Helpers for deriving the shared state used by `Prepare RC` commands."""

from __future__ import annotations

from buildish_release_tooling.release.git_repo import GitRepository
from buildish_release_tooling.release.config import (
    ReleaseConfig,
    require_asf_profile,
    require_built_source_snapshot,
    require_candidate_config,
)
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
from buildish_release_tooling.release.core.naming import (
    derive_candidate_tag,
    parse_candidate_tag,
    render_release_name_template,
    require_candidate_label,
    require_semantic_version,
)

def resolve_prepare_rc_state(
    repo: GitRepository,
    component_config: ReleaseConfig,
    version: str,
    source_sha: str | None,
    rc_tag: str | None = None,
    candidate_label: str | None = None,
) -> CandidateReleaseState:
    """Resolve and validate the common state shared across RC-related commands."""

    version = require_semantic_version(version)
    if source_sha:
        resolved_source_ref = source_sha
        resolved_release_branch = "explicit-source-sha"
    else:
        resolved_release_branch = repo.resolve_release_branch_for_version(version)
        resolved_source_ref = repo.resolve_commit(resolved_release_branch)
    source_date_epoch = repo.commit_timestamp_epoch(resolved_source_ref)
    if rc_tag is None:
        candidate_label = require_candidate_label(candidate_label or "rc")
        rc_number = repo.next_matching_candidate_number(
            version,
            candidate_label,
            require_candidate_config(component_config).start_number,
        )
        resolved_rc_tag = derive_candidate_tag(version, candidate_label, rc_number)
    else:
        parsed_label, rc_number = parse_candidate_tag(version, rc_tag)
        if candidate_label is not None and parsed_label != candidate_label:
            raise ValueError(
                f"explicit candidate tag label does not match {candidate_label}: {rc_tag}"
            )
        candidate_label = parsed_label
        resolved_rc_tag = rc_tag
    source_snapshot = require_built_source_snapshot(component_config)
    source_artifact_name = render_release_name_template(
        source_snapshot.filename_template,
        component=component_config.component.id,
        version=version,
        field_name="source artifact filename",
    )
    source_artifact_root_name = render_release_name_template(
        source_snapshot.archive_root_template,
        component=component_config.component.id,
        version=version,
        field_name="source artifact archive root",
    )
    release_identity = ReleaseIdentity(
        component=ComponentIdentity(
            id=component_config.component.id,
            display_name=component_config.component.display_name,
        ),
        version=version,
    )
    candidate_tag = TagIdentity(
        name=resolved_rc_tag,
        target_commit=resolved_source_ref,
        purpose="candidate",
    )
    return CandidateReleaseState(
        release=release_identity,
        source=SourceRevision(
            repository=repo.remote_url(),
            commit_sha=resolved_source_ref,
            source_ref=resolved_release_branch,
        ),
        source_date_epoch=source_date_epoch,
        candidate=CandidateIdentity(
            release=release_identity,
            label=candidate_label,
            number=rc_number,
            tag=candidate_tag,
        ),
        final_tag_identity=TagIdentity(
            name=component_config.versioning.final_tag_template.format(version=version),
            target_commit=resolved_source_ref,
            purpose="final",
        ),
        source_artifact=SourceArtifactPlan(
            filename=source_artifact_name,
            archive_root=source_artifact_root_name,
        ),
        publications=[
            PublicationReference(
                target_kind="asf-dist-svn-candidate",
                uri=(
                    f"{require_asf_profile(component_config).dist_dev_base.rstrip('/')}"
                    f"/{resolved_rc_tag.removeprefix('v')}/"
                ),
            )
        ],
    )
