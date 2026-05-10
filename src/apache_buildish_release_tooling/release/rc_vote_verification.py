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

"""Helpers for authoritative RC vote-manifest verification and mirrored asset checks."""

from __future__ import annotations

from pydantic import ValidationError

from apache_buildish_release_tooling.release.github_releases import (
    download_release_asset_text,
    release_asset_ids_by_names,
)
from apache_buildish_release_tooling.release.contracts import (
    RcVoteManifestV1,
    SourceArtifactContract,
)
from apache_buildish_release_tooling.release.models import CommandContext
from apache_buildish_release_tooling.release.prepare_rc_state import prepare_rc_source_artifact_name
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_text, uri_sha512
from apache_buildish_release_tooling.release.release_state import derive_final_tag


def required_source_release_file_names(source_artifact_prefix: str, version: str) -> list[str]:
    """Return the mandatory ASF source-release files expected in one staged RC directory."""

    artifact_name = prepare_rc_source_artifact_name(source_artifact_prefix, version)
    return [
        artifact_name,
        f"{artifact_name}.sha512",
        f"{artifact_name}.asc",
    ]


def required_rc_vote_manifest_file_names() -> list[str]:
    """Return the RC vote-manifest files expected after vote finalization."""

    return [
        "rc-vote-manifest.json",
        "rc-vote-manifest.json.sha512",
        "rc-vote-manifest.json.asc",
    ]


def verified_staged_source_artifact_sha512(source_artifact_url: str) -> str:
    """Recompute one staged source-artifact digest and verify the `.sha512` sidecar."""

    actual_sha512 = uri_sha512(source_artifact_url)
    sidecar_url = f"{source_artifact_url}.sha512"
    staged_sha512 = _sha512_sidecar_digest(read_uri_text(sidecar_url), source=sidecar_url)
    if staged_sha512 != actual_sha512:
        raise ValueError("staged source artifact .sha512 sidecar does not match the staged source artifact bytes")
    return actual_sha512


def verify_staged_source_release_against_vote_manifest(
    context: CommandContext,
    *,
    repository_slug: str,
    release_payload: dict[str, object],
    source_url: str,
    version: str,
    selected_rc_tag: str,
    expected_source_artifact_name: str,
) -> str:
    """Verify staged source-release bytes against the mirrored authoritative vote manifest."""

    source_url = source_url.rstrip("/")
    manifest_name = "rc-vote-manifest.json"
    mirrored_manifest_text = _mirrored_release_asset_text(
        repository_slug,
        release_payload,
        asset_name=manifest_name,
    )
    staged_manifest_url = f"{source_url}/{manifest_name}"
    staged_manifest_text = read_uri_text(staged_manifest_url)
    if staged_manifest_text != mirrored_manifest_text:
        raise ValueError("RC vote manifest in SVN staging does not match the mirrored GitHub Release asset")

    manifest_payload = _rc_vote_manifest_payload(staged_manifest_text, source=staged_manifest_url)
    if manifest_payload.component_id != context.component_config.component_id:
        raise ValueError(f"RC vote manifest component does not match {context.component_config.component_id}")
    if manifest_payload.version != version:
        raise ValueError(f"RC vote manifest version does not match {version}")
    if manifest_payload.rc_tag != selected_rc_tag:
        raise ValueError(f"RC vote manifest RC tag does not match {selected_rc_tag}")
    if manifest_payload.final_tag != derive_final_tag(version):
        raise ValueError(f"RC vote manifest final tag does not match v{version}")

    source_artifact = _source_artifact_entry_from_vote_manifest(
        manifest_payload,
        source=staged_manifest_url,
    )
    manifest_filename = source_artifact.filename
    if manifest_filename != expected_source_artifact_name:
        raise ValueError(
            "RC vote manifest source artifact filename does not match the expected staged source release"
        )
    expected_source_artifact_url = f"{source_url}/{expected_source_artifact_name}"

    expected_sha512 = _manifest_source_artifact_sha512(source_artifact)
    actual_sha512 = verified_staged_source_artifact_sha512(expected_source_artifact_url)
    if actual_sha512 != expected_sha512:
        raise ValueError("staged source artifact checksum does not match the authoritative RC vote manifest")
    return expected_sha512


def _rc_vote_manifest_payload(manifest_text: str, *, source: str) -> RcVoteManifestV1:
    """Parse and validate one RC vote-manifest JSON document."""

    try:
        return RcVoteManifestV1.model_validate_json(manifest_text)
    except ValidationError as exc:
        raise ValueError(f"RC vote manifest is invalid: {source}") from exc


def _source_artifact_entry_from_vote_manifest(
    manifest_payload: RcVoteManifestV1,
    *,
    source: str,
) -> SourceArtifactContract:
    """Return the single source-artifact entry recorded in one RC vote manifest."""

    source_artifacts = manifest_payload.vote_materials.source_artifacts
    if len(source_artifacts) != 1:
        raise ValueError(f"RC vote manifest must contain exactly one source artifact: {source}")
    return source_artifacts[0]


def _manifest_source_artifact_sha512(
    source_artifact: SourceArtifactContract,
) -> str:
    """Return the SHA512 recorded for one manifest source artifact."""

    return source_artifact.checksums.sha512.value


def _sha512_sidecar_digest(sidecar_text: str, *, source: str) -> str:
    """Parse the first digest field from one staged `.sha512` sidecar."""

    fields = sidecar_text.strip().split()
    if not fields or not fields[0]:
        raise ValueError(f"invalid sha512 sidecar contents: {source}")
    return fields[0]


def _mirrored_release_asset_text(
    repository_slug: str,
    release_payload: dict[str, object],
    *,
    asset_name: str,
) -> str:
    """Download one mirrored draft-release asset as UTF-8 text."""

    asset_ids = release_asset_ids_by_names(release_payload, asset_names=[asset_name])
    asset_id = asset_ids.get(asset_name)
    if asset_id is None:
        raise ValueError(f"draft GitHub Release is missing mirrored asset: {asset_name}")
    return download_release_asset_text(repository_slug, asset_id)
