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

from pathlib import Path
from typing import cast

from apache_buildish_release_tooling.release.contracts import (
    GenericFileVerificationReport,
    SourceArtifactVerificationSection,
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
from apache_buildish_release_tooling.release.verification.inspection.report_loading import (
    load_supported_bundle_manifest,
    load_supported_verify_rc_report,
)
from apache_buildish_release_tooling.release.verification.inspection.targets import (
    failing_reproducibility_targets,
    filtered_reproducibility_targets,
    inspect_repro_summary,
    inspect_repro_target_payload,
    renumber_reproducibility_targets,
)
from apache_buildish_release_tooling.release.verification.inspection.transcript import (
    emit_failure_summary,
    emit_failure_target_list,
    emit_reproducibility_header,
)
from apache_buildish_release_tooling.release.verification.schemas import InspectReproReportV1


def inspect_repro_report(
    report_path: Path,
    *,
    progress_reporter: ProgressReporter,
    artifact_ids: tuple[str, ...] = (),
    summary_only: bool = False,
) -> None:
    """Read one saved verify-rc report and inspect any retained reproducibility evidence."""

    report = load_supported_verify_rc_report(report_path)
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
    bundle_manifest = load_supported_bundle_manifest(
        bundle_root=bundle_root,
        report=report,
    )
    emit_title(progress_reporter, "Inspect Repro")
    emit_detail(progress_reporter, "Report JSON", str(report_path))
    emit_detail(progress_reporter, "Inspection bundle", str(bundle_root))
    if bundle_manifest is not None:
        emit_detail(progress_reporter, "Bundle schema version", bundle_manifest.schema_version)
    emit_section(progress_reporter, "Summary")
    emit_detail(progress_reporter, "Component", report.component_id or "n/a")
    emit_detail(progress_reporter, "RC tag", report.rc_tag or "n/a")
    emit_detail(progress_reporter, "Report verdict", report.verdict)
    emit_detail(
        progress_reporter,
        "Build checks attempted",
        str(report.reproducibility_execution.build_checks_attempted),
    )
    targets = failing_reproducibility_targets(report)
    if not targets:
        emit_success(
            progress_reporter,
            "No reproducibility failures recorded in the verify-rc report",
        )
        return
    if artifact_ids:
        requested_ids = tuple(dict.fromkeys(artifact_ids))
        targets = renumber_reproducibility_targets(
            filtered_reproducibility_targets(targets, artifact_ids=requested_ids)
        )
        emit_detail(progress_reporter, "Selected artifact ids", ", ".join(requested_ids))
    total_failure_count = len(targets)
    emit_failure_summary(progress_reporter, targets=targets)
    emit_failure_target_list(progress_reporter, targets=targets)
    if summary_only:
        emit_info(
            progress_reporter,
            "Summary-only mode requested; skipping per-artifact inspection",
        )
        emit_section(progress_reporter, "Outcome")
        emit_success(
            progress_reporter,
            f"Summarized {total_failure_count} saved reproducibility failure(s)",
        )
        return
    emit_info(
        progress_reporter,
        f"Inspecting {total_failure_count} reproducibility failure(s) from the saved bundle",
    )
    for target in targets:
        emit_reproducibility_header(
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


def inspect_repro_report_json(
    report_path: Path,
    *,
    artifact_ids: tuple[str, ...] = (),
    summary_only: bool = False,
) -> InspectReproReportV1:
    """Build machine-readable inspect-repro output for one saved verify-rc report."""

    report = load_supported_verify_rc_report(report_path)
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
    bundle_manifest = load_supported_bundle_manifest(
        bundle_root=bundle_root,
        report=report,
    )
    targets = failing_reproducibility_targets(report)
    selected_artifact_ids = tuple(dict.fromkeys(artifact_ids))
    if selected_artifact_ids:
        targets = renumber_reproducibility_targets(
            filtered_reproducibility_targets(targets, artifact_ids=selected_artifact_ids)
        )
    summary = inspect_repro_summary(targets)
    target_payloads = [
        inspect_repro_target_payload(target)
        for target in targets
    ]
    return InspectReproReportV1(
        verify_rc_report_schema_version=report.schema_version,
        bundle_schema_version=bundle_manifest.schema_version if bundle_manifest is not None else None,
        component_id=report.component_id,
        rc_tag=report.rc_tag,
        verify_rc_verdict=report.verdict,
        build_checks_attempted=report.reproducibility_execution.build_checks_attempted,
        report_json_path=str(report_path),
        inspection_bundle_path=str(bundle_root),
        selected_artifact_ids=list(selected_artifact_ids),
        summary_only=summary_only,
        summary=summary,
        targets=target_payloads,
    )
__all__ = ["inspect_repro_report", "inspect_repro_report_json"]
