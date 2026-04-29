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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from apache_buildish_release_tooling.release.git_repo import GitRepository
from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.process import run_logged_command
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import create_from_git, sha512

_GPG_ALGORITHM_NAMES = {
    "1": "rsa",
    "16": "elgamal",
    "17": "dsa",
    "18": "ecdh",
    "19": "ecdsa",
    "22": "ed25519",
}


@dataclass(frozen=True)
class SignatureVerification:
    """Structured details about one detached-signature verification."""

    signer_fingerprint: str
    signer_user_id: str | None
    trust_label: str | None
    key_algorithm: str | None
    key_size_bits: int | None


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
    """Verify the signed RC vote manifest plus the staged source artifact."""

    work_dir.mkdir(parents=True, exist_ok=True)
    _validate_fetch_uri(
        manifest_url,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose="RC vote manifest URL",
    )
    _validate_fetch_uri(
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

    manifest_sha512 = _verify_sha512_sidecar(
        manifest_path,
        manifest_sha512_path,
        purpose="RC vote manifest",
    )
    verifier = _GpgVerifier(work_dir / "gnupg", keys_path)
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

    _validate_fetch_uri(
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
    _validate_fetch_uri(
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
        _validate_fetch_uri(
            checksum_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="Source artifact checksum sidecar URL",
        )
        source_sha512_sidecar_path = work_dir / f"{source_artifact_filename}.sha512"
        source_sha512_sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
        _verify_sha512_sidecar(
            source_artifact_path,
            source_sha512_sidecar_path,
            purpose="source artifact",
        )
        source_sha512_sidecar_verified = True

    source_signature_uri = _source_signature_uri(source_artifact, source=manifest_url)
    _validate_fetch_uri(
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

    report_payload: dict[str, Any] = {
        "schema_version": "1",
        "report_type": "verify-rc-phase1a",
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
            "signature": _signature_payload(manifest_signature),
            "rc_tag_target_commit": rc_tag_target_commit,
            "rc_tag_matches_source_commit_sha": True,
        },
        "source_artifact_verification": {
            "filename": source_artifact_filename,
            "uri": source_artifact_url,
            "sha512": actual_source_sha512,
            "sha512_sidecar_verified": source_sha512_sidecar_verified,
            "signature": _signature_payload(source_artifact_signature),
            "rebuilt_sha512": rebuilt_source_sha512,
            "matches_source_commit_sha": True,
        },
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


class _GpgVerifier:
    """Small helper for detached-signature verification against one imported KEYS file."""

    def __init__(self, home_dir: Path, keys_path: Path) -> None:
        self.home_dir = home_dir
        self.home_dir.mkdir(parents=True, exist_ok=True)
        self.home_dir.chmod(0o700)
        run_logged_command(
            ["gpg", "--batch", "--quiet", "--import", str(keys_path)],
            env={"GNUPGHOME": str(self.home_dir)},
            capture_output=False,
        )

    def verify_detached(self, *, target_path: Path, signature_path: Path) -> SignatureVerification:
        completed = run_logged_command(
            [
                "gpg",
                "--batch",
                "--status-fd",
                "1",
                "--verify",
                str(signature_path),
                str(target_path),
            ],
            env={"GNUPGHOME": str(self.home_dir)},
        )
        return _signature_verification_from_status(
            completed.stdout,
            home_dir=self.home_dir,
        )


def _signature_verification_from_status(status_output: str, *, home_dir: Path) -> SignatureVerification:
    fingerprint: str | None = None
    user_id: str | None = None
    trust_label: str | None = None
    for line in status_output.splitlines():
        if line.startswith("[GNUPG:] VALIDSIG "):
            fields = line.split()
            if len(fields) > 2:
                fingerprint = fields[2]
        elif line.startswith("[GNUPG:] GOODSIG "):
            fields = line.split(maxsplit=3)
            if len(fields) > 3:
                user_id = fields[3]
        elif line.startswith("[GNUPG:] TRUST_"):
            trust_label = line.removeprefix("[GNUPG:] ").strip()
    if fingerprint is None:
        raise ValueError("gpg verification did not report a signer fingerprint")

    completed = run_logged_command(
        ["gpg", "--batch", "--with-colons", "--list-keys", fingerprint],
        env={"GNUPGHOME": str(home_dir)},
    )
    key_algorithm: str | None = None
    key_size_bits: int | None = None
    for line in completed.stdout.splitlines():
        parts = line.split(":")
        if parts and parts[0] == "pub":
            if len(parts) > 3 and parts[3]:
                key_algorithm = _GPG_ALGORITHM_NAMES.get(parts[3], parts[3])
            if len(parts) > 2 and parts[2].isdigit():
                key_size_bits = int(parts[2])
            break
    return SignatureVerification(
        signer_fingerprint=fingerprint,
        signer_user_id=user_id,
        trust_label=trust_label,
        key_algorithm=key_algorithm,
        key_size_bits=key_size_bits,
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


def _verify_sha512_sidecar(target_path: Path, sidecar_path: Path, *, purpose: str) -> str:
    actual_sha512 = sha512(target_path)
    sidecar_text = sidecar_path.read_text(encoding="utf-8")
    fields = sidecar_text.strip().split()
    if not fields or not fields[0]:
        raise ValueError(f"invalid .sha512 sidecar contents for {purpose}: {sidecar_path}")
    declared_sha512 = fields[0].strip().lower()
    if declared_sha512 != actual_sha512:
        raise ValueError(
            f"{purpose} .sha512 sidecar does not match the downloaded bytes: "
            f"{declared_sha512} != {actual_sha512}"
        )
    return actual_sha512


def _validate_fetch_uri(
    uri: str,
    *,
    allow_non_production_release_targets: bool,
    purpose: str,
) -> None:
    parsed = urlparse(uri)
    if parsed.scheme == "https":
        return
    if allow_non_production_release_targets and parsed.scheme in {"file", "http"}:
        return
    raise ValueError(
        f"{purpose} must use https; pass --allow-non-production-release-targets only for local file:// or http:// test inputs: {uri}"
    )


def _signature_payload(signature: SignatureVerification) -> dict[str, Any]:
    return asdict(signature)


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
) -> str:
    return "\n".join(
        [
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
            "### Outcome",
            "",
            "```text",
            "Verified manifest authenticity, explicit KEYS binding, rc_tag-to-source_commit binding, and the staged source artifact bytes.",
            "```",
            "",
        ]
    )
