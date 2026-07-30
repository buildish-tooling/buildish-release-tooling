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

"""Phase 1a verifier helpers for manifest and source-artifact validation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    RcVoteManifestReadV1,
    SourceArtifactContract,
)
from buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from buildish_release_tooling.release.path_validation import validate_simple_filename
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.process import run_logged_command
from buildish_release_tooling.release.rc_vote_manifest import (
    DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
    DEFAULT_KEYS_MAX_BYTES,
    DEFAULT_MANIFEST_MAX_BYTES,
    DEFAULT_SIGNATURE_MAX_BYTES,
    download_uri_to_path,
)
from buildish_release_tooling.release.source_artifact import create_from_git, sha512
from buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    SignatureVerification,
    emit_detail,
    emit_failure,
    emit_info,
    emit_section,
    emit_success,
    emit_warning,
    validate_fetch_uri,
    verify_checksum_sidecar,
    signature_summary,
)
from buildish_release_tooling.release.verification import phase1_reporting
from buildish_release_tooling.release.verification.phase1_reporting import (
    VerificationFailure,
    VerifyRcPhase1Result,
    _phase1_result,
    _source_artifact_reproducibility_payload,
)
from buildish_release_tooling.release.verification.secondary import (
    verify_secondary_artifacts,
)
from buildish_release_tooling.release.verification.rebuild import (
    ReproducibilityModeDecision,
    decide_reproducibility_mode,
    ensure_detached_source_checkout,
)
from buildish_release_tooling.shared.io import files_equal
from buildish_release_tooling.shared.parsing import read_pydantic_json_file_bounded

_report_markdown = phase1_reporting._report_markdown


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
    source_artifact_reproducibility: ArtifactReproducibilityReport | None = None
    secondary_artifact_verifications: list[AnySecondaryArtifactVerification] = []
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
        download_uri_to_path(manifest_url, manifest_path, max_bytes=DEFAULT_MANIFEST_MAX_BYTES)
        manifest_sha512_path = work_dir / "rc-vote-manifest.json.sha512"
        download_uri_to_path(
            f"{manifest_url}.sha512",
            manifest_sha512_path,
            max_bytes=DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
        )
        manifest_signature_path = work_dir / "rc-vote-manifest.json.asc"
        download_uri_to_path(
            f"{manifest_url}.asc",
            manifest_signature_path,
            max_bytes=DEFAULT_SIGNATURE_MAX_BYTES,
        )
        keys_path = work_dir / "KEYS"
        download_uri_to_path(keys_url, keys_path, max_bytes=DEFAULT_KEYS_MAX_BYTES)
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
        source_artifact_filename = validate_simple_filename(
            source_artifact.filename,
            field_name="source artifact filename",
        )
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
            download_uri_to_path(source_artifact_url, downloaded_source_artifact_path)
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
                download_uri_to_path(
                    checksum_uri,
                    source_sha512_sidecar_path,
                    max_bytes=DEFAULT_CHECKSUM_SIDECAR_MAX_BYTES,
                )
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
            download_uri_to_path(
                source_signature_uri,
                source_signature_path,
                max_bytes=DEFAULT_SIGNATURE_MAX_BYTES,
            )
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
            source_artifact_matches_source_commit = files_equal(
                rebuilt_source_artifact_path,
                source_artifact_path,
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
            getattr(verification, "reproducibility", None) is not None
            for verification in secondary_artifact_verifications
        )
        for verification in secondary_artifact_verifications:
            for issue in verification.issues:
                failures.append(
                    VerificationFailure(
                        scope="secondary-artifact",
                        subject=str(verification.artifact_id),
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

def _rc_vote_manifest_payload(manifest_path: Path) -> RcVoteManifestReadV1:
    try:
        return read_pydantic_json_file_bounded(
            RcVoteManifestReadV1,
            manifest_path,
            max_bytes=DEFAULT_MANIFEST_MAX_BYTES,
        )
    except (ValidationError, ValueError) as exc:
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
