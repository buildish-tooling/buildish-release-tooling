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
    AnySecondaryArtifactVerification,
    ArtifactReproducibilityReport,
    GenericFileVerificationReport,
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
from apache_buildish_release_tooling.release.verification.inspection.oci_image import (
    inspect_oci_image_reproducibility,
)


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
    failing_reproducibility_checks: list[
        tuple[AnySecondaryArtifactVerification, ArtifactReproducibilityReport]
    ] = []
    for verification in report.secondary_artifact_verifications:
        reproducibility = getattr(verification, "reproducibility", None)
        if not isinstance(reproducibility, ArtifactReproducibilityReport):
            continue
        if reproducibility.verdict != "failed":
            continue
        failing_reproducibility_checks.append((verification, reproducibility))
    if not failing_reproducibility_checks:
        emit_success(
            progress_reporter,
            "No reproducibility failures recorded in the verify-rc report",
        )
        return
    emit_info(
        progress_reporter,
        f"Inspecting {len(failing_reproducibility_checks)} reproducibility failure(s) from the saved bundle",
    )
    for index, (verification, reproducibility) in enumerate(
        failing_reproducibility_checks,
        start=1,
    ):
        emit_section(
            progress_reporter,
            f"Artifact {index}/{len(failing_reproducibility_checks)}: {verification.artifact_id}",
        )
        emit_detail(progress_reporter, "Kind", verification.kind)
        emit_detail(progress_reporter, "Profile", reproducibility.profile_id)
        emit_detail(progress_reporter, "Comparison mode", reproducibility.comparison_mode)
        emit_detail(progress_reporter, "Recipe source", reproducibility.recipe_source)
        if reproducibility.override_fields:
            emit_detail(
                progress_reporter,
                "Override fields",
                ", ".join(reproducibility.override_fields),
            )
        if reproducibility.failure_class is not None:
            emit_detail(
                progress_reporter,
                "Failure class",
                reproducibility.failure_class,
            )
        if verification.kind in {"generic-file", "generic-file-with-openpgp"}:
            inspect_file_like_reproducibility(
                progress_reporter,
                verification=cast(GenericFileVerificationReport, verification),
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "python-distribution":
            inspect_file_like_reproducibility(
                progress_reporter,
                verification=verification,
                reproducibility=reproducibility,
                bundle_root=bundle_root,
            )
            continue
        if verification.kind == "npm-package":
            inspect_file_like_reproducibility(
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


__all__ = ["inspect_repro_report"]
