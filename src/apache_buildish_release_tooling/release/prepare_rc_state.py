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

"""Helpers for deriving the shared state used by `Prepare RC` commands."""

from __future__ import annotations

from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.models import ComponentConfig, PrepareRcState
from apache_buildish_release_tooling.release.release_state import (
    derive_final_tag,
    derive_rc_tag,
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
) -> PrepareRcState:
    """Resolve and validate the common state shared across RC-related commands."""

    version = require_semantic_version(version)
    if source_sha:
        resolved_source_ref = source_sha
        resolved_release_branch = "explicit-source-sha"
    else:
        resolved_release_branch = repo.resolve_release_branch_for_version(version)
        resolved_source_ref = repo.resolve_commit(resolved_release_branch)
    if rc_tag is None:
        rc_number = repo.next_matching_rc_number(version)
        resolved_rc_tag = derive_rc_tag(version, rc_number)
    else:
        expected_prefix = f"v{version}-rc"
        if not rc_tag.startswith(expected_prefix):
            raise ValueError(f"explicit RC tag does not match version {version}: {rc_tag}")
        rc_suffix = rc_tag.removeprefix(expected_prefix)
        if not rc_suffix.isdigit():
            raise ValueError(f"explicit RC tag does not end in a numeric suffix: {rc_tag}")
        rc_number = int(rc_suffix)
        resolved_rc_tag = rc_tag
    source_artifact_name = prepare_rc_source_artifact_name(
        component_config.source_artifact_prefix, version
    )
    return PrepareRcState(
        resolved_release_branch=resolved_release_branch,
        resolved_source_ref=resolved_source_ref,
        rc_number=rc_number,
        rc_tag=resolved_rc_tag,
        final_tag=derive_final_tag(version),
        source_artifact_name=source_artifact_name,
        source_artifact_root_name=prepare_rc_source_artifact_root_name(source_artifact_name),
        source_artifact_prefix_path=prepare_rc_source_artifact_prefix_path(source_artifact_name),
        staging_url=f"{component_config.asf_dist_dev_base.rstrip('/')}/{version}-rc{rc_number}/",
    )
