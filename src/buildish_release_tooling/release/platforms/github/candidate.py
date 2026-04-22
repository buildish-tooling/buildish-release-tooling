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

"""Exact-state validation for GitHub-hosted release candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from buildish_release_tooling.release.core.models import ArtifactReference
from buildish_release_tooling.release.core.state import CandidateReleaseState
from buildish_release_tooling.release.platforms.github.direct import (
    expected_release_artifacts,
    observed_release_assets,
    validate_observed_release_assets,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubCandidatePublication,
)
from buildish_release_tooling.release.platforms.github.selection import asset_release_url
from buildish_release_tooling.release.platforms.github.text import (
    render_candidate_release_body,
)
from buildish_release_tooling.release.source_artifact import checksum

CANDIDATE_MANIFEST_ASSET_NAME = "candidate-manifest.json"


def candidate_release_name(state: CandidateReleaseState) -> str:
    """Return the deterministic GitHub title for one exact candidate."""

    return (
        f"{state.release.component.display_name} {state.release.version} "
        f"({state.candidate.label}{state.candidate.number})"
    )


def artifact_references_from_paths(
    asset_paths: Sequence[Path],
) -> list[ArtifactReference]:
    """Record immutable file identities for local candidate assets."""

    seen: set[str] = set()
    artifacts: list[ArtifactReference] = []
    for asset_path in sorted(asset_paths, key=lambda path: path.name):
        if not asset_path.is_file():
            raise ValueError(f"GitHub candidate asset file does not exist: {asset_path}")
        if asset_path.name == CANDIDATE_MANIFEST_ASSET_NAME:
            raise ValueError(
                f"{CANDIDATE_MANIFEST_ASSET_NAME} is reserved for the durable manifest"
            )
        if asset_path.name in seen:
            raise ValueError(f"duplicate local GitHub candidate asset: {asset_path.name}")
        seen.add(asset_path.name)
        artifacts.append(
            ArtifactReference(
                kind="generic-file",
                logical_name=asset_path.name,
                digests={"sha256": checksum(asset_path, "sha256")},
                size_bytes=asset_path.stat().st_size,
            )
        )
    return artifacts


def candidate_state_with_local_artifacts(
    state: CandidateReleaseState,
    asset_paths: Sequence[Path],
) -> CandidateReleaseState:
    """Bind supplied local assets or verify them against an existing state inventory."""

    supplied = artifact_references_from_paths(asset_paths)
    if state.artifacts:
        expected = {artifact.logical_name: artifact for artifact in state.artifacts}
        observed = {artifact.logical_name: artifact for artifact in supplied}
        if expected != observed:
            raise ValueError("local candidate assets do not match candidate-release state")
    return state if state.artifacts else state.model_copy(update={"artifacts": supplied})


def validate_candidate_release(
    state: CandidateReleaseState,
    repository: str,
    release_payload: Mapping[str, object],
    *,
    allow_attached_manifest: bool,
) -> GitHubCandidatePublication:
    """Validate candidate metadata and immutable build-asset identities."""

    release_id, draft, prerelease, release_url = _validate_candidate_metadata(
        state,
        release_payload,
    )
    observed = observed_release_assets(release_payload)
    manifest_asset = observed.pop(CANDIDATE_MANIFEST_ASSET_NAME, None)
    if manifest_asset is not None and not allow_attached_manifest:
        raise ValueError("GitHub candidate release already contains a candidate manifest")
    missing = validate_observed_release_assets(
        expected_release_artifacts(state),
        observed,
    )
    if missing:
        raise ValueError(
            "GitHub candidate release asset set does not match candidate state: "
            f"missing={missing}, unexpected=[]"
        )
    assets = [observed[name] for name in expected_release_artifacts(state)]
    if manifest_asset is not None:
        assets.append(manifest_asset)
    return GitHubCandidatePublication(
        repository=repository,
        release_id=release_id,
        release_url=release_url,
        tag=state.candidate.tag.name,
        draft=draft,
        prerelease=prerelease,
        assets=assets,
    )


def _validate_candidate_metadata(
    state: CandidateReleaseState,
    release_payload: Mapping[str, object],
) -> tuple[int, bool, bool, str]:
    release_id = release_payload.get("id")
    if not isinstance(release_id, int) or release_id < 1:
        raise ValueError("GitHub candidate release does not include a valid numeric id")
    if release_payload.get("tag_name") != state.candidate.tag.name:
        raise ValueError("GitHub candidate release tag does not match candidate state")
    if release_payload.get("name") != candidate_release_name(state):
        raise ValueError("GitHub candidate release title does not match candidate state")
    expected_body = render_candidate_release_body(state, state.artifacts)
    if release_payload.get("body") != expected_body:
        raise ValueError("GitHub candidate release body does not match candidate state")
    draft = release_payload.get("draft")
    prerelease = release_payload.get("prerelease")
    if not isinstance(draft, bool) or not isinstance(prerelease, bool):
        raise ValueError("GitHub candidate release visibility is invalid")
    if not draft and not prerelease:
        raise ValueError("published GitHub candidate release must remain a pre-release")
    release_url = asset_release_url(dict(release_payload))
    if not release_url:
        raise ValueError("GitHub candidate release does not include a release URL")
    return release_id, draft, prerelease, release_url


def missing_candidate_release_assets(
    state: CandidateReleaseState,
    release_payload: Mapping[str, object],
) -> list[str]:
    """Validate candidate metadata and return only absent build assets."""

    _validate_candidate_metadata(state, release_payload)
    observed = observed_release_assets(release_payload)
    observed.pop(CANDIDATE_MANIFEST_ASSET_NAME, None)
    return validate_observed_release_assets(
        expected_release_artifacts(state),
        observed,
    )
