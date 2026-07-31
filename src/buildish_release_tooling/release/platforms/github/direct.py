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

"""Exact-state validation for direct GitHub final releases."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from buildish_release_tooling.release.core.models import ArtifactReference
from buildish_release_tooling.release.core.state import (
    CandidateReleaseState,
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.platforms.github.manifests import (
    GitHubAssetIdentity,
    GitHubFinalPublication,
)
from buildish_release_tooling.release.platforms.github.releases import release_assets
from buildish_release_tooling.release.platforms.github.selection import asset_release_url
from buildish_release_tooling.release.source_artifact import checksum


def direct_release_name(state: DirectReleaseState | PromotionState) -> str:
    """Return the deterministic GitHub title for one direct final release."""

    return f"{state.release.component.display_name} {state.release.version}"


ReleaseArtifactState = DirectReleaseState | CandidateReleaseState | PromotionState
FinalReleaseState = DirectReleaseState | PromotionState


def expected_release_artifacts(
    state: ReleaseArtifactState,
) -> dict[str, ArtifactReference]:
    expected: dict[str, ArtifactReference] = {}
    for artifact in state.artifacts:
        name = artifact.logical_name
        if Path(name).name != name:
            raise ValueError(f"GitHub Release asset logical_name must be a basename: {name}")
        if name in expected:
            raise ValueError(f"duplicate direct-release artifact logical_name: {name}")
        sha256 = artifact.digests.get("sha256")
        if sha256 is None:
            raise ValueError(f"direct GitHub Release artifact requires a sha256 digest: {name}")
        if artifact.size_bytes is None:
            raise ValueError(f"direct GitHub Release artifact requires size_bytes: {name}")
        expected[name] = artifact
    return expected


def validate_local_release_assets(
    state: ReleaseArtifactState,
    asset_paths: Sequence[Path],
) -> list[Path]:
    """Validate local upload bytes against the exact direct-release artifact inventory."""

    expected = expected_release_artifacts(state)
    supplied: dict[str, Path] = {}
    for asset_path in asset_paths:
        if not asset_path.is_file():
            raise ValueError(f"GitHub Release asset file does not exist: {asset_path}")
        if asset_path.name in supplied:
            raise ValueError(f"duplicate local GitHub Release asset name: {asset_path.name}")
        supplied[asset_path.name] = asset_path
    if set(supplied) != set(expected):
        missing = sorted(set(expected) - set(supplied))
        unexpected = sorted(set(supplied) - set(expected))
        raise ValueError(
            "local GitHub Release asset set does not match direct-release state: "
            f"missing={missing}, unexpected={unexpected}"
        )
    ordered_paths: list[Path] = []
    for name, artifact in expected.items():
        asset_path = supplied[name]
        if asset_path.stat().st_size != artifact.size_bytes:
            raise ValueError(f"local GitHub Release asset size mismatch: {name}")
        if checksum(asset_path, "sha256") != artifact.digests["sha256"]:
            raise ValueError(f"local GitHub Release asset sha256 mismatch: {name}")
        ordered_paths.append(asset_path)
    return ordered_paths


def validate_final_tag(state: FinalReleaseState, tag_target_commit: str | None) -> None:
    """Require the immutable final tag to exist at the state's exact source commit."""

    if tag_target_commit is None:
        raise ValueError(f"final tag does not exist: {state.final_tag.name}")
    if tag_target_commit != state.final_tag.target_commit:
        raise ValueError(
            f"final tag {state.final_tag.name} targets {tag_target_commit}, "
            f"expected {state.final_tag.target_commit}"
        )


def validate_final_release(
    state: FinalReleaseState,
    repository: str,
    release_payload: Mapping[str, object],
    *,
    expected_body: str,
) -> GitHubFinalPublication:
    """Validate exact GitHub release metadata and asset identities or fail closed."""

    release_id, draft, release_url = _validate_release_metadata(
        state,
        release_payload,
        expected_body=expected_body,
    )
    expected = expected_release_artifacts(state)
    observed = observed_release_assets(release_payload)
    missing = validate_observed_release_assets(expected, observed)
    if missing:
        raise ValueError(
            "GitHub final release asset set does not match direct-release state: "
            f"missing={missing}, unexpected=[]"
        )
    return GitHubFinalPublication(
        repository=repository,
        release_id=release_id,
        release_url=release_url,
        tag=state.final_tag.name,
        draft=draft,
        prerelease=False,
        assets=[observed[name] for name in expected],
    )


def observe_final_release(
    state: FinalReleaseState,
    repository: str,
    release_payload: Mapping[str, object],
) -> GitHubFinalPublication:
    """Return a typed exact-tag GitHub observation without policy comparison."""

    release_id = release_payload.get("id")
    if not isinstance(release_id, int) or release_id < 1:
        raise ValueError("GitHub final release does not include a valid numeric id")
    if release_payload.get("tag_name") != state.final_tag.name:
        raise ValueError("GitHub final release tag does not match direct-release state")
    draft = release_payload.get("draft")
    prerelease = release_payload.get("prerelease")
    if not isinstance(draft, bool) or not isinstance(prerelease, bool):
        raise ValueError("GitHub final release draft/prerelease state is invalid")
    release_url = asset_release_url(dict(release_payload))
    if not release_url:
        raise ValueError("GitHub final release does not include a release URL")
    observed = observed_release_assets(release_payload)
    return GitHubFinalPublication(
        repository=repository,
        release_id=release_id,
        release_url=release_url,
        tag=state.final_tag.name,
        draft=draft,
        prerelease=prerelease,
        assets=[observed[name] for name in sorted(observed)],
    )


def missing_final_release_assets(
    state: FinalReleaseState,
    release_payload: Mapping[str, object],
    *,
    expected_body: str,
) -> list[str]:
    """Validate existing metadata/assets and return only absent expected asset names."""

    _validate_release_metadata(state, release_payload, expected_body=expected_body)
    return validate_observed_release_assets(
        expected_release_artifacts(state),
        observed_release_assets(release_payload),
    )


def _validate_release_metadata(
    state: FinalReleaseState,
    release_payload: Mapping[str, object],
    *,
    expected_body: str,
) -> tuple[int, bool, str]:
    release_id = release_payload.get("id")
    if not isinstance(release_id, int) or release_id < 1:
        raise ValueError("GitHub final release does not include a valid numeric id")
    if release_payload.get("tag_name") != state.final_tag.name:
        raise ValueError("GitHub final release tag does not match direct-release state")
    if release_payload.get("name") != direct_release_name(state):
        raise ValueError("GitHub final release title does not match direct-release state")
    if release_payload.get("body") != expected_body:
        raise ValueError("GitHub final release body does not match direct-release state")
    draft = release_payload.get("draft")
    prerelease = release_payload.get("prerelease")
    if not isinstance(draft, bool) or prerelease is not False:
        raise ValueError("GitHub final release draft/prerelease state is invalid")
    release_url = asset_release_url(dict(release_payload))
    if not release_url:
        raise ValueError("GitHub final release does not include a release URL")
    return release_id, draft, release_url


def observed_release_assets(
    release_payload: Mapping[str, object],
) -> dict[str, GitHubAssetIdentity]:
    observed: dict[str, GitHubAssetIdentity] = {}
    for asset_payload in release_assets(release_payload):
        name = asset_payload.get("name")
        asset_id = asset_payload.get("id")
        size = asset_payload.get("size")
        digest = asset_payload.get("digest")
        if not isinstance(name, str) or not name:
            raise ValueError("GitHub final release contains an asset without a valid name")
        if name in observed:
            raise ValueError(f"GitHub final release contains a duplicate asset: {name}")
        if (
            not isinstance(asset_id, int)
            or not isinstance(size, int)
            or not isinstance(digest, str)
        ):
            raise ValueError(f"GitHub final release asset identity is incomplete: {name}")
        observed[name] = GitHubAssetIdentity(
            name=name,
            asset_id=asset_id,
            size_bytes=size,
            digest=digest,
        )
    return observed


def validate_observed_release_assets(
    expected: Mapping[str, ArtifactReference],
    observed: Mapping[str, GitHubAssetIdentity],
) -> list[str]:
    unexpected = sorted(set(observed) - set(expected))
    if unexpected:
        raise ValueError(
            "GitHub final release asset set does not match direct-release state: "
            f"missing=[], unexpected={unexpected}"
        )
    for name in set(expected) & set(observed):
        expected_artifact = expected[name]
        observed_asset = observed[name]
        if observed_asset.size_bytes != expected_artifact.size_bytes:
            raise ValueError(f"GitHub final release asset size mismatch: {name}")
        if observed_asset.digest != f"sha256:{expected_artifact.digests['sha256']}":
            raise ValueError(f"GitHub final release asset sha256 mismatch: {name}")
    return sorted(set(expected) - set(observed))
