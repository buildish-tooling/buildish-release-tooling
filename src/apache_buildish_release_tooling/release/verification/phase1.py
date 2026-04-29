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

from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.process import run_logged_command
from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import create_from_git, sha512
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    emit_detail,
    emit_failure,
    emit_info,
    emit_section,
    emit_success,
    emit_warning,
    signature_payload,
    signature_summary,
    validate_fetch_uri,
    verify_checksum_sidecar,
)
from apache_buildish_release_tooling.release.verification.secondary import (
    INVALID_SECONDARY_ARTIFACT_KIND,
    verify_secondary_artifacts,
)


@dataclass(frozen=True)
class VerificationFailure:
    """One collected verification failure surfaced in the final report."""

    scope: str
    subject: str
    message: str


@dataclass(frozen=True)
class VerifyRcPhase1Result:
    """Structured result for one Phase 1a RC verification run."""

    verdict: str
    component_id: str | None
    version: str | None
    rc_tag: str | None
    source_commit_sha: str | None
    source_repository_url: str | None
    manifest_url: str
    keys_url: str
    work_dir: Path
    failures: tuple[VerificationFailure, ...]
    report_payload: dict[str, Any]
    report_markdown: str


def verify_rc_phase1(
    *,
    manifest_url: str,
    keys_url: str,
    component_config: ComponentConfig | None,
    allow_non_production_release_targets: bool,
    work_dir: Path,
    progress_reporter: ProgressReporter,
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

    failures: list[VerificationFailure] = []
    component_id: str | None = None
    version: str | None = None
    rc_tag: str | None = None
    source_commit_sha: str | None = None
    source_repository_url: str | None = None
    manifest_sha512: str | None = None
    manifest_signature: SignatureVerification | None = None
    manifest_payload: dict[str, Any] | None = None
    verifier: GpgVerifier | None = None
    keys_url_matches_manifest = False
    keys_url_matches_component_config: bool | None = None
    rc_tag_target_commit: str | None = None
    repository_path: Path | None = None
    source_artifact_filename: str | None = None
    source_artifact_url: str | None = None
    actual_source_sha512: str | None = None
    source_sha512_sidecar_verified = False
    source_artifact_signature: SignatureVerification | None = None
    rebuilt_source_sha512: str | None = None
    source_artifact_matches_source_commit = False
    secondary_artifact_verifications: list[dict[str, Any]] = []

    emit_section(progress_reporter, "Vote Manifest")
    emit_info(progress_reporter, "Downloading signed RC vote manifest and sidecars")
    try:
        manifest_path = work_dir / "rc-vote-manifest.json"
        manifest_path.write_bytes(read_uri_bytes(manifest_url))
        manifest_sha512_path = work_dir / "rc-vote-manifest.json.sha512"
        manifest_sha512_path.write_bytes(read_uri_bytes(f"{manifest_url}.sha512"))
        manifest_signature_path = work_dir / "rc-vote-manifest.json.asc"
        manifest_signature_path.write_bytes(read_uri_bytes(f"{manifest_url}.asc"))
        keys_path = work_dir / "KEYS"
        keys_path.write_bytes(read_uri_bytes(keys_url))
        emit_success(progress_reporter, "Downloaded manifest, checksum sidecar, signature, and KEYS")
        manifest_sha512 = verify_checksum_sidecar(
            manifest_path,
            manifest_sha512_path,
            algorithm="sha512",
            purpose="RC vote manifest",
        )
        emit_success(progress_reporter, f"Verified manifest SHA512: {manifest_sha512}")
        verifier = GpgVerifier(work_dir / "gnupg", keys_path)
        manifest_signature = verifier.verify_detached(
            target_path=manifest_path,
            signature_path=manifest_signature_path,
        )
        emit_success(
            progress_reporter,
            f"Verified manifest signature: {signature_summary(manifest_signature)}",
        )
        manifest_payload = _rc_vote_manifest_payload(manifest_path)
        component_id = _required_non_empty_string(manifest_payload, "component_id", source=manifest_url)
        version = _required_non_empty_string(manifest_payload, "version", source=manifest_url)
        source_commit_sha = _required_commit_sha(manifest_payload, "source_commit_sha", source=manifest_url)
        rc_tag = _required_non_empty_string(manifest_payload, "rc_tag", source=manifest_url)
        source_repository_url = _source_repository_url(manifest_payload, source=manifest_url)
    except Exception as exc:
        _append_failure(
            failures,
            progress_reporter=progress_reporter,
            scope="vote-manifest",
            subject="manifest trust chain",
            message=str(exc),
        )
        return _phase1_result(
            manifest_url=manifest_url,
            keys_url=keys_url,
            work_dir=work_dir,
            failures=failures,
            component_id=component_id,
            version=version,
            rc_tag=rc_tag,
            source_commit_sha=source_commit_sha,
            source_repository_url=source_repository_url,
            manifest_sha512=manifest_sha512,
            manifest_signature=manifest_signature,
            keys_url_matches_manifest=keys_url_matches_manifest,
            keys_url_matches_component_config=keys_url_matches_component_config,
            rc_tag_target_commit=rc_tag_target_commit,
            source_artifact_filename=source_artifact_filename,
            source_artifact_url=source_artifact_url,
            actual_source_sha512=actual_source_sha512,
            source_sha512_sidecar_verified=source_sha512_sidecar_verified,
            source_artifact_signature=source_artifact_signature,
            rebuilt_source_sha512=rebuilt_source_sha512,
            source_artifact_matches_source_commit=source_artifact_matches_source_commit,
            secondary_artifact_verifications=secondary_artifact_verifications,
        )

    if (
        component_id is None
        or version is None
        or rc_tag is None
        or source_commit_sha is None
        or source_repository_url is None
        or manifest_signature is None
        or manifest_payload is None
        or verifier is None
    ):
        raise RuntimeError("verified manifest extraction produced incomplete state")

    emit_detail(progress_reporter, "Component", component_id)
    emit_detail(progress_reporter, "Version", version)
    emit_detail(progress_reporter, "RC tag", rc_tag)

    try:
        keys_url_matches_component_config = _cross_check_keys_url(
            manifest_payload=manifest_payload,
            keys_url=keys_url,
            component_config=component_config,
            source=manifest_url,
        )
        keys_url_matches_manifest = True
        emit_success(progress_reporter, "Cross-checked KEYS URL against the signed manifest")
        if keys_url_matches_component_config:
            emit_success(progress_reporter, "Cross-checked KEYS URL against component config")
        else:
            emit_warning(progress_reporter, "Component config not provided; skipped local KEYS URL cross-check")
    except Exception as exc:
        _append_failure(
            failures,
            progress_reporter=progress_reporter,
            scope="vote-manifest",
            subject="KEYS URL cross-check",
            message=str(exc),
        )

    emit_section(progress_reporter, "Source Artifact")
    emit_detail(progress_reporter, "Source repository", source_repository_url)
    emit_detail(progress_reporter, "Source commit", source_commit_sha)
    try:
        validate_fetch_uri(
            source_repository_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="Source repository URL",
        )
        emit_info(progress_reporter, "Cloning source repository")
        repository_path = _clone_source_repository(
            source_repository_url=source_repository_url,
            work_dir=work_dir,
        )
        emit_success(progress_reporter, "Cloned source repository")
    except Exception as exc:
        _append_failure(
            failures,
            progress_reporter=progress_reporter,
            scope="source-artifact",
            subject="source repository clone",
            message=str(exc),
        )

    if repository_path is not None:
        try:
            rc_tag_target_commit = _resolved_commit(repository_path, rc_tag)
            if rc_tag_target_commit != source_commit_sha:
                raise ValueError(
                    "manifest rc_tag does not resolve to the declared source_commit_sha: "
                    f"{rc_tag} -> {rc_tag_target_commit} != {source_commit_sha}"
                )
            emit_success(progress_reporter, f"Verified rc_tag binding: {rc_tag} -> {source_commit_sha}")
        except Exception as exc:
            _append_failure(
                failures,
                progress_reporter=progress_reporter,
                scope="source-artifact",
                subject="rc_tag binding",
                message=str(exc),
            )

    source_artifact: dict[str, Any] | None = None
    try:
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
        emit_detail(progress_reporter, "Artifact", source_artifact_filename)
        emit_detail(progress_reporter, "Artifact URL", source_artifact_url)
    except Exception as exc:
        _append_failure(
            failures,
            progress_reporter=progress_reporter,
            scope="source-artifact",
            subject="manifest source artifact entry",
            message=str(exc),
        )

    source_artifact_path: Path | None = None
    declared_source_sha512: str | None = None
    if source_artifact is not None and source_artifact_filename is not None and source_artifact_url is not None:
        try:
            emit_info(progress_reporter, "Downloading staged source artifact")
            downloaded_source_artifact_path = work_dir / source_artifact_filename
            downloaded_source_artifact_path.write_bytes(read_uri_bytes(source_artifact_url))
            source_artifact_path = downloaded_source_artifact_path
            emit_success(progress_reporter, "Downloaded staged source artifact")
            declared_source_sha512 = _required_sha512_from_source_artifact(source_artifact, source=manifest_url)
            actual_source_sha512 = sha512(source_artifact_path)
            if actual_source_sha512 != declared_source_sha512:
                raise ValueError(
                    "staged source artifact checksum does not match the signed manifest: "
                    f"{actual_source_sha512} != {declared_source_sha512}"
                )
            emit_success(progress_reporter, f"Verified staged source SHA512: {actual_source_sha512}")
        except Exception as exc:
            _append_failure(
                failures,
                progress_reporter=progress_reporter,
                scope="source-artifact",
                subject="staged source checksum",
                message=str(exc),
            )

    if source_artifact is not None and source_artifact_path is not None and source_artifact_filename is not None:
        checksum_uri = _checksum_uri_from_source_artifact(source_artifact)
        if checksum_uri is not None:
            try:
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
                emit_success(progress_reporter, "Verified source artifact SHA512 sidecar")
            except Exception as exc:
                _append_failure(
                    failures,
                    progress_reporter=progress_reporter,
                    scope="source-artifact",
                    subject="source artifact checksum sidecar",
                    message=str(exc),
                )
        else:
            emit_warning(progress_reporter, "No source artifact SHA512 sidecar URI declared in the manifest")

        try:
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
            emit_success(
                progress_reporter,
                f"Verified source artifact signature: {signature_summary(source_artifact_signature)}",
            )
        except Exception as exc:
            _append_failure(
                failures,
                progress_reporter=progress_reporter,
                scope="source-artifact",
                subject="source artifact signature",
                message=str(exc),
            )

    if (
        repository_path is not None
        and source_artifact_path is not None
        and source_artifact_filename is not None
    ):
        try:
            expected_prefix = _archive_prefix_from_source_artifact_filename(source_artifact_filename)
            rebuilt_source_artifact_path = work_dir / f"rebuilt-{source_artifact_filename}"
            emit_info(progress_reporter, "Rebuilding source artifact from declared source commit")
            create_from_git(
                repository_path,
                source_commit_sha,
                expected_prefix,
                rebuilt_source_artifact_path,
                log_commands=False,
            )
            rebuilt_source_sha512 = sha512(rebuilt_source_artifact_path)
            emit_success(progress_reporter, f"Rebuilt source artifact SHA512: {rebuilt_source_sha512}")
            source_artifact_matches_source_commit = (
                rebuilt_source_artifact_path.read_bytes() == source_artifact_path.read_bytes()
            )
            if not source_artifact_matches_source_commit:
                raise ValueError(
                    "staged source artifact does not match the declared source_commit_sha"
                )
            emit_success(
                progress_reporter,
                "Verified staged source artifact matches the declared source commit",
            )
        except Exception as exc:
            _append_failure(
                failures,
                progress_reporter=progress_reporter,
                scope="source-artifact",
                subject="source artifact reproducibility",
                message=str(exc),
            )

    try:
        secondary_artifact_verifications = verify_secondary_artifacts(
            manifest_payload,
            manifest_url=manifest_url,
            work_dir=work_dir / "secondary-artifacts",
            verifier=verifier,
            allow_non_production_release_targets=allow_non_production_release_targets,
            progress_reporter=progress_reporter,
        )
        for verification in secondary_artifact_verifications:
            for issue in verification.get("issues", []):
                failures.append(
                    VerificationFailure(
                        scope="secondary-artifact",
                        subject=str(verification["artifact_id"]),
                        message=str(issue),
                    )
                )
    except Exception as exc:
        _append_failure(
            failures,
            progress_reporter=progress_reporter,
            scope="secondary-artifact",
            subject="secondary artifacts manifest",
            message=str(exc),
        )
        secondary_artifact_verifications = []

    return _phase1_result(
        manifest_url=manifest_url,
        keys_url=keys_url,
        work_dir=work_dir,
        failures=failures,
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_repository_url=source_repository_url,
        manifest_sha512=manifest_sha512,
        manifest_signature=manifest_signature,
        keys_url_matches_manifest=keys_url_matches_manifest,
        keys_url_matches_component_config=keys_url_matches_component_config,
        rc_tag_target_commit=rc_tag_target_commit,
        source_artifact_filename=source_artifact_filename,
        source_artifact_url=source_artifact_url,
        actual_source_sha512=actual_source_sha512,
        source_sha512_sidecar_verified=source_sha512_sidecar_verified,
        source_artifact_signature=source_artifact_signature,
        rebuilt_source_sha512=rebuilt_source_sha512,
        source_artifact_matches_source_commit=source_artifact_matches_source_commit,
        secondary_artifact_verifications=secondary_artifact_verifications,
    )


def _append_failure(
    failures: list[VerificationFailure],
    *,
    progress_reporter: ProgressReporter,
    scope: str,
    subject: str,
    message: str,
) -> None:
    failures.append(
        VerificationFailure(
            scope=scope,
            subject=subject,
            message=message,
        )
    )
    emit_failure(progress_reporter, message)


def _failure_messages(
    failures: list[VerificationFailure],
    *,
    scope: str,
) -> list[str]:
    return [failure.message for failure in failures if failure.scope == scope]


def _phase1_result(
    *,
    manifest_url: str,
    keys_url: str,
    work_dir: Path,
    failures: list[VerificationFailure],
    component_id: str | None,
    version: str | None,
    rc_tag: str | None,
    source_commit_sha: str | None,
    source_repository_url: str | None,
    manifest_sha512: str | None,
    manifest_signature: SignatureVerification | None,
    keys_url_matches_manifest: bool,
    keys_url_matches_component_config: bool | None,
    rc_tag_target_commit: str | None,
    source_artifact_filename: str | None,
    source_artifact_url: str | None,
    actual_source_sha512: str | None,
    source_sha512_sidecar_verified: bool,
    source_artifact_signature: SignatureVerification | None,
    rebuilt_source_sha512: str | None,
    source_artifact_matches_source_commit: bool,
    secondary_artifact_verifications: list[dict[str, Any]],
) -> VerifyRcPhase1Result:
    verdict = "verified" if not failures else "failed"
    manifest_issues = _failure_messages(failures, scope="vote-manifest")
    source_artifact_issues = _failure_messages(failures, scope="source-artifact")
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
        "verdict": verdict,
        "work_dir": str(work_dir),
        "failures": [
            {
                "scope": failure.scope,
                "subject": failure.subject,
                "message": failure.message,
            }
            for failure in failures
        ],
        "manifest_verification": {
            "verdict": "verified"
            if manifest_signature is not None and keys_url_matches_manifest
            else "failed",
            "sha512": manifest_sha512,
            "keys_url_matches_manifest": keys_url_matches_manifest,
            "keys_url_matches_component_config": keys_url_matches_component_config,
            "signature": (
                signature_payload(manifest_signature)
                if manifest_signature is not None
                else None
            ),
            "rc_tag_target_commit": rc_tag_target_commit,
            "rc_tag_matches_source_commit_sha": (
                rc_tag_target_commit is not None
                and source_commit_sha is not None
                and rc_tag_target_commit == source_commit_sha
            ),
            "issues": manifest_issues,
        },
        "source_artifact_verification": {
            "verdict": "verified"
            if (
                source_artifact_filename is not None
                and source_artifact_url is not None
                and actual_source_sha512 is not None
                and source_artifact_signature is not None
                and source_artifact_matches_source_commit
            )
            else "failed",
            "filename": source_artifact_filename,
            "uri": source_artifact_url,
            "sha512": actual_source_sha512,
            "sha512_sidecar_verified": source_sha512_sidecar_verified,
            "signature": (
                signature_payload(source_artifact_signature)
                if source_artifact_signature is not None
                else None
            ),
            "rebuilt_sha512": rebuilt_source_sha512,
            "matches_source_commit_sha": source_artifact_matches_source_commit,
            "issues": source_artifact_issues,
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
        verdict=verdict,
        failures=failures,
        manifest_signature=manifest_signature,
        source_artifact_filename=source_artifact_filename,
        source_artifact_url=source_artifact_url,
        source_artifact_signature=source_artifact_signature,
        actual_source_sha512=actual_source_sha512,
        manifest_issues=manifest_issues,
        source_artifact_issues=source_artifact_issues,
        secondary_artifact_verifications=secondary_artifact_verifications,
    )
    return VerifyRcPhase1Result(
        verdict=verdict,
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_repository_url=source_repository_url,
        manifest_url=manifest_url,
        keys_url=keys_url,
        work_dir=work_dir,
        failures=tuple(failures),
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
        log_command=False,
    )
    return repository_path


def _resolved_commit(repository_path: Path, ref: str) -> str:
    completed = run_logged_command(
        [
            "git",
            "-C",
            str(repository_path),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{ref}^{{commit}}",
        ],
        log_command=False,
    )
    resolved = completed.stdout.strip()
    if not resolved:
        raise ValueError(f"unable to resolve Git ref: {ref}")
    return resolved


def _report_markdown(
    *,
    component_id: str | None,
    version: str | None,
    rc_tag: str | None,
    source_commit_sha: str | None,
    source_repository_url: str | None,
    manifest_url: str,
    keys_url: str,
    verdict: str,
    failures: list[VerificationFailure],
    manifest_signature: SignatureVerification | None,
    source_artifact_filename: str | None,
    source_artifact_url: str | None,
    source_artifact_signature: SignatureVerification | None,
    actual_source_sha512: str | None,
    manifest_issues: list[str],
    source_artifact_issues: list[str],
    secondary_artifact_verifications: list[dict[str, Any]],
) -> str:
    lines = [
        "## Verify RC",
        "",
        "### Technical details",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Component | `{_md_value(component_id)}` |",
        f"| Version | `{_md_value(version)}` |",
        f"| RC tag | `{_md_value(rc_tag)}` |",
        f"| Source commit | `{_md_value(source_commit_sha)}` |",
        f"| Source repository URL | `{_md_value(source_repository_url)}` |",
        f"| Manifest URL | `{manifest_url}` |",
        f"| KEYS URL | `{keys_url}` |",
        "",
        "### Manifest verification",
        "",
        (
            f"- ✓ Signature verified: `{manifest_signature.signer_fingerprint}`"
            if manifest_signature is not None
            else "- ✗ Signature verification did not complete."
        ),
        (
            f"- ✓ RC tag resolved from the signed manifest: `{rc_tag}`"
            if rc_tag is not None
            else "- ✗ RC tag could not be read from the signed manifest."
        ),
    ]
    for issue in manifest_issues:
        lines.append(f"- ✗ {issue}")
    lines.extend(
        [
            "",
            "### Source artifact verification",
            "",
            f"- Source artifact: `{_md_value(source_artifact_filename)}`",
            f"- Source artifact URL: `{_md_value(source_artifact_url)}`",
            f"- SHA512: `{_md_value(actual_source_sha512)}`",
            (
                f"- ✓ Signature verified: `{source_artifact_signature.signer_fingerprint}`"
                if source_artifact_signature is not None
                else "- ✗ Source artifact signature verification did not complete."
            ),
            (
                f"- ✓ Declared source commit: `{source_commit_sha}`"
                if source_commit_sha is not None
                else "- ✗ Source commit could not be read from the signed manifest."
            ),
        ]
    )
    for issue in source_artifact_issues:
        lines.append(f"- ✗ {issue}")
    lines.extend(
        [
            "",
            "### Secondary artifact verification",
            "",
        ]
    )
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
                    ]
                )
                if checksum_payload.get("algorithm") and checksum_payload.get("value"):
                    lines.append(
                        f"- Checksum observed: `{checksum_payload['algorithm']}:{checksum_payload['value']}`"
                    )
                lines.append(
                    f"- Checksum matched signed manifest: `{checksum_payload.get('matches_manifest')}`"
                )
                lines.append(
                    f"- Checksum sidecar verified: `{checksum_payload['sidecar_verified']}`"
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
                        f"- Inventory verified: `{inventory_payload['filename'] if isinstance(inventory_payload, dict) else 'n/a'}`",
                        f"- Live repository entry count: `{live_repository['entry_count']}`",
                        f"- Live repository matches signed inventory: `{live_repository['matches_signed_inventory']}`",
                    ]
                )
                signature_verifications = live_repository.get("signature_verifications", [])
                for signature_verification in signature_verifications:
                    lines.append(
                        f"- Signature verified: `{signature_verification['path']}` by `{signature_verification['signature']['signer_fingerprint']}`"
                    )
            elif kind == "python-distribution":
                checksum_payload = verification["checksum"]
                index_resolution = verification["index_resolution"]
                lines.extend(
                    [
                        f"- File: `{verification['filename']}`",
                        f"- URL: `{verification['uri']}`",
                        f"- Project: `{verification['project_name']}` `{verification['version']}`",
                    ]
                )
                if checksum_payload.get("algorithm") and checksum_payload.get("value"):
                    lines.append(
                        f"- Checksum observed: `{checksum_payload['algorithm']}:{checksum_payload['value']}`"
                    )
                lines.extend(
                    [
                        f"- Checksum matched signed manifest: `{checksum_payload.get('matches_manifest')}`",
                        f"- Checksum sidecar verified: `{checksum_payload['sidecar_verified']}`",
                        f"- Simple index verified: `{index_resolution['project_index_url']}`",
                        f"- Simple index hash matched: `{index_resolution['sha256_matches_index']}`",
                    ]
                )
            elif kind == "oci-image":
                inspection = verification["inspection"]
                lines.extend(
                    [
                        f"- Image: `{inspection['image_ref']}`",
                        f"- Digest verified: `{verification['digest']}`",
                        f"- Platform digests matched: `{inspection['platform_digests_match']}`",
                    ]
                )
            elif kind == "npm-package":
                checksum_payload = verification["checksum"]
                registry_resolution = verification["registry_resolution"]
                lines.extend(
                    [
                        f"- Package: `{verification['package_name']}` `{verification['version']}`",
                        f"- Tarball: `{verification['uri']}`",
                        f"- Integrity verified: `{verification['integrity']['value']}`",
                        f"- Integrity matched downloaded bytes: `{verification['integrity']['matches_downloaded_bytes']}`",
                        f"- Integrity matched signed manifest checksum: `{verification['integrity']['matches_manifest_checksum']}`",
                    ]
                )
                if checksum_payload.get("algorithm") and checksum_payload.get("value"):
                    lines.append(
                        f"- Checksum observed: `{checksum_payload['algorithm']}:{checksum_payload['value']}`"
                    )
                lines.extend(
                    [
                        f"- Checksum matched signed manifest: `{checksum_payload.get('matches_manifest')}`",
                        f"- Registry metadata verified: `{registry_resolution['metadata_url']}`",
                        f"- Registry tarball matched: `{registry_resolution['tarball_url_matches_manifest']}`",
                        f"- Registry integrity matched: `{registry_resolution['integrity_matches_manifest']}`",
                    ]
                )
            elif kind == INVALID_SECONDARY_ARTIFACT_KIND:
                declared_kind = verification.get("declared_kind")
                lines.append(f"- Declared kind: `{_md_value(declared_kind if isinstance(declared_kind, str) else None)}`")
            else:
                raise ValueError(
                    "unsupported secondary artifact kind for markdown reporting: "
                    f"{verification['artifact_id']} ({kind})"
                )
            for issue in verification.get("issues", []):
                lines.append(f"- ✗ {issue}")
            lines.append("")
    lines.extend(
        [
            "### Outcome",
            "",
        ]
    )
    if verdict == "verified":
        lines.extend(
            [
                "```text",
                "Verified manifest authenticity, explicit KEYS binding, rc_tag-to-source_commit binding, the staged source artifact bytes, and all supported secondary artifacts declared in the signed manifest.",
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- ✗ Verification failed with `{len(failures)}` issue(s).",
            ]
        )
        for failure in failures:
            lines.append(
                f"- `{failure.scope}` / `{failure.subject}`: {failure.message}"
            )
        lines.append("")
    return "\n".join(lines)


def _md_value(value: str | None) -> str:
    return value if value is not None else "n/a"
