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
from buildish_release_tooling.release.models import ComponentConfig, PrepareRcState
from buildish_release_tooling.release.release_state import (
    derive_candidate_tag,
    derive_final_tag,
    parse_candidate_tag,
    require_candidate_label,
    require_semantic_version,
)


def prepare_rc_source_artifact_name(source_artifact_prefix: str, version: str) -> str:
    """Derive the canonical source-artifact filename for a version."""

    return f"{source_artifact_prefix}-{version}-incubating-src.tar.gz"


def prepare_rc_source_artifact_root_name(source_artifact_name: str) -> str:
    """Derive the root directory name contained inside a source artifact."""

    if not source_artifact_name.endswith(".tar.gz"):
        raise ValueError(f"source artifact name must end with .tar.gz: {source_artifact_name}")
    return source_artifact_name[: -len(".tar.gz")]


def prepare_rc_source_artifact_prefix_path(source_artifact_name: str) -> str:
    """Derive the `git archive --prefix` path for a source artifact."""

    return f"{prepare_rc_source_artifact_root_name(source_artifact_name)}/"


def resolve_prepare_rc_state(
    repo: GitRepository,
    component_config: ComponentConfig,
    version: str,
    source_sha: str | None,
    rc_tag: str | None = None,
    candidate_label: str | None = None,
) -> PrepareRcState:
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
            component_config.candidate_start_number,
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
    source_artifact_name = prepare_rc_source_artifact_name(
        component_config.source_artifact_prefix, version
    )
    return PrepareRcState(
        resolved_release_branch=resolved_release_branch,
        resolved_source_ref=resolved_source_ref,
        source_date_epoch=source_date_epoch,
        candidate_label=candidate_label,
        rc_number=rc_number,
        rc_tag=resolved_rc_tag,
        final_tag=derive_final_tag(version),
        source_artifact_name=source_artifact_name,
        source_artifact_root_name=prepare_rc_source_artifact_root_name(source_artifact_name),
        source_artifact_prefix_path=prepare_rc_source_artifact_prefix_path(source_artifact_name),
        staging_url=f"{component_config.asf_dist_dev_base.rstrip('/')}/{resolved_rc_tag.removeprefix('v')}/",
    )
