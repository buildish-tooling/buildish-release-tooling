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

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from apache_buildish_release_tooling.release.contracts import (
    RcVoteManifestReadV1,
    SecondaryArtifactVerificationAdapter,
    SourceArtifactContract,
    VerifyRcReportV1,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
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
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    retain_source_artifact_evidence_file,
    write_source_artifact_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    build_shallow_archive_analysis,
)
from apache_buildish_release_tooling.release.verification.secondary import (
    INVALID_SECONDARY_ARTIFACT_KIND,
    verify_secondary_artifacts,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ReproducibilityModeDecision,
    decide_reproducibility_mode,
    ensure_detached_source_checkout,
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
    source_date_epoch: int | None
    source_repository_url: str | None
    manifest_url: str
    keys_url: str
    work_dir: Path
    failures: tuple[VerificationFailure, ...]
    report_payload: VerifyRcReportV1
    report_markdown: str


def verify_rc_phase1(
    *,
    manifest_url: str,
    keys_url: str,
    component_config: ComponentConfig | None,
    allow_non_production_release_targets: bool,
    work_dir: Path,
    progress_reporter: ProgressReporter,
    requested_mode: Literal["auto", "integrity-only", "full"],
    interactive_input_enabled: bool,
    confirm_candidate_code_execution: Callable[[], bool],
    inspection_bundle_path: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
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
    source_date_epoch: int | None = None
    source_repository_url: str | None = None
    manifest_sha512: str | None = None
    manifest_signature: SignatureVerification | None = None
    manifest_payload: RcVoteManifestReadV1 | None = None
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
    rebuilt_source_artifact_path: Path | None = None
    source_artifact_reproducibility: dict[str, Any] | None = None
    secondary_artifact_verifications: list[dict[str, Any]] = []
    reproducibility_decision = ReproducibilityModeDecision(
        requested_mode=requested_mode,
        effective_mode="integrity-only",
        prompt_used=False,
        prompt_confirmed=None,
        build_checks_allowed=False,
        build_checks_skipped_reason="build-based reproducibility checks were not evaluated",
    )
    build_checks_attempted = False

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
        component_id = manifest_payload.component_id
        version = manifest_payload.version
        source_commit_sha = manifest_payload.source_commit_sha
        source_date_epoch = manifest_payload.source_date_epoch
        rc_tag = manifest_payload.rc_tag
        if rc_tag is None:
            raise ValueError(f"manifest field rc_tag must be a non-empty string: {manifest_url}")
        source_repository_url = manifest_payload.source_repository_url
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
            source_date_epoch=source_date_epoch,
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
            source_artifact_reproducibility=source_artifact_reproducibility,
            secondary_artifact_verifications=secondary_artifact_verifications,
            reproducibility_decision=reproducibility_decision,
            build_checks_attempted=build_checks_attempted,
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
    if source_date_epoch is not None:
        emit_detail(progress_reporter, "SOURCE_DATE_EPOCH", str(source_date_epoch))

    try:
        keys_url_matches_component_config = _cross_check_keys_url(
            manifest_payload=manifest_payload,
            keys_url=keys_url,
            component_config=component_config,
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

    source_artifact: SourceArtifactContract | None = None
    try:
        source_artifact = _source_artifact_entry(manifest_payload, source=manifest_url)
        if source_artifact.git_commit_sha != source_commit_sha:
            raise ValueError(
                "manifest source artifact git_commit_sha does not match source_commit_sha"
            )
        source_artifact_url = source_artifact.uri
        validate_fetch_uri(
            source_artifact_url,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose="Source artifact URL",
        )
        source_artifact_filename = source_artifact.filename
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

    source_artifact_reproducibility = _source_artifact_reproducibility_payload(
        source_artifact=source_artifact,
        source_artifact_path=source_artifact_path,
        rebuilt_source_artifact_path=rebuilt_source_artifact_path,
        rebuilt_source_sha512=rebuilt_source_sha512,
        source_artifact_matches_source_commit=source_artifact_matches_source_commit,
        failures=failures,
        inspection_bundle_root=inspection_bundle_path,
    )

    has_build_candidates = manifest_payload is not None and _has_build_reproducibility_candidates(
        manifest_payload
    )
    reproducibility_decision = decide_reproducibility_mode(
        requested_mode=requested_mode,
        has_build_candidates=has_build_candidates,
        is_interactive=interactive_input_enabled,
        confirm_callback=confirm_candidate_code_execution,
    )
    emit_section(progress_reporter, "Local Reproducibility")
    emit_detail(progress_reporter, "Requested mode", reproducibility_decision.requested_mode)
    emit_detail(progress_reporter, "Effective mode", reproducibility_decision.effective_mode)
    if reproducibility_decision.prompt_used:
        emit_detail(
            progress_reporter,
            "Prompt confirmed",
            str(bool(reproducibility_decision.prompt_confirmed)),
        )
    if reproducibility_decision.build_checks_skipped_reason is not None:
        emit_info(progress_reporter, reproducibility_decision.build_checks_skipped_reason)
    elif reproducibility_decision.build_checks_allowed:
        emit_info(progress_reporter, "Build-based reproducibility checks enabled via host-direct executor")
    if (
        reproducibility_decision.build_checks_allowed
        and repository_path is not None
        and source_commit_sha is not None
    ):
        try:
            ensure_detached_source_checkout(repository_path, source_commit_sha)
            emit_success(progress_reporter, f"Checked out verified source tree at {source_commit_sha}")
        except Exception as exc:
            _append_failure(
                failures,
                progress_reporter=progress_reporter,
                scope="reproducibility",
                subject="source checkout",
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
            component_config=component_config,
            project_root=repository_path,
            source_date_epoch=source_date_epoch,
            build_checks_allowed=reproducibility_decision.build_checks_allowed,
            inspection_bundle_root=inspection_bundle_path,
            profile_overrides=profile_overrides,
        )
        build_checks_attempted = any(
            verification.get("reproducibility") is not None
            for verification in secondary_artifact_verifications
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
        source_date_epoch=source_date_epoch,
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
        source_artifact_reproducibility=source_artifact_reproducibility,
        secondary_artifact_verifications=secondary_artifact_verifications,
        reproducibility_decision=reproducibility_decision,
        build_checks_attempted=build_checks_attempted,
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
    source_date_epoch: int | None,
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
    source_artifact_reproducibility: dict[str, Any] | None,
    secondary_artifact_verifications: list[dict[str, Any]],
    reproducibility_decision: ReproducibilityModeDecision,
    build_checks_attempted: bool,
) -> VerifyRcPhase1Result:
    verdict = "verified" if not failures else "failed"
    manifest_issues = _failure_messages(failures, scope="vote-manifest")
    source_artifact_issues = _failure_messages(failures, scope="source-artifact")
    validated_secondary_artifact_verifications = [
        SecondaryArtifactVerificationAdapter.validate_python(verification)
        for verification in secondary_artifact_verifications
    ]
    secondary_artifact_verification_payloads = [
        verification.model_dump(mode="json")
        for verification in validated_secondary_artifact_verifications
    ]
    report_payload = VerifyRcReportV1.model_validate(
        {
            "schema_version": "1",
            "report_type": "verify-rc",
            "component_id": component_id,
            "version": version,
            "rc_tag": rc_tag,
            "source_commit_sha": source_commit_sha,
            "source_date_epoch": source_date_epoch,
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
                "reproducibility": source_artifact_reproducibility,
                "issues": source_artifact_issues,
            },
            "reproducibility_execution": {
                "requested_mode": reproducibility_decision.requested_mode,
                "effective_mode": reproducibility_decision.effective_mode,
                "build_checks_attempted": build_checks_attempted,
                "execution_backend": "host-direct" if build_checks_attempted else "none",
                "inherits_host_home": True if build_checks_attempted else None,
                "prompt_used": reproducibility_decision.prompt_used,
                "prompt_confirmed": reproducibility_decision.prompt_confirmed,
                "skipped_reason": reproducibility_decision.build_checks_skipped_reason,
            },
            "secondary_artifact_verifications": secondary_artifact_verification_payloads,
        }
    )

    report_markdown = _report_markdown(
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_date_epoch=source_date_epoch,
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
        source_artifact_reproducibility=source_artifact_reproducibility,
        manifest_issues=manifest_issues,
        source_artifact_issues=source_artifact_issues,
        reproducibility_decision=reproducibility_decision,
        build_checks_attempted=build_checks_attempted,
        secondary_artifact_verifications=secondary_artifact_verification_payloads,
    )
    return VerifyRcPhase1Result(
        verdict=verdict,
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_date_epoch=source_date_epoch,
        source_repository_url=source_repository_url,
        manifest_url=manifest_url,
        keys_url=keys_url,
        work_dir=work_dir,
        failures=tuple(failures),
        report_payload=report_payload,
        report_markdown=report_markdown,
    )


def _rc_vote_manifest_payload(manifest_path: Path) -> RcVoteManifestReadV1:
    try:
        return RcVoteManifestReadV1.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise ValueError(f"RC vote manifest is invalid: {manifest_path}") from exc


def _cross_check_keys_url(
    *,
    manifest_payload: RcVoteManifestReadV1,
    keys_url: str,
    component_config: ComponentConfig | None,
) -> bool | None:
    manifest_keys_url = manifest_payload.trust_roots.asf_keys.uri
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


def _has_build_reproducibility_candidates(manifest_payload: RcVoteManifestReadV1) -> bool:
    for artifact in manifest_payload.vote_materials.secondary_artifacts:
        reproducibility = getattr(artifact, "reproducibility", None)
        if reproducibility is not None:
            return True
    return False


def _source_artifact_entry(
    manifest_payload: RcVoteManifestReadV1,
    *,
    source: str,
) -> SourceArtifactContract:
    source_artifacts = manifest_payload.vote_materials.source_artifacts
    if len(source_artifacts) != 1:
        raise ValueError(f"manifest must contain exactly one source artifact: {source}")
    return source_artifacts[0]


def _required_sha512_from_source_artifact(
    source_artifact: SourceArtifactContract,
    *,
    source: str,
) -> str:
    sha512_value = source_artifact.checksums.sha512.value
    if not sha512_value:
        raise ValueError(f"manifest source artifact is missing sha512: {source}")
    return sha512_value


def _checksum_uri_from_source_artifact(source_artifact: SourceArtifactContract) -> str | None:
    return source_artifact.checksums.sha512.uri


def _source_signature_uri(source_artifact: SourceArtifactContract, *, source: str) -> str:
    if not source_artifact.signatures:
        raise ValueError(f"manifest source artifact is missing signatures: {source}")
    return source_artifact.signatures[0].uri


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
    source_date_epoch: int | None,
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
    source_artifact_reproducibility: dict[str, Any] | None,
    manifest_issues: list[str],
    source_artifact_issues: list[str],
    reproducibility_decision: ReproducibilityModeDecision,
    build_checks_attempted: bool,
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
        f"| SOURCE_DATE_EPOCH | `{_md_value(str(source_date_epoch) if source_date_epoch is not None else None)}` |",
        f"| Source repository URL | `{_md_value(source_repository_url)}` |",
        f"| Manifest URL | `{manifest_url}` |",
        f"| KEYS URL | `{keys_url}` |",
        f"| Requested verify mode | `{reproducibility_decision.requested_mode}` |",
        f"| Effective verify mode | `{reproducibility_decision.effective_mode}` |",
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
    if isinstance(source_artifact_reproducibility, dict):
        _append_source_artifact_reproducibility_markdown(
            lines,
            reproducibility_payload=source_artifact_reproducibility,
        )
    for issue in source_artifact_issues:
        lines.append(f"- ✗ {issue}")
    lines.extend(
        [
            "",
            "### Build-based reproducibility",
            "",
            f"- Requested mode: `{reproducibility_decision.requested_mode}`",
            f"- Effective mode: `{reproducibility_decision.effective_mode}`",
            f"- Prompt used: `{reproducibility_decision.prompt_used}`",
            f"- Prompt confirmed: `{_md_value(str(reproducibility_decision.prompt_confirmed).lower() if reproducibility_decision.prompt_confirmed is not None else None)}`",
            f"- Build checks attempted: `{build_checks_attempted}`",
        ]
    )
    if reproducibility_decision.build_checks_skipped_reason is not None:
        lines.append(
            f"- Skipped reason: `{reproducibility_decision.build_checks_skipped_reason}`"
        )
    lines.append("")
    lines.extend(
        [
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
                reproducibility_payload = verification.get("reproducibility")
                if isinstance(reproducibility_payload, dict):
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=reproducibility_payload,
                        match_summary_label="Rebuilt bytes matched staged artifact",
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
                reproducibility_payload = verification.get("reproducibility")
                if isinstance(reproducibility_payload, dict):
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=reproducibility_payload,
                        match_summary_label="Rebuilt repository matched staged policy",
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
                reproducibility_payload = verification.get("reproducibility")
                if isinstance(reproducibility_payload, dict):
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=reproducibility_payload,
                        match_summary_label="Rebuilt bytes matched staged artifact",
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
                reproducibility_payload = verification.get("reproducibility")
                if isinstance(reproducibility_payload, dict):
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=reproducibility_payload,
                        match_summary_label="Rebuilt image matched staged digests",
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
                reproducibility_payload = verification.get("reproducibility")
                if isinstance(reproducibility_payload, dict):
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=reproducibility_payload,
                        match_summary_label="Rebuilt bytes matched staged artifact",
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


def _append_reproducibility_markdown(
    lines: list[str],
    *,
    reproducibility_payload: dict[str, Any],
    match_summary_label: str,
) -> None:
    override_payload = reproducibility_payload.get("override", {})
    recipe_source = (
        "local-override"
        if isinstance(override_payload, dict) and override_payload.get("applied")
        else "canonical-profile"
    )
    lines.extend(
        [
            f"- Reproducibility profile: `{reproducibility_payload['profile_id']}`",
            f"- Reproducibility verdict: `{reproducibility_payload['verdict']}`",
            f"- Reproducibility mode: `{reproducibility_payload['comparison_mode']}`",
            f"- Recipe source: `{recipe_source}`",
            f"- {match_summary_label}: `{reproducibility_payload['matches_remote_bytes']}`",
        ]
    )
    canonical_build = _nested_mapping(reproducibility_payload, "canonical_recipe", "build")
    effective_execution = _nested_mapping(reproducibility_payload, "effective_execution")
    effective_build = _nested_mapping(reproducibility_payload, "effective_execution", "build")
    override_build = _nested_mapping(reproducibility_payload, "override", "build")
    if effective_execution is not None and effective_execution.get("backend") is not None:
        lines.append(f"- Execution backend: `{effective_execution['backend']}`")
    if recipe_source == "local-override" and canonical_build is not None:
        canonical_command = canonical_build.get("command", [])
        if canonical_command:
            lines.append(
                "- Canonical build command: `"
                + " ".join(str(part) for part in canonical_command)
                + "`"
            )
    build_command = effective_build.get("command", []) if effective_build else []
    if build_command:
        lines.append("- Build command: `" + " ".join(str(part) for part in build_command) + "`")
    build_working_directory = effective_build.get("working_directory") if effective_build else None
    if build_working_directory:
        lines.append(f"- Build working directory: `{build_working_directory}`")
    injected_environment_keys = (
        effective_build.get("injected_environment_keys", []) if effective_build else []
    )
    if injected_environment_keys:
        lines.append(
            "- Injected environment keys: `"
            + ", ".join(str(key) for key in injected_environment_keys)
            + "`"
        )
    override_fields = _override_field_summary(override_build)
    if override_fields:
        lines.append(
            "- Override fields: `"
            + ", ".join(str(field) for field in override_fields)
            + "`"
        )
    if reproducibility_payload.get("failure_class") is not None:
        lines.append(
            f"- Reproducibility failure class: `{reproducibility_payload['failure_class']}`"
        )
    for output_path in (effective_build.get("output_paths", []) if effective_build else []):
        lines.append(f"- Rebuild output: `{output_path}`")
    for evidence_reference in reproducibility_payload.get("evidence", []):
        if not isinstance(evidence_reference, dict):
            continue
        if evidence_reference.get("label") and evidence_reference.get("path"):
            lines.append(
                f"- Reproducibility evidence `{evidence_reference['label']}`: `{evidence_reference['path']}`"
            )


def _append_source_artifact_reproducibility_markdown(
    lines: list[str],
    *,
    reproducibility_payload: dict[str, Any],
) -> None:
    lines.extend(
        [
            f"- Source reproducibility profile: `{reproducibility_payload['profile_id']}`",
            f"- Source reproducibility verdict: `{reproducibility_payload['verdict']}`",
            f"- Source reproducibility mode: `{reproducibility_payload['comparison_mode']}`",
            "- Source recipe source: `verifier-internal`",
            f"- Rebuilt bytes matched declared source commit: `{reproducibility_payload['matches_remote_bytes']}`",
        ]
    )
    effective_execution = _nested_mapping(reproducibility_payload, "effective_execution")
    effective_build = _nested_mapping(reproducibility_payload, "effective_execution", "build")
    if effective_execution is not None and effective_execution.get("backend") is not None:
        lines.append(f"- Source rebuild backend: `{effective_execution['backend']}`")
    build_command = effective_build.get("command", []) if effective_build else []
    if build_command:
        lines.append(
            "- Source rebuild command: `"
            + " ".join(str(part) for part in build_command)
            + "`"
        )
    build_working_directory = effective_build.get("working_directory") if effective_build else None
    if build_working_directory:
        lines.append(f"- Source rebuild working directory: `{build_working_directory}`")
    for output_path in (effective_build.get("output_paths", []) if effective_build else []):
        lines.append(f"- Source rebuild output: `{output_path}`")
    if reproducibility_payload.get("failure_class") is not None:
        lines.append(
            f"- Source reproducibility failure class: `{reproducibility_payload['failure_class']}`"
        )


def _md_value(value: str | None) -> str:
    return value if value is not None else "n/a"


def _nested_mapping(payload: dict[str, Any], *path: str) -> dict[str, Any] | None:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, dict) else None


def _source_artifact_reproducibility_payload(
    *,
    source_artifact: SourceArtifactContract | None,
    source_artifact_path: Path | None,
    rebuilt_source_artifact_path: Path | None,
    rebuilt_source_sha512: str | None,
    source_artifact_matches_source_commit: bool,
    failures: list[VerificationFailure],
    inspection_bundle_root: Path | None,
) -> dict[str, Any] | None:
    reproducibility_issues = [
        failure.message
        for failure in failures
        if failure.scope == "source-artifact" and failure.subject == "source artifact reproducibility"
    ]
    if source_artifact is None:
        return None
    if rebuilt_source_artifact_path is None and rebuilt_source_sha512 is None and not reproducibility_issues:
        return None
    profile_id = "source-artifact-from-git"
    failure_class: str | None = None
    if reproducibility_issues:
        failure_class = (
            "byte-mismatch"
            if rebuilt_source_sha512 is not None and not source_artifact_matches_source_commit
            else "build-failed"
        )
    effective_execution = None
    if rebuilt_source_artifact_path is not None:
        effective_execution = {
            "backend": "host-direct",
            "build": {
                "command": ["internal:create-from-git"],
                "working_directory": "source-repository",
                "output_paths": [rebuilt_source_artifact_path.name],
                "injected_environment_keys": [],
            },
        }
    evidence: list[dict[str, str]] = []
    if inspection_bundle_root is not None and source_artifact_path is not None:
        metadata_payload: dict[str, Any] = {
            "profile_id": profile_id,
            "comparison_mode": "exact-bytes",
            "failure_class": failure_class,
            "archive_analysis": (
                build_shallow_archive_analysis(
                    staged_path=source_artifact_path,
                    rebuilt_path=rebuilt_source_artifact_path,
                )
                if rebuilt_source_artifact_path is not None
                and source_artifact_path.exists()
                and rebuilt_source_artifact_path.exists()
                else None
            ),
            "staged_artifact": {
                "filename": source_artifact.filename,
                "sha512": sha512(source_artifact_path),
                "size_bytes": source_artifact_path.stat().st_size,
            },
            "matches_remote_bytes": (
                source_artifact_matches_source_commit if rebuilt_source_sha512 is not None else None
            ),
            "issues": reproducibility_issues,
        }
        if rebuilt_source_artifact_path is not None:
            metadata_payload["rebuilt_artifact"] = {
                "filename": rebuilt_source_artifact_path.name,
                "sha512": rebuilt_source_sha512,
                "size_bytes": rebuilt_source_artifact_path.stat().st_size,
            }
        metadata_path = write_source_artifact_reproducibility_metadata(
            inspection_bundle_root,
            payload=metadata_payload,
        )
        evidence.append({"label": "comparison-metadata", "path": metadata_path})
        if reproducibility_issues:
            evidence.append(
                {
                    "label": "staged-artifact",
                    "path": retain_source_artifact_evidence_file(
                        inspection_bundle_root,
                        label_directory="staged",
                        source_path=source_artifact_path,
                    ),
                }
            )
            if rebuilt_source_artifact_path is not None:
                evidence.append(
                    {
                        "label": "rebuilt-artifact",
                        "path": retain_source_artifact_evidence_file(
                            inspection_bundle_root,
                            label_directory="rebuilt",
                            source_path=rebuilt_source_artifact_path,
                        ),
                    }
                )
    return {
        "profile_id": profile_id,
        "verdict": "failed" if reproducibility_issues else "verified",
        "comparison_mode": "exact-bytes",
        "canonical_recipe": None,
        "effective_execution": effective_execution,
        "override": {"applied": False},
        "matches_remote_bytes": (
            source_artifact_matches_source_commit if rebuilt_source_sha512 is not None else None
        ),
        "failure_class": failure_class,
        "archive_analysis": (
            build_shallow_archive_analysis(
                staged_path=source_artifact_path,
                rebuilt_path=rebuilt_source_artifact_path,
            )
            if source_artifact_path is not None
            and rebuilt_source_artifact_path is not None
            and source_artifact_path.exists()
            and rebuilt_source_artifact_path.exists()
            else None
        ),
        "evidence": evidence,
        "issues": reproducibility_issues,
    }


def _override_field_summary(override_build: dict[str, Any] | None) -> list[str]:
    if override_build is None:
        return []
    fields: list[str] = []
    if override_build.get("command") is not None:
        fields.append("build.command")
    if override_build.get("working_directory") is not None:
        fields.append("build.working_directory")
    if override_build.get("output_globs") is not None:
        fields.append("build.output_globs")
    env_keys = override_build.get("env_keys")
    if isinstance(env_keys, list):
        fields.extend(f"build.env.{key}" for key in env_keys if isinstance(key, str))
    return fields
