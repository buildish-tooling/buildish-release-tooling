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

"""Provider-neutral candidate state resolution."""

from __future__ import annotations

from buildish_release_tooling.release.config import (
    ReleaseConfig,
    require_candidate_config,
)
from buildish_release_tooling.release.core.config import BuiltSourceSnapshotConfig
from buildish_release_tooling.release.core.models import (
    CandidateIdentity,
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.naming import (
    derive_candidate_tag,
    render_release_name_template,
    require_candidate_label,
    require_semantic_version,
)
from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    PromotionState,
    SourceArtifactPlan,
)
from buildish_release_tooling.release.manifests import CandidateManifestV1
from buildish_release_tooling.release.direct_release import selected_source_ref
from buildish_release_tooling.release.git_repo import GitRepository


def resolve_candidate_release_state(
    repo: GitRepository,
    config: ReleaseConfig,
    version: str,
    source_ref: str | None,
    candidate_label: str | None,
) -> CandidateReleaseState:
    """Resolve one exact candidate without platform or foundation publication data."""

    if config.lifecycle.mode != "candidate":
        raise ValueError("resolve-candidate requires lifecycle.mode candidate")
    candidate_config = require_candidate_config(config)
    normalized_version = require_semantic_version(version)
    selected_ref = selected_source_ref(repo, config, normalized_version, source_ref)
    resolved_commit = repo.resolve_commit(selected_ref)
    label = require_candidate_label(candidate_label or candidate_config.label)
    number = repo.next_matching_candidate_number(
        normalized_version,
        label,
        candidate_config.start_number,
    )
    tag_name = derive_candidate_tag(normalized_version, label, number)
    release = ReleaseIdentity(
        component=ComponentIdentity(
            id=config.component.id,
            display_name=config.component.display_name,
        ),
        version=normalized_version,
    )
    candidate_tag = TagIdentity(
        name=tag_name,
        target_commit=resolved_commit,
        purpose="candidate",
    )
    source_artifact = None
    if isinstance(config.source.snapshot, BuiltSourceSnapshotConfig):
        source_artifact = SourceArtifactPlan(
            filename=render_release_name_template(
                config.source.snapshot.filename_template,
                component=config.component.id,
                version=normalized_version,
                field_name="source artifact filename",
            ),
            archive_root=render_release_name_template(
                config.source.snapshot.archive_root_template,
                component=config.component.id,
                version=normalized_version,
                field_name="source artifact archive root",
            ),
        )
    return CandidateReleaseState(
        release=release,
        source=SourceRevision(
            repository=repo.remote_url(),
            commit_sha=resolved_commit,
            source_ref=selected_ref,
        ),
        source_date_epoch=repo.commit_timestamp_epoch(resolved_commit),
        candidate=CandidateIdentity(
            release=release,
            label=label,
            number=number,
            tag=candidate_tag,
        ),
        final_tag_identity=TagIdentity(
            name=config.versioning.final_tag_template.format(version=normalized_version),
            target_commit=resolved_commit,
            purpose="final",
        ),
        source_artifact=source_artifact,
    )


def resolve_promotion_state(
    config: ReleaseConfig,
    manifest: CandidateManifestV1,
    *,
    version: str,
    candidate_tag: str,
    candidate_manifest_digest: str,
) -> PromotionState:
    """Resolve exact candidate evidence into provider-neutral promotion state."""

    if config.lifecycle.mode != "candidate":
        raise ValueError("resolve-promotion requires lifecycle.mode candidate")
    normalized_version = require_semantic_version(version)
    if manifest.release.component.id != config.component.id:
        raise ValueError("candidate manifest component does not match release configuration")
    if manifest.release.version != normalized_version:
        raise ValueError("candidate manifest version does not match requested promotion")
    if manifest.candidate.tag.name != candidate_tag:
        raise ValueError("candidate manifest does not match selected candidate tag")
    final_tag = TagIdentity(
        name=config.versioning.final_tag_template.format(version=normalized_version),
        target_commit=manifest.source.commit_sha,
        purpose="final",
    )
    return PromotionState(
        release=manifest.release,
        source=manifest.source,
        candidate=manifest.candidate,
        candidate_manifest_digest=candidate_manifest_digest,
        final_tag=final_tag,
        artifacts=manifest.artifacts,
        verification_results=manifest.verification_results,
        publications=manifest.publications,
        tooling=manifest.tooling,
    )
