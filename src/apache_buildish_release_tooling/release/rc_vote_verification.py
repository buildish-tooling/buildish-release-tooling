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

import tempfile
from pathlib import Path

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
from apache_buildish_release_tooling.release.rc_vote_manifest import (
    DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
    DEFAULT_KEYS_MAX_BYTES,
    DEFAULT_MANIFEST_MAX_BYTES,
    DEFAULT_SIGNATURE_MAX_BYTES,
    download_uri_to_path,
    read_uri_text,
    uri_sha512,
)
from apache_buildish_release_tooling.release.release_state import derive_final_tag
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    validate_fetch_uri,
    verify_checksum_sidecar,
)

_RC_VOTE_MANIFEST_NAME = "rc-vote-manifest.json"


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
    allow_non_production_release_targets: bool,
) -> str:
    """Verify staged source-release bytes against the mirrored authoritative vote manifest."""

    source_url = source_url.rstrip("/")
    mirrored_manifest_text = _mirrored_release_asset_text(
        repository_slug,
        release_payload,
        asset_name=_RC_VOTE_MANIFEST_NAME,
    )
    staged_manifest_url = f"{source_url}/{_RC_VOTE_MANIFEST_NAME}"
    staged_manifest_text = _read_validated_uri_text(
        staged_manifest_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="staged RC vote manifest",
        max_bytes=DEFAULT_MANIFEST_MAX_BYTES,
    )
    if staged_manifest_text != mirrored_manifest_text:
        raise ValueError("RC vote manifest in SVN staging does not match the mirrored GitHub Release asset")

    manifest_payload = _verified_rc_vote_manifest_payload(
        context,
        manifest_text=staged_manifest_text,
        checksum_sidecar_text=_read_validated_uri_text(
            f"{staged_manifest_url}.sha512",
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="staged RC vote manifest .sha512 sidecar",
            max_bytes=DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
        ),
        signature_text=_read_validated_uri_text(
            f"{staged_manifest_url}.asc",
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="staged RC vote manifest detached signature",
            max_bytes=DEFAULT_SIGNATURE_MAX_BYTES,
        ),
        source=staged_manifest_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )
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


def verified_mirrored_rc_vote_manifest(
    context: CommandContext,
    *,
    repository_slug: str,
    release_payload: dict[str, object],
    allow_non_production_release_targets: bool,
) -> RcVoteManifestV1 | None:
    """Return a mirrored GitHub Release vote manifest only after checksum and signature verification."""

    sidecar_name = f"{_RC_VOTE_MANIFEST_NAME}.sha512"
    signature_name = f"{_RC_VOTE_MANIFEST_NAME}.asc"
    asset_ids = release_asset_ids_by_names(
        release_payload,
        asset_names=[_RC_VOTE_MANIFEST_NAME, sidecar_name, signature_name],
    )
    manifest_id = asset_ids.get(_RC_VOTE_MANIFEST_NAME)
    if manifest_id is None:
        return None
    sidecar_id = asset_ids.get(sidecar_name)
    if sidecar_id is None:
        raise ValueError(f"draft GitHub Release is missing mirrored asset: {sidecar_name}")
    signature_id = asset_ids.get(signature_name)
    if signature_id is None:
        raise ValueError(f"draft GitHub Release is missing mirrored asset: {signature_name}")
    return _verified_rc_vote_manifest_payload(
        context,
        manifest_text=download_release_asset_text(repository_slug, manifest_id),
        checksum_sidecar_text=download_release_asset_text(repository_slug, sidecar_id),
        signature_text=download_release_asset_text(repository_slug, signature_id),
        source=f"GitHub Release asset {_RC_VOTE_MANIFEST_NAME}",
        allow_non_production_release_targets=allow_non_production_release_targets,
    )


def _verified_rc_vote_manifest_payload(
    context: CommandContext,
    *,
    manifest_text: str,
    checksum_sidecar_text: str,
    signature_text: str,
    source: str,
    allow_non_production_release_targets: bool,
) -> RcVoteManifestV1:
    """Verify one vote manifest's sidecars before parsing trusted release metadata from it."""

    with tempfile.TemporaryDirectory(prefix="buildish-rc-vote-manifest-") as temp_dir:
        work_dir = Path(temp_dir)
        manifest_path = work_dir / _RC_VOTE_MANIFEST_NAME
        sidecar_path = work_dir / f"{_RC_VOTE_MANIFEST_NAME}.sha512"
        signature_path = work_dir / f"{_RC_VOTE_MANIFEST_NAME}.asc"
        keys_path = work_dir / "KEYS"
        manifest_path.write_text(manifest_text, encoding="utf-8")
        sidecar_path.write_text(checksum_sidecar_text, encoding="utf-8")
        signature_path.write_text(signature_text, encoding="utf-8")
        verify_checksum_sidecar(
            manifest_path,
            sidecar_path,
            algorithm="sha512",
            purpose="RC vote manifest",
        )
        keys_uri = context.component_config.asf_keys_url
        validate_fetch_uri(
            keys_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="ASF KEYS URL for RC vote manifest verification",
        )
        download_uri_to_path(keys_uri, keys_path, max_bytes=DEFAULT_KEYS_MAX_BYTES)
        GpgVerifier(work_dir / "gnupg", keys_path).verify_detached(
            target_path=manifest_path,
            signature_path=signature_path,
        )

    manifest_payload = _rc_vote_manifest_payload(manifest_text, source=source)
    if manifest_payload.trust_roots.asf_keys.uri != context.component_config.asf_keys_url:
        raise ValueError(
            "RC vote manifest ASF KEYS trust root does not match the component configuration"
        )
    return manifest_payload


def _read_validated_uri_text(
    uri: str,
    *,
    allow_non_production_release_targets: bool,
    purpose: str,
    max_bytes: int,
) -> str:
    """Read one URI after enforcing the production/non-production target policy."""

    validate_fetch_uri(
        uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=purpose,
    )
    return read_uri_text(uri, max_bytes=max_bytes)


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
