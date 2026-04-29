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

"""Phase 1a verifier helpers for manifest and source-artifact validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.process import run_logged_command
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import create_from_git, sha512
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    signature_payload,
    validate_fetch_uri,
    verify_checksum_sidecar,
)
from apache_buildish_release_tooling.release.verification.secondary import (
    verify_secondary_artifacts,
)


@dataclass(frozen=True)
class VerifyRcPhase1Result:
    """Structured result for one successful Phase 1a RC verification run."""

    component_id: str
    version: str
    rc_tag: str
    source_commit_sha: str
    source_repository_url: str
    manifest_url: str
    keys_url: str
    work_dir: Path
    report_payload: dict[str, Any]
    report_markdown: str


def verify_rc_phase1(
    *,
    manifest_url: str,
    keys_url: str,
    component_config: ComponentConfig | None,
    allow_non_production_release_targets: bool,
    work_dir: Path,
) -> VerifyRcPhase1Result:
    """Verify the signed RC vote manifest, source artifact, and supported secondary artifacts."""

    work_dir.mkdir(parents=True, exist_ok=True)
    validate_fetch_uri(
        manifest_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="RC vote manifest URL",
    )
    validate_fetch_uri(
        keys_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="KEYS URL",
    )

    manifest_path = work_dir / "rc-vote-manifest.json"
    manifest_path.write_bytes(read_uri_bytes(manifest_url))
    manifest_sha512_path = work_dir / "rc-vote-manifest.json.sha512"
    manifest_sha512_path.write_bytes(read_uri_bytes(f"{manifest_url}.sha512"))
    manifest_signature_path = work_dir / "rc-vote-manifest.json.asc"
    manifest_signature_path.write_bytes(read_uri_bytes(f"{manifest_url}.asc"))
    keys_path = work_dir / "KEYS"
    keys_path.write_bytes(read_uri_bytes(keys_url))

    manifest_sha512 = verify_checksum_sidecar(
        manifest_path,
        manifest_sha512_path,
        algorithm="sha512",
        purpose="RC vote manifest",
    )
    verifier = GpgVerifier(work_dir / "gnupg", keys_path)
    manifest_signature = verifier.verify_detached(
        target_path=manifest_path,
        signature_path=manifest_signature_path,
    )

    manifest_payload = _rc_vote_manifest_payload(manifest_path)
    component_id = _required_non_empty_string(manifest_payload, "component_id", source=manifest_url)
    version = _required_non_empty_string(manifest_payload, "version", source=manifest_url)
    source_commit_sha = _required_commit_sha(manifest_payload, "source_commit_sha", source=manifest_url)
    rc_tag = _required_non_empty_string(manifest_payload, "rc_tag", source=manifest_url)
    source_repository_url = _source_repository_url(manifest_payload, source=manifest_url)

    keys_url_matches_component_config = _cross_check_keys_url(
        manifest_payload=manifest_payload,
        keys_url=keys_url,
        component_config=component_config,
        source=manifest_url,
    )

    validate_fetch_uri(
        source_repository_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="Source repository URL",
    )
    repository_path = _clone_source_repository(
        source_repository_url=source_repository_url,
        work_dir=work_dir,
    )
    repository = GitRepository(repository_path)
    rc_tag_target_commit = repository.resolve_commit(rc_tag)
    if rc_tag_target_commit != source_commit_sha:
        raise ValueError(
            "manifest rc_tag does not resolve to the declared source_commit_sha: "
            f"{rc_tag} -> {rc_tag_target_commit} != {source_commit_sha}"
        )

    source_artifact = _source_artifact_entry(manifest_payload, source=manifest_url)
    if source_artifact.get("git_commit_sha") not in {None, source_commit_sha}:
        raise ValueError(
            "manifest source artifact git_commit_sha does not match source_commit_sha"
        )
    source_artifact_url = _required_non_empty_string(source_artifact, "uri", source=manifest_url)
    validate_fetch_uri(
        source_artifact_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="Source artifact URL",
    )
    source_artifact_filename = _required_non_empty_string(source_artifact, "filename", source=manifest_url)
    source_artifact_path = work_dir / source_artifact_filename
    source_artifact_path.write_bytes(read_uri_bytes(source_artifact_url))
    declared_source_sha512 = _required_sha512_from_source_artifact(source_artifact, source=manifest_url)
    actual_source_sha512 = sha512(source_artifact_path)
    if actual_source_sha512 != declared_source_sha512:
        raise ValueError(
            "staged source artifact checksum does not match the signed manifest: "
            f"{actual_source_sha512} != {declared_source_sha512}"
        )

    checksum_uri = _checksum_uri_from_source_artifact(source_artifact)
    source_sha512_sidecar_verified = False
    if checksum_uri is not None:
        validate_fetch_uri(
            checksum_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="Source artifact checksum sidecar URL",
        )
        source_sha512_sidecar_path = work_dir / f"{source_artifact_filename}.sha512"
        source_sha512_sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
        verify_checksum_sidecar(
            source_artifact_path,
            source_sha512_sidecar_path,
            algorithm="sha512",
            purpose="source artifact",
        )
        source_sha512_sidecar_verified = True

    source_signature_uri = _source_signature_uri(source_artifact, source=manifest_url)
    validate_fetch_uri(
        source_signature_uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="Source artifact signature URL",
    )
    source_signature_path = work_dir / f"{source_artifact_filename}.asc"
    source_signature_path.write_bytes(read_uri_bytes(source_signature_uri))
    source_artifact_signature = verifier.verify_detached(
        target_path=source_artifact_path,
        signature_path=source_signature_path,
    )

    expected_prefix = _archive_prefix_from_source_artifact_filename(source_artifact_filename)
    rebuilt_source_artifact_path = work_dir / f"rebuilt-{source_artifact_filename}"
    create_from_git(
        repository_path,
        source_commit_sha,
        expected_prefix,
        rebuilt_source_artifact_path,
    )
    rebuilt_source_sha512 = sha512(rebuilt_source_artifact_path)
    source_artifact_matches_source_commit = rebuilt_source_artifact_path.read_bytes() == source_artifact_path.read_bytes()
    if not source_artifact_matches_source_commit:
        raise ValueError(
            "staged source artifact does not match the declared source_commit_sha"
        )
    secondary_artifact_verifications = verify_secondary_artifacts(
        manifest_payload,
        manifest_url=manifest_url,
        work_dir=work_dir / "secondary-artifacts",
        verifier=verifier,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )

    report_payload: dict[str, Any] = {
        "schema_version": "1",
        "report_type": "verify-rc",
        "component_id": component_id,
        "version": version,
        "rc_tag": rc_tag,
        "source_commit_sha": source_commit_sha,
        "source_repository_url": source_repository_url,
        "manifest_url": manifest_url,
        "keys_url": keys_url,
        "verdict": "verified",
        "work_dir": str(work_dir),
        "manifest_verification": {
            "sha512": manifest_sha512,
            "keys_url_matches_manifest": True,
            "keys_url_matches_component_config": keys_url_matches_component_config,
            "signature": signature_payload(manifest_signature),
            "rc_tag_target_commit": rc_tag_target_commit,
            "rc_tag_matches_source_commit_sha": True,
        },
        "source_artifact_verification": {
            "filename": source_artifact_filename,
            "uri": source_artifact_url,
            "sha512": actual_source_sha512,
            "sha512_sidecar_verified": source_sha512_sidecar_verified,
            "signature": signature_payload(source_artifact_signature),
            "rebuilt_sha512": rebuilt_source_sha512,
            "matches_source_commit_sha": True,
        },
        "secondary_artifact_verifications": secondary_artifact_verifications,
    }

    report_markdown = _report_markdown(
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_repository_url=source_repository_url,
        manifest_url=manifest_url,
        keys_url=keys_url,
        manifest_signature=manifest_signature,
        source_artifact_filename=source_artifact_filename,
        source_artifact_url=source_artifact_url,
        source_artifact_signature=source_artifact_signature,
        actual_source_sha512=actual_source_sha512,
        secondary_artifact_verifications=secondary_artifact_verifications,
    )
    return VerifyRcPhase1Result(
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_repository_url=source_repository_url,
        manifest_url=manifest_url,
        keys_url=keys_url,
        work_dir=work_dir,
        report_payload=report_payload,
        report_markdown=report_markdown,
    )


def _rc_vote_manifest_payload(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"RC vote manifest must be a JSON object: {manifest_path}")
    if payload.get("manifest_type") != "rc-vote":
        raise ValueError(f"unexpected RC vote manifest type in {manifest_path}")
    return payload


def _required_non_empty_string(payload: dict[str, Any], field_name: str, *, source: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field {field_name} must be a non-empty string: {source}")
    return value.strip()


def _required_commit_sha(payload: dict[str, Any], field_name: str, *, source: str) -> str:
    value = _required_non_empty_string(payload, field_name, source=source)
    if len(value) != 40 or any(character not in "0123456789abcdefABCDEF" for character in value):
        raise ValueError(f"manifest field {field_name} must be a full 40-character Git commit SHA: {source}")
    return value.lower()


def _source_repository_url(manifest_payload: dict[str, Any], *, source: str) -> str:
    source_repository_url = manifest_payload.get("source_repository_url")
    if isinstance(source_repository_url, str) and source_repository_url.strip():
        return source_repository_url.strip()
    draft_release = manifest_payload.get("draft_github_release")
    if not isinstance(draft_release, dict):
        raise ValueError(f"manifest is missing source_repository_url and draft_github_release: {source}")
    repository_slug = draft_release.get("repository")
    if not isinstance(repository_slug, str) or not repository_slug.strip():
        raise ValueError(f"manifest is missing source_repository_url: {source}")
    return f"https://github.com/{repository_slug.strip()}.git"


def _cross_check_keys_url(
    *,
    manifest_payload: dict[str, Any],
    keys_url: str,
    component_config: ComponentConfig | None,
    source: str,
) -> bool | None:
    trust_roots = manifest_payload.get("trust_roots")
    if not isinstance(trust_roots, dict):
        raise ValueError(f"manifest is missing trust_roots: {source}")
    asf_keys = trust_roots.get("asf_keys")
    if not isinstance(asf_keys, dict):
        raise ValueError(f"manifest is missing trust_roots.asf_keys: {source}")
    manifest_keys_url = _required_non_empty_string(asf_keys, "uri", source=source)
    if manifest_keys_url != keys_url:
        raise ValueError(f"manifest KEYS URL does not match the explicit keys_url: {manifest_keys_url} != {keys_url}")
    if component_config is None:
        return None
    if component_config.asf_keys_url != keys_url:
        raise ValueError(
            "component-config asf_keys_url does not match the explicit keys_url: "
            f"{component_config.asf_keys_url} != {keys_url}"
        )
    return True


def _source_artifact_entry(manifest_payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    vote_materials = manifest_payload.get("vote_materials")
    if not isinstance(vote_materials, dict):
        raise ValueError(f"manifest is missing vote_materials: {source}")
    source_artifacts = vote_materials.get("source_artifacts")
    if not isinstance(source_artifacts, list) or len(source_artifacts) != 1:
        raise ValueError(f"manifest must contain exactly one source artifact: {source}")
    source_artifact = source_artifacts[0]
    if not isinstance(source_artifact, dict):
        raise ValueError(f"manifest source artifact must be an object: {source}")
    return source_artifact


def _required_sha512_from_source_artifact(source_artifact: dict[str, Any], *, source: str) -> str:
    checksums = source_artifact.get("checksums")
    if not isinstance(checksums, dict):
        raise ValueError(f"manifest source artifact is missing checksums: {source}")
    sha512_payload = checksums.get("sha512")
    if not isinstance(sha512_payload, dict):
        raise ValueError(f"manifest source artifact is missing sha512: {source}")
    return _required_commit_sha256_style_digest(sha512_payload, "value", source=source)


def _checksum_uri_from_source_artifact(source_artifact: dict[str, Any]) -> str | None:
    checksums = source_artifact.get("checksums")
    if not isinstance(checksums, dict):
        return None
    sha512_payload = checksums.get("sha512")
    if not isinstance(sha512_payload, dict):
        return None
    checksum_uri = sha512_payload.get("uri")
    if isinstance(checksum_uri, str) and checksum_uri.strip():
        return checksum_uri.strip()
    return None


def _source_signature_uri(source_artifact: dict[str, Any], *, source: str) -> str:
    signatures = source_artifact.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        raise ValueError(f"manifest source artifact is missing signatures: {source}")
    for signature in signatures:
        if not isinstance(signature, dict):
            continue
        if signature.get("type") != "openpgp-detached-ascii-armored":
            continue
        signature_uri = signature.get("uri")
        if isinstance(signature_uri, str) and signature_uri.strip():
            return signature_uri.strip()
    raise ValueError(f"manifest source artifact is missing an OpenPGP detached signature URI: {source}")


def _required_commit_sha256_style_digest(
    payload: dict[str, Any],
    field_name: str,
    *,
    source: str,
) -> str:
    value = _required_non_empty_string(payload, field_name, source=source).lower()
    if len(value) != 128 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"manifest source artifact sha512 must be a 128-character hex digest: {source}")
    return value


def _archive_prefix_from_source_artifact_filename(filename: str) -> str:
    if not filename.endswith(".tar.gz"):
        raise ValueError(
            "Phase 1a only supports staged source artifacts named as .tar.gz archives"
        )
    return f"{filename.removesuffix('.tar.gz')}/"


def _clone_source_repository(*, source_repository_url: str, work_dir: Path) -> Path:
    repository_path = work_dir / "source-repository"
    run_logged_command(
        ["git", "clone", "--quiet", source_repository_url, str(repository_path)],
        capture_output=False,
    )
    return repository_path


def _report_markdown(
    *,
    component_id: str,
    version: str,
    rc_tag: str,
    source_commit_sha: str,
    source_repository_url: str,
    manifest_url: str,
    keys_url: str,
    manifest_signature: SignatureVerification,
    source_artifact_filename: str,
    source_artifact_url: str,
    source_artifact_signature: SignatureVerification,
    actual_source_sha512: str,
    secondary_artifact_verifications: list[dict[str, Any]],
) -> str:
    lines = [
        "## Verify RC",
        "",
        "### Technical details",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Component | `{component_id}` |",
        f"| Version | `{version}` |",
        f"| RC tag | `{rc_tag}` |",
        f"| Source commit | `{source_commit_sha}` |",
        f"| Source repository URL | `{source_repository_url}` |",
        f"| Manifest URL | `{manifest_url}` |",
        f"| KEYS URL | `{keys_url}` |",
        "",
        "### Manifest verification",
        "",
        f"- Signature verified: `{manifest_signature.signer_fingerprint}`",
        f"- RC tag resolves to the declared source commit: `{rc_tag}`",
        "",
        "### Source artifact verification",
        "",
        f"- Source artifact: `{source_artifact_filename}`",
        f"- Source artifact URL: `{source_artifact_url}`",
        f"- SHA512: `{actual_source_sha512}`",
        f"- Signature verified: `{source_artifact_signature.signer_fingerprint}`",
        f"- Source artifact matches the declared source commit: `{source_commit_sha}`",
        "",
        "### Secondary artifact verification",
        "",
    ]
    if not secondary_artifact_verifications:
        lines.extend(
            [
                "- No secondary artifacts declared.",
                "",
            ]
        )
    else:
        for verification in secondary_artifact_verifications:
            kind = verification["kind"]
            lines.extend(
                [
                    f"#### `{verification['artifact_id']}`",
                    "",
                    f"- Kind: `{kind}`",
                ]
            )
            if kind in {"generic-file", "generic-file-with-openpgp"}:
                checksum_payload = verification["checksum"]
                lines.extend(
                    [
                        f"- File: `{verification['filename']}`",
                        f"- URL: `{verification['uri']}`",
                        f"- Checksum verified: `{checksum_payload['algorithm']}:{checksum_payload['value']}`",
                        f"- Checksum sidecar verified: `{checksum_payload['sidecar_verified']}`",
                    ]
                )
                signature_verifications = verification.get("signatures", [])
                if signature_verifications:
                    for signature_verification in signature_verifications:
                        lines.append(
                            f"- Signature verified: `{signature_verification['signer_fingerprint']}`"
                        )
                inventory_payload = verification.get("inventory")
                if isinstance(inventory_payload, dict):
                    lines.append(
                        f"- Inventory verified: `{inventory_payload['filename']}`"
                    )
            elif kind == "maven-repository":
                inventory_payload = verification["inventory"]
                live_repository = verification["live_repository"]
                lines.extend(
                    [
                        f"- Base URL: `{verification['base_url']}`",
                        f"- Inventory verified: `{inventory_payload['filename']}`",
                        f"- Live repository entry count: `{live_repository['entry_count']}`",
                        f"- Live repository matches signed inventory: `{live_repository['matches_signed_inventory']}`",
                    ]
                )
                signature_verifications = live_repository.get("signature_verifications", [])
                for signature_verification in signature_verifications:
                    lines.append(
                        f"- Signature verified: `{signature_verification['path']}` by `{signature_verification['signature']['signer_fingerprint']}`"
                    )
            lines.append("")
    lines.extend(
        [
            "### Outcome",
            "",
            "```text",
            "Verified manifest authenticity, explicit KEYS binding, rc_tag-to-source_commit binding, the staged source artifact bytes, and all supported secondary artifacts declared in the signed manifest.",
            "```",
            "",
        ]
    )
    return "\n".join(lines)
