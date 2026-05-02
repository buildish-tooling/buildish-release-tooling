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

"""Read-only post-verification reproducibility inspection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    GenericFileVerificationReport,
    SourceArtifactVerificationSection,
    VerifyRcReportV1,
)
from apache_buildish_release_tooling.release.progress import ProgressReporter
from apache_buildish_release_tooling.release.verification.common import (
    emit_detail,
    emit_info,
    emit_section,
    emit_success,
    emit_title,
    emit_warning,
)
from apache_buildish_release_tooling.release.verification.inspection.file_like import (
    inspect_file_like_reproducibility,
)
from apache_buildish_release_tooling.release.verification.inspection.maven_repository import (
    inspect_maven_repository_reproducibility,
)
from apache_buildish_release_tooling.release.verification.inspection.npm_package import (
    inspect_npm_package_reproducibility,
)
from apache_buildish_release_tooling.release.verification.inspection.oci_image import (
    inspect_oci_image_reproducibility,
)
from apache_buildish_release_tooling.release.verification.inspection.python_distribution import (
    inspect_python_distribution_reproducibility,
)
from apache_buildish_release_tooling.release.verification.inspection.source_artifact import (
    inspect_source_artifact_reproducibility,
)


@dataclass(frozen=True)
class ReproducibilityFailureInspectionTarget:
    """One retained reproducibility failure selected for inspect-repro analysis."""

    section_label: str
    kind: str
    artifact_id: str
    reproducibility: ArtifactReproducibilityReport
    verification: AnySecondaryArtifactVerification | SourceArtifactVerificationSection


def inspect_repro_report(report_path: Path, *, progress_reporter: ProgressReporter) -> None:
    """Read one saved verify-rc report and inspect any retained reproducibility evidence."""

    report = VerifyRcReportV1.model_validate_json(report_path.read_text(encoding="utf-8"))
    inspection_bundle = report.inspection_bundle
    if inspection_bundle is None:
        raise ValueError(
            f"verify-rc report does not reference an inspection bundle: {report_path}"
        )
    bundle_root = (report_path.parent / inspection_bundle.relative_path_from_report).resolve()
    if not bundle_root.exists():
        raise ValueError(
            f"inspection bundle referenced by verify-rc report does not exist: {bundle_root}"
        )
    emit_title(progress_reporter, "Inspect Repro")
    emit_detail(progress_reporter, "Report JSON", str(report_path))
    emit_detail(progress_reporter, "Inspection bundle", str(bundle_root))
    emit_section(progress_reporter, "Summary")
    emit_detail(progress_reporter, "Component", report.component_id or "n/a")
    emit_detail(progress_reporter, "RC tag", report.rc_tag or "n/a")
    emit_detail(progress_reporter, "Report verdict", report.verdict)
    emit_detail(
        progress_reporter,
        "Build checks attempted",
        str(report.reproducibility_execution.build_checks_attempted),
    )
    targets = _failing_reproducibility_targets(report)
    total_failure_count = len(targets)
    if total_failure_count == 0:
        emit_success(
            progress_reporter,
            "No reproducibility failures recorded in the verify-rc report",
        )
        return
    _emit_failure_summary(progress_reporter, targets=targets)
    emit_info(
        progress_reporter,
        f"Inspecting {total_failure_count} reproducibility failure(s) from the saved bundle",
    )
    for target in targets:
        _emit_reproducibility_header(
            progress_reporter,
            section_label=target.section_label,
            reproducibility=target.reproducibility,
            verification=target.verification,
        )
        if isinstance(target.verification, SourceArtifactVerificationSection):
            inspect_source_artifact_reproducibility(
                progress_reporter,
                verification=target.verification,
                reproducibility=target.reproducibility,
                bundle_root=bundle_root,
            )
            continue
        verification = target.verification
        reproducibility = target.reproducibility
        if verification.kind in {"generic-file", "generic-file-with-openpgp"}:
            inspect_file_like_reproducibility(
                progress_reporter,
                verification=cast(GenericFileVerificationReport, verification),
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "python-distribution":
            inspect_python_distribution_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "npm-package":
            inspect_npm_package_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "maven-repository":
            inspect_maven_repository_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "oci-image":
            inspect_oci_image_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        emit_warning(
            progress_reporter,
            f"No inspect-repro analyzer is implemented yet for {verification.kind}",
        )
    emit_section(progress_reporter, "Outcome")
    emit_success(
        progress_reporter,
        f"Inspected {total_failure_count} saved reproducibility failure(s)",
    )


def _failing_reproducibility_targets(
    report: VerifyRcReportV1,
) -> list[ReproducibilityFailureInspectionTarget]:
    targets: list[ReproducibilityFailureInspectionTarget] = []
    source_reproducibility = report.source_artifact_verification.reproducibility
    if (
        isinstance(source_reproducibility, ArtifactReproducibilityReport)
        and source_reproducibility.verdict == "failed"
    ):
        targets.append(
            ReproducibilityFailureInspectionTarget(
                section_label="Source Artifact",
                kind="source-artifact",
                artifact_id="source-artifact",
                reproducibility=source_reproducibility,
                verification=report.source_artifact_verification,
            )
        )
    for verification in report.secondary_artifact_verifications:
        reproducibility = getattr(verification, "reproducibility", None)
        if not isinstance(reproducibility, ArtifactReproducibilityReport):
            continue
        if reproducibility.verdict != "failed":
            continue
        targets.append(
            ReproducibilityFailureInspectionTarget(
                section_label=f"Artifact: {verification.artifact_id}",
                kind=verification.kind,
                artifact_id=verification.artifact_id,
                reproducibility=reproducibility,
                verification=verification,
            )
        )
    total_failure_count = len(targets)
    normalized_targets: list[ReproducibilityFailureInspectionTarget] = []
    for index, target in enumerate(targets, start=1):
        normalized_targets.append(
            ReproducibilityFailureInspectionTarget(
                section_label=(
                    f"Source Artifact {index}/{total_failure_count}"
                    if target.kind == "source-artifact"
                    else f"Artifact {index}/{total_failure_count}: {target.artifact_id}"
                ),
                kind=target.kind,
                artifact_id=target.artifact_id,
                reproducibility=target.reproducibility,
                verification=target.verification,
            )
        )
    return normalized_targets


def _emit_failure_summary(
    progress_reporter: ProgressReporter,
    *,
    targets: list[ReproducibilityFailureInspectionTarget],
) -> None:
    emit_detail(progress_reporter, "Reproducibility failures", str(len(targets)))
    source_failure_count = sum(1 for target in targets if target.kind == "source-artifact")
    secondary_failure_count = len(targets) - source_failure_count
    emit_detail(progress_reporter, "Source artifact failures", str(source_failure_count))
    emit_detail(progress_reporter, "Secondary artifact failures", str(secondary_failure_count))
    emit_detail(
        progress_reporter,
        "Failure kinds",
        _summarize_counts([target.kind for target in targets]),
    )
    emit_detail(
        progress_reporter,
        "Failure classes",
        _summarize_counts(
            [target.reproducibility.failure_class or "unspecified" for target in targets]
        ),
    )


def _emit_reproducibility_header(
    progress_reporter: ProgressReporter,
    *,
    section_label: str,
    reproducibility: ArtifactReproducibilityReport,
    verification: AnySecondaryArtifactVerification | SourceArtifactVerificationSection,
) -> None:
    emit_section(progress_reporter, section_label)
    if isinstance(verification, SourceArtifactVerificationSection):
        emit_detail(progress_reporter, "Kind", "source-artifact")
        source_artifact_verification = True
    else:
        emit_detail(progress_reporter, "Kind", verification.kind)
        source_artifact_verification = False
    emit_detail(progress_reporter, "Profile", reproducibility.profile_id)
    emit_detail(progress_reporter, "Comparison mode", reproducibility.comparison_mode)
    recipe_source = (
        "verifier-internal"
        if source_artifact_verification
        else ("local-override" if reproducibility.override.applied else "canonical-profile")
    )
    emit_detail(progress_reporter, "Recipe source", recipe_source)
    if recipe_source == "local-override" and reproducibility.canonical_recipe is not None:
        canonical_build = reproducibility.canonical_recipe.build
        if canonical_build.command:
            emit_detail(
                progress_reporter,
                "Canonical build command",
                " ".join(canonical_build.command),
            )
    effective_execution = reproducibility.effective_execution
    if effective_execution is not None:
        emit_detail(progress_reporter, "Execution backend", effective_execution.backend)
    effective_build = effective_execution.build if effective_execution is not None else None
    if effective_build is not None and effective_build.command:
        emit_detail(
            progress_reporter,
            "Build command",
            " ".join(effective_build.command),
        )
    if effective_build is not None and effective_build.working_directory is not None:
        emit_detail(
            progress_reporter,
            "Build working directory",
            effective_build.working_directory,
        )
    if effective_build is not None and effective_build.injected_environment_keys:
        emit_detail(
            progress_reporter,
            "Injected environment keys",
            ", ".join(effective_build.injected_environment_keys),
        )
    override_fields = _override_field_summary(reproducibility)
    if override_fields:
        emit_detail(
            progress_reporter,
            "Override fields",
            ", ".join(override_fields),
        )
    if reproducibility.failure_class is not None:
        emit_detail(
            progress_reporter,
            "Failure class",
            reproducibility.failure_class,
        )
    if reproducibility.evidence:
        emit_detail(
            progress_reporter,
            "Retained evidence",
            ", ".join(reference.label for reference in reproducibility.evidence),
        )


def _override_field_summary(
    reproducibility: ArtifactReproducibilityReport,
) -> list[str]:
    build_override = reproducibility.override.build
    if build_override is None:
        return []
    fields: list[str] = []
    if build_override.command is not None:
        fields.append("build.command")
    if build_override.working_directory is not None:
        fields.append("build.working_directory")
    if build_override.output_globs is not None:
        fields.append("build.output_globs")
    fields.extend(f"build.env.{key}" for key in build_override.env_keys)
    return fields


def _summarize_counts(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return ", ".join(f"{value}={count}" for value, count in sorted(counts.items()))


__all__ = ["inspect_repro_report"]
