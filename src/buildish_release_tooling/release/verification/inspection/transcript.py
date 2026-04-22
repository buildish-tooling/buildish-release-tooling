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

"""Human-transcript helpers for `inspect-repro`."""

from __future__ import annotations

from buildish_release_tooling.release.contracts import (
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    SourceArtifactVerificationSection,
)
from buildish_release_tooling.release.progress import ProgressReporter
from buildish_release_tooling.release.verification.common import emit_detail, emit_section

from .targets import (
    ReproducibilityFailureInspectionTarget,
    grouped_failure_targets,
    inspect_repro_summary,
    override_field_summary,
    render_count_summaries,
    secondary_recipe_source,
)


def emit_failure_summary(
    progress_reporter: ProgressReporter,
    *,
    targets: list[ReproducibilityFailureInspectionTarget],
) -> None:
    """Emit the top-level grouped failure summary for one inspect-repro run."""

    summary = inspect_repro_summary(targets)
    emit_detail(progress_reporter, "Reproducibility failures", str(summary.failure_count))
    emit_detail(progress_reporter, "Source artifact failures", str(summary.source_failure_count))
    emit_detail(progress_reporter, "Secondary artifact failures", str(summary.secondary_failure_count))
    emit_detail(
        progress_reporter,
        "Failure kinds",
        render_count_summaries(summary.failure_kinds),
    )
    emit_detail(
        progress_reporter,
        "Failure classes",
        render_count_summaries(summary.failure_classes),
    )
    emit_detail(
        progress_reporter,
        "Failure groups",
        render_count_summaries(summary.failure_groups),
    )
    for group_label, artifact_ids in grouped_failure_targets(targets).items():
        emit_detail(
            progress_reporter,
            "Failure group",
            f"{group_label}: {', '.join(sorted(artifact_ids))}",
        )


def emit_failure_target_list(
    progress_reporter: ProgressReporter,
    *,
    targets: list[ReproducibilityFailureInspectionTarget],
) -> None:
    """Emit the flat per-target failure list for one inspect-repro run."""

    for target in targets:
        failure_class = target.reproducibility.failure_class or "unspecified"
        emit_detail(
            progress_reporter,
            "Failure target",
            f"{target.artifact_id} [{target.kind}] {failure_class}",
        )


def emit_reproducibility_header(
    progress_reporter: ProgressReporter,
    *,
    section_label: str,
    reproducibility: ArtifactReproducibilityReport,
    verification: AnySecondaryArtifactVerification | SourceArtifactVerificationSection,
) -> None:
    """Emit the per-target header section before kind-specific inspection details."""

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
        else secondary_recipe_source(reproducibility)
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
    fields = override_field_summary(reproducibility)
    if fields:
        emit_detail(
            progress_reporter,
            "Override fields",
            ", ".join(fields),
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
