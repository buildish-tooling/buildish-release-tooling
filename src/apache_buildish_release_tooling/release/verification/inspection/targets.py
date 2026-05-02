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

"""Target selection and machine-readable summaries for `inspect-repro`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    InspectReproCountSummary,
    InspectReproSummaryV1,
    InspectReproTargetV1,
    SourceArtifactVerificationSection,
    VerifyRcReportV1,
)


@dataclass(frozen=True)
class ReproducibilityFailureInspectionTarget:
    """One retained reproducibility failure selected for inspect-repro analysis."""

    section_label: str
    kind: str
    artifact_id: str
    reproducibility: ArtifactReproducibilityReport
    verification: AnySecondaryArtifactVerification | SourceArtifactVerificationSection


def failing_reproducibility_targets(
    report: VerifyRcReportV1,
) -> list[ReproducibilityFailureInspectionTarget]:
    """Return all retained reproducibility failures from one verify-rc report."""

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
    return renumber_reproducibility_targets(targets)


def filtered_reproducibility_targets(
    targets: list[ReproducibilityFailureInspectionTarget],
    *,
    artifact_ids: tuple[str, ...],
) -> list[ReproducibilityFailureInspectionTarget]:
    """Filter retained failures to explicit artifact ids or raise a direct error."""

    allowed_ids = set(artifact_ids)
    filtered_targets = [target for target in targets if target.artifact_id in allowed_ids]
    if filtered_targets:
        return filtered_targets
    available_ids = ", ".join(sorted(target.artifact_id for target in targets))
    raise ValueError(
        "requested inspect-repro artifact ids did not match any retained reproducibility failures: "
        f"{', '.join(artifact_ids)}; available: {available_ids or 'none'}"
    )


def renumber_reproducibility_targets(
    targets: list[ReproducibilityFailureInspectionTarget],
) -> list[ReproducibilityFailureInspectionTarget]:
    """Normalize section headings so filtered and full runs number targets consistently."""

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


def inspect_repro_summary(
    targets: list[ReproducibilityFailureInspectionTarget],
) -> InspectReproSummaryV1:
    """Build the machine-readable top-level failure summary for inspect-repro."""

    source_failure_count = sum(1 for target in targets if target.kind == "source-artifact")
    secondary_failure_count = len(targets) - source_failure_count
    return InspectReproSummaryV1(
        failure_count=len(targets),
        source_failure_count=source_failure_count,
        secondary_failure_count=secondary_failure_count,
        failure_kinds=_count_summaries([target.kind for target in targets]),
        failure_classes=_count_summaries(
            [target.reproducibility.failure_class or "unspecified" for target in targets]
        ),
        failure_groups=_count_summaries(
            [failure_group_label(target) for target in targets]
        ),
    )


def grouped_failure_targets(
    targets: list[ReproducibilityFailureInspectionTarget],
) -> dict[str, list[str]]:
    """Group retained failures by stable machine-readable failure bucket."""

    grouped: dict[str, list[str]] = {}
    for target in targets:
        grouped.setdefault(failure_group_label(target), []).append(target.artifact_id)
    return grouped


def render_count_summaries(summaries: list[InspectReproCountSummary]) -> str:
    """Render one list of grouped failure counters for the human transcript."""

    return ", ".join(f"{summary.key}={summary.count}" for summary in summaries)


def override_field_summary(
    reproducibility: ArtifactReproducibilityReport,
) -> list[str]:
    """Return stable dotted-path labels for the applied local override delta."""

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


def secondary_recipe_source(
    reproducibility: ArtifactReproducibilityReport,
) -> Literal["canonical-profile", "local-override"]:
    """Return the human- and machine-facing recipe-source label for one secondary artifact."""

    return "local-override" if reproducibility.override.applied else "canonical-profile"


def inspect_repro_target_payload(
    target: ReproducibilityFailureInspectionTarget,
) -> InspectReproTargetV1:
    """Build one machine-readable inspect-repro target payload."""

    reproducibility = target.reproducibility
    verification = target.verification
    source_artifact_verification = isinstance(verification, SourceArtifactVerificationSection)
    recipe_source = (
        "verifier-internal"
        if source_artifact_verification
        else secondary_recipe_source(reproducibility)
    )
    return InspectReproTargetV1(
        section_label=target.section_label,
        artifact_id=target.artifact_id,
        kind=target.kind,
        failure_class=reproducibility.failure_class,
        profile_id=reproducibility.profile_id,
        comparison_mode=reproducibility.comparison_mode,
        recipe_source=recipe_source,
        evidence_labels=[reference.label for reference in reproducibility.evidence],
        override_fields=override_field_summary(reproducibility),
    )


def failure_group_label(target: ReproducibilityFailureInspectionTarget) -> str:
    """Return the stable failure-group label used in inspect-repro summaries."""

    scope = "source" if target.kind == "source-artifact" else "secondary"
    failure_class = target.reproducibility.failure_class or "unspecified"
    return f"{scope}/{target.kind}/{failure_class}"


def _count_summaries(values: list[str]) -> list[InspectReproCountSummary]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        InspectReproCountSummary(key=value, count=count)
        for value, count in sorted(counts.items())
    ]
