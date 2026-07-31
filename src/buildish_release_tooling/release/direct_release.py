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

"""Provider-neutral direct-release state resolution from Git source policy."""

from __future__ import annotations

from buildish_release_tooling.release.config import ReleaseConfig
from buildish_release_tooling.release.core.config import BuiltSourceSnapshotConfig
from buildish_release_tooling.release.core.models import (
    ComponentIdentity,
    ReleaseIdentity,
    SourceRevision,
    TagIdentity,
)
from buildish_release_tooling.release.core.naming import (
    render_release_name_template,
    require_semantic_version,
)
from buildish_release_tooling.release.core.state import DirectReleaseState, SourceArtifactPlan
from buildish_release_tooling.release.git_repo import GitRepository


def _selected_source_ref(
    repo: GitRepository,
    config: ReleaseConfig,
    version: str,
    source_ref: str | None,
) -> str:
    selection = config.source.selection
    if selection == "explicit-ref":
        if source_ref is None:
            raise ValueError("source ref is required when source.selection is explicit-ref")
        return source_ref
    if selection == "explicit-ref-or-default-branch":
        default_branch = config.source.default_branch
        if source_ref is None and default_branch is None:
            raise ValueError(
                "source.default_branch is required for default-branch source selection"
            )
        return source_ref or default_branch or ""
    if source_ref is not None:
        raise ValueError("source ref must not be supplied when source.selection is release-branch")
    return repo.resolve_release_branch_for_version(version)


def resolve_direct_release_state(
    repo: GitRepository,
    config: ReleaseConfig,
    version: str,
    source_ref: str | None,
) -> DirectReleaseState:
    """Resolve one exact direct-release source revision and immutable final tag."""

    if config.lifecycle.mode != "direct":
        raise ValueError("resolve-direct-release requires lifecycle.mode direct")
    normalized_version = require_semantic_version(version)
    selected_ref = _selected_source_ref(repo, config, normalized_version, source_ref)
    resolved_commit = repo.resolve_commit(selected_ref)
    snapshot = config.source.snapshot
    source_artifact = None
    if isinstance(snapshot, BuiltSourceSnapshotConfig):
        source_artifact = SourceArtifactPlan(
            filename=render_release_name_template(
                snapshot.filename_template,
                component=config.component.id,
                version=normalized_version,
                field_name="source artifact filename",
            ),
            archive_root=render_release_name_template(
                snapshot.archive_root_template,
                component=config.component.id,
                version=normalized_version,
                field_name="source artifact archive root",
            ),
        )
    release = ReleaseIdentity(
        component=ComponentIdentity(
            id=config.component.id,
            display_name=config.component.display_name,
        ),
        version=normalized_version,
    )
    return DirectReleaseState(
        release=release,
        source=SourceRevision(
            repository=repo.remote_url(),
            commit_sha=resolved_commit,
            source_ref=selected_ref,
        ),
        source_date_epoch=repo.commit_timestamp_epoch(resolved_commit),
        final_tag=TagIdentity(
            name=config.versioning.final_tag_template.format(version=normalized_version),
            target_commit=resolved_commit,
            purpose="final",
        ),
        source_artifact=source_artifact,
    )
