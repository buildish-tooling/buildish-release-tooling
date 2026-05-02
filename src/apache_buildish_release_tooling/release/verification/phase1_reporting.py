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

"""Phase 1a report assembly and source reproducibility helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityBuildOverrideReport,
    ArtifactReproducibilityEffectiveBuildExecutionReport,
    ArtifactReproducibilityEffectiveExecutionReport,
    ArtifactReproducibilityOverrideReport,
    ArtifactReproducibilityReport,
    GenericFileVerificationReport,
    InspectionEvidenceReference,
    InvalidSecondaryArtifactVerificationReport,
    ManifestVerificationSection,
    MavenRepositoryVerificationReport,
    NpmPackageVerificationReport,
    OciImageVerificationReport,
    PythonDistributionVerificationReport,
    ReproducibilityExecutionSection,
    RetainedArtifactSnapshot,
    SourceArtifactContract,
    SourceArtifactVerificationSection,
    VerificationFailurePayload,
)
from apache_buildish_release_tooling.release.source_artifact import sha512
from apache_buildish_release_tooling.release.verification.common import (
    SignatureVerification,
    signature_payload,
)
from apache_buildish_release_tooling.release.verification.inspection.archive_shallow import (
    build_shallow_archive_analysis,
)
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    retain_source_artifact_evidence_file,
    write_source_artifact_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ReproducibilityModeDecision,
)
from apache_buildish_release_tooling.release.verification.schemas import (
    SourceArtifactReproducibilityMetadata,
    VerifyRcReportV1,
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
    source_artifact_reproducibility: ArtifactReproducibilityReport | None,
    secondary_artifact_verifications: list[AnySecondaryArtifactVerification],
    reproducibility_decision: ReproducibilityModeDecision,
    build_checks_attempted: bool,
) -> VerifyRcPhase1Result:
    verdict: Literal["verified", "failed"] = "verified" if not failures else "failed"
    manifest_issues = _failure_messages(failures, scope="vote-manifest")
    source_artifact_issues = _failure_messages(failures, scope="source-artifact")
    report_payload = VerifyRcReportV1(
        component_id=component_id,
        version=version,
        rc_tag=rc_tag,
        source_commit_sha=source_commit_sha,
        source_date_epoch=source_date_epoch,
        source_repository_url=source_repository_url,
        manifest_url=manifest_url,
        keys_url=keys_url,
        verdict=verdict,
        work_dir=str(work_dir),
        failures=[
            VerificationFailurePayload(
                scope=failure.scope,
                subject=failure.subject,
                message=failure.message,
            )
            for failure in failures
        ],
        manifest_verification=ManifestVerificationSection(
            verdict="verified"
            if manifest_signature is not None and keys_url_matches_manifest
            else "failed",
            sha512=manifest_sha512,
            keys_url_matches_manifest=keys_url_matches_manifest,
            keys_url_matches_component_config=keys_url_matches_component_config,
            signature=signature_payload(manifest_signature) if manifest_signature is not None else None,
            rc_tag_target_commit=rc_tag_target_commit,
            rc_tag_matches_source_commit_sha=(
                rc_tag_target_commit is not None
                and source_commit_sha is not None
                and rc_tag_target_commit == source_commit_sha
            ),
            issues=manifest_issues,
        ),
        source_artifact_verification=SourceArtifactVerificationSection(
            verdict="verified"
            if (
                source_artifact_filename is not None
                and source_artifact_url is not None
                and actual_source_sha512 is not None
                and source_artifact_signature is not None
                and source_artifact_matches_source_commit
            )
            else "failed",
            filename=source_artifact_filename,
            uri=source_artifact_url,
            sha512=actual_source_sha512,
            sha512_sidecar_verified=source_sha512_sidecar_verified,
            signature=(
                signature_payload(source_artifact_signature)
                if source_artifact_signature is not None
                else None
            ),
            rebuilt_sha512=rebuilt_source_sha512,
            matches_source_commit_sha=source_artifact_matches_source_commit,
            reproducibility=source_artifact_reproducibility,
            issues=source_artifact_issues,
        ),
        reproducibility_execution=ReproducibilityExecutionSection(
            requested_mode=reproducibility_decision.requested_mode,
            effective_mode=reproducibility_decision.effective_mode,
            build_checks_attempted=build_checks_attempted,
            execution_backend="host-direct" if build_checks_attempted else "none",
            inherits_host_home=True if build_checks_attempted else None,
            prompt_used=reproducibility_decision.prompt_used,
            prompt_confirmed=reproducibility_decision.prompt_confirmed,
            skipped_reason=reproducibility_decision.build_checks_skipped_reason,
        ),
        secondary_artifact_verifications=secondary_artifact_verifications,
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
        source_artifact_reproducibility=report_payload.source_artifact_verification.reproducibility,
        manifest_issues=manifest_issues,
        source_artifact_issues=source_artifact_issues,
        reproducibility_decision=reproducibility_decision,
        build_checks_attempted=build_checks_attempted,
        secondary_artifact_verifications=report_payload.secondary_artifact_verifications,
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
    source_artifact_reproducibility: ArtifactReproducibilityReport | None,
    manifest_issues: list[str],
    source_artifact_issues: list[str],
    reproducibility_decision: ReproducibilityModeDecision,
    build_checks_attempted: bool,
    secondary_artifact_verifications: Sequence[
        AnySecondaryArtifactVerification | dict[str, object]
    ],
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
    if source_artifact_reproducibility is not None:
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
            if isinstance(verification, dict):
                raw_artifact_id = verification.get("artifact_id")
                artifact_id = _md_value(raw_artifact_id if isinstance(raw_artifact_id, str) else None)
                raw_kind = verification.get("kind")
                kind = _md_value(raw_kind if isinstance(raw_kind, str) else None)
                raise ValueError(
                    "unsupported secondary artifact kind for markdown reporting: "
                    f"{artifact_id} ({kind})"
                )
            kind = verification.kind
            lines.extend(
                [
                    f"#### `{verification.artifact_id}`",
                    "",
                    f"- Kind: `{kind}`",
                ]
            )
            if isinstance(verification, GenericFileVerificationReport):
                checksum_payload = verification.checksum
                lines.extend(
                    [
                        f"- File: `{verification.filename}`",
                        f"- URL: `{verification.uri}`",
                    ]
                )
                if checksum_payload.algorithm and checksum_payload.value:
                    lines.append(
                        f"- Checksum observed: `{checksum_payload.algorithm}:{checksum_payload.value}`"
                    )
                lines.append(
                    f"- Checksum matched signed manifest: `{checksum_payload.matches_manifest}`"
                )
                lines.append(
                    f"- Checksum sidecar verified: `{checksum_payload.sidecar_verified}`"
                )
                for signature_verification in verification.signatures:
                    lines.append(
                        f"- Signature verified: `{signature_verification.signer_fingerprint}`"
                    )
                if verification.inventory is not None:
                    lines.append(
                        f"- Inventory verified: `{verification.inventory.filename}`"
                    )
                if verification.reproducibility is not None:
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=verification.reproducibility,
                        match_summary_label="Rebuilt bytes matched staged artifact",
                    )
            elif isinstance(verification, MavenRepositoryVerificationReport):
                live_repository = verification.live_repository
                lines.extend(
                    [
                        f"- Base URL: `{verification.base_url}`",
                        f"- Inventory verified: `{verification.inventory.filename if verification.inventory is not None else 'n/a'}`",
                        f"- Live repository entry count: `{live_repository.entry_count}`",
                        f"- Live repository matches signed inventory: `{live_repository.matches_signed_inventory}`",
                    ]
                )
                for repository_signature in live_repository.signature_verifications:
                    lines.append(
                        f"- Signature verified: `{repository_signature.path}` by `{repository_signature.signature.signer_fingerprint}`"
                    )
                if verification.reproducibility is not None:
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=verification.reproducibility,
                        match_summary_label="Rebuilt repository matched staged policy",
                    )
            elif isinstance(verification, PythonDistributionVerificationReport):
                checksum_payload = verification.checksum
                index_resolution = verification.index_resolution
                lines.extend(
                    [
                        f"- File: `{verification.filename}`",
                        f"- URL: `{verification.uri}`",
                        f"- Project: `{verification.project_name}` `{verification.version}`",
                    ]
                )
                if checksum_payload.algorithm and checksum_payload.value:
                    lines.append(
                        f"- Checksum observed: `{checksum_payload.algorithm}:{checksum_payload.value}`"
                    )
                lines.extend(
                    [
                        f"- Checksum matched signed manifest: `{checksum_payload.matches_manifest}`",
                        f"- Checksum sidecar verified: `{checksum_payload.sidecar_verified}`",
                        f"- Simple index verified: `{index_resolution.project_index_url}`",
                        f"- Simple index hash matched: `{index_resolution.sha256_matches_index}`",
                    ]
                )
                if verification.reproducibility is not None:
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=verification.reproducibility,
                        match_summary_label="Rebuilt bytes matched staged artifact",
                    )
            elif isinstance(verification, OciImageVerificationReport):
                inspection = verification.inspection
                lines.extend(
                    [
                        f"- Image: `{inspection.image_ref}`",
                        f"- Digest verified: `{verification.digest}`",
                        f"- Platform digests matched: `{inspection.platform_digests_match}`",
                    ]
                )
                if verification.reproducibility is not None:
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=verification.reproducibility,
                        match_summary_label="Rebuilt image matched staged digests",
                    )
            elif isinstance(verification, NpmPackageVerificationReport):
                checksum_payload = verification.checksum
                registry_resolution = verification.registry_resolution
                lines.extend(
                    [
                        f"- Package: `{verification.package_name}` `{verification.version}`",
                        f"- Tarball: `{verification.uri}`",
                        f"- Integrity verified: `{verification.integrity.value}`",
                        f"- Integrity matched downloaded bytes: `{verification.integrity.matches_downloaded_bytes}`",
                        f"- Integrity matched signed manifest checksum: `{verification.integrity.matches_manifest_checksum}`",
                    ]
                )
                if checksum_payload.algorithm and checksum_payload.value:
                    lines.append(
                        f"- Checksum observed: `{checksum_payload.algorithm}:{checksum_payload.value}`"
                    )
                lines.extend(
                    [
                        f"- Checksum matched signed manifest: `{checksum_payload.matches_manifest}`",
                        f"- Registry metadata verified: `{registry_resolution.metadata_url}`",
                        f"- Registry tarball matched: `{registry_resolution.tarball_url_matches_manifest}`",
                        f"- Registry integrity matched: `{registry_resolution.integrity_matches_manifest}`",
                    ]
                )
                if verification.reproducibility is not None:
                    _append_reproducibility_markdown(
                        lines,
                        reproducibility_payload=verification.reproducibility,
                        match_summary_label="Rebuilt bytes matched staged artifact",
                    )
            elif isinstance(verification, InvalidSecondaryArtifactVerificationReport):
                lines.append(f"- Declared kind: `{_md_value(verification.declared_kind)}`")
            else:
                raise ValueError(
                    "unsupported secondary artifact kind for markdown reporting: "
                    f"{verification.artifact_id} ({kind})"
                )
            for issue in verification.issues:
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
    reproducibility_payload: ArtifactReproducibilityReport,
    match_summary_label: str,
) -> None:
    recipe_source = "local-override" if reproducibility_payload.override.applied else "canonical-profile"
    lines.extend(
        [
            f"- Reproducibility profile: `{reproducibility_payload.profile_id}`",
            f"- Reproducibility verdict: `{reproducibility_payload.verdict}`",
            f"- Reproducibility mode: `{reproducibility_payload.comparison_mode}`",
            f"- Recipe source: `{recipe_source}`",
            f"- {match_summary_label}: `{reproducibility_payload.matches_remote_bytes}`",
        ]
    )
    canonical_build = reproducibility_payload.canonical_recipe.build if reproducibility_payload.canonical_recipe else None
    effective_execution = reproducibility_payload.effective_execution
    effective_build = effective_execution.build if effective_execution is not None else None
    override_build = reproducibility_payload.override.build
    if effective_execution is not None:
        lines.append(f"- Execution backend: `{effective_execution.backend}`")
    if recipe_source == "local-override" and canonical_build is not None:
        canonical_command = canonical_build.command
        if canonical_command:
            lines.append(
                "- Canonical build command: `"
                + " ".join(str(part) for part in canonical_command)
                + "`"
            )
    build_command = effective_build.command if effective_build else []
    if build_command:
        lines.append("- Build command: `" + " ".join(str(part) for part in build_command) + "`")
    build_working_directory = effective_build.working_directory if effective_build else None
    if build_working_directory:
        lines.append(f"- Build working directory: `{build_working_directory}`")
    injected_environment_keys = effective_build.injected_environment_keys if effective_build else []
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
    if reproducibility_payload.failure_class is not None:
        lines.append(
            f"- Reproducibility failure class: `{reproducibility_payload.failure_class}`"
        )
    for output_path in (effective_build.output_paths if effective_build else []):
        lines.append(f"- Rebuild output: `{output_path}`")
    for evidence_reference in reproducibility_payload.evidence:
        lines.append(
            f"- Reproducibility evidence `{evidence_reference.label}`: `{evidence_reference.path}`"
        )


def _append_source_artifact_reproducibility_markdown(
    lines: list[str],
    *,
    reproducibility_payload: ArtifactReproducibilityReport,
) -> None:
    lines.extend(
        [
            f"- Source reproducibility profile: `{reproducibility_payload.profile_id}`",
            f"- Source reproducibility verdict: `{reproducibility_payload.verdict}`",
            f"- Source reproducibility mode: `{reproducibility_payload.comparison_mode}`",
            "- Source recipe source: `verifier-internal`",
            f"- Rebuilt bytes matched declared source commit: `{reproducibility_payload.matches_remote_bytes}`",
        ]
    )
    effective_execution = reproducibility_payload.effective_execution
    effective_build = effective_execution.build if effective_execution is not None else None
    if effective_execution is not None:
        lines.append(f"- Source rebuild backend: `{effective_execution.backend}`")
    build_command = effective_build.command if effective_build else []
    if build_command:
        lines.append(
            "- Source rebuild command: `"
            + " ".join(str(part) for part in build_command)
            + "`"
        )
    build_working_directory = effective_build.working_directory if effective_build else None
    if build_working_directory:
        lines.append(f"- Source rebuild working directory: `{build_working_directory}`")
    for output_path in (effective_build.output_paths if effective_build else []):
        lines.append(f"- Source rebuild output: `{output_path}`")
    if reproducibility_payload.failure_class is not None:
        lines.append(
            f"- Source reproducibility failure class: `{reproducibility_payload.failure_class}`"
        )


def _md_value(value: str | None) -> str:
    return value if value is not None else "n/a"


def _source_artifact_reproducibility_payload(
    *,
    source_artifact: SourceArtifactContract | None,
    source_artifact_path: Path | None,
    rebuilt_source_artifact_path: Path | None,
    rebuilt_source_sha512: str | None,
    source_artifact_matches_source_commit: bool,
    failures: list[VerificationFailure],
    inspection_bundle_root: Path | None,
) -> ArtifactReproducibilityReport | None:
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
    effective_execution: ArtifactReproducibilityEffectiveExecutionReport | None = None
    if rebuilt_source_artifact_path is not None:
        effective_execution = ArtifactReproducibilityEffectiveExecutionReport(
            backend="host-direct",
            build=ArtifactReproducibilityEffectiveBuildExecutionReport(
                command=["internal:create-from-git"],
                working_directory="source-repository",
                output_paths=[rebuilt_source_artifact_path.name],
                injected_environment_keys=[],
            ),
        )
    archive_analysis = (
        build_shallow_archive_analysis(
            staged_path=source_artifact_path,
            rebuilt_path=rebuilt_source_artifact_path,
        )
        if source_artifact_path is not None
        and rebuilt_source_artifact_path is not None
        and source_artifact_path.exists()
        and rebuilt_source_artifact_path.exists()
        else None
    )
    evidence: list[InspectionEvidenceReference] = []
    if inspection_bundle_root is not None and source_artifact_path is not None:
        metadata_payload = SourceArtifactReproducibilityMetadata(
            profile_id=profile_id,
            comparison_mode="exact-bytes",
            failure_class=failure_class,
            archive_analysis=archive_analysis,
            staged_artifact=RetainedArtifactSnapshot(
                filename=source_artifact.filename,
                sha512=sha512(source_artifact_path),
                size_bytes=source_artifact_path.stat().st_size,
            ),
            rebuilt_artifact=(
                RetainedArtifactSnapshot(
                    filename=rebuilt_source_artifact_path.name,
                    sha512=rebuilt_source_sha512,
                    size_bytes=rebuilt_source_artifact_path.stat().st_size,
                )
                if rebuilt_source_artifact_path is not None and rebuilt_source_sha512 is not None
                else None
            ),
            matches_remote_bytes=(
                source_artifact_matches_source_commit if rebuilt_source_sha512 is not None else None
            ),
            issues=reproducibility_issues,
        )
        metadata_path = write_source_artifact_reproducibility_metadata(
            inspection_bundle_root,
            payload=metadata_payload,
        )
        evidence.append(
            InspectionEvidenceReference(
                label="comparison-metadata",
                path=metadata_path,
            )
        )
        if reproducibility_issues:
            evidence.append(
                InspectionEvidenceReference(
                    label="staged-artifact",
                    path=retain_source_artifact_evidence_file(
                        inspection_bundle_root,
                        label_directory="staged",
                        source_path=source_artifact_path,
                    ),
                )
            )
            if rebuilt_source_artifact_path is not None:
                evidence.append(
                    InspectionEvidenceReference(
                        label="rebuilt-artifact",
                        path=retain_source_artifact_evidence_file(
                            inspection_bundle_root,
                            label_directory="rebuilt",
                            source_path=rebuilt_source_artifact_path,
                        ),
                    )
                )
    return ArtifactReproducibilityReport(
        profile_id=profile_id,
        verdict="failed" if reproducibility_issues else "verified",
        comparison_mode="exact-bytes",
        canonical_recipe=None,
        effective_execution=effective_execution,
        override=ArtifactReproducibilityOverrideReport(applied=False),
        matches_remote_bytes=(
            source_artifact_matches_source_commit if rebuilt_source_sha512 is not None else None
        ),
        failure_class=failure_class,
        archive_analysis=archive_analysis,
        evidence=evidence,
        issues=reproducibility_issues,
    )


def _failure_messages(
    failures: list[VerificationFailure],
    *,
    scope: str,
) -> list[str]:
    return [failure.message for failure in failures if failure.scope == scope]


def _override_field_summary(
    override_build: ArtifactReproducibilityBuildOverrideReport | None,
) -> list[str]:
    if override_build is None:
        return []
    fields: list[str] = []
    if override_build.command is not None:
        fields.append("build.command")
    if override_build.working_directory is not None:
        fields.append("build.working_directory")
    if override_build.output_globs is not None:
        fields.append("build.output_globs")
    fields.extend(f"build.env.{key}" for key in override_build.env_keys)
    return fields
