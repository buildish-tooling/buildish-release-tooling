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

"""Shared host-direct reproducibility helpers for file-like secondary artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.models import ComponentConfig
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    retain_evidence_file,
    write_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    resolve_rebuild_profile,
    run_host_direct_profile,
)

from .shared import required_non_empty_string


def verify_host_direct_single_file_reproducibility(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    kind: str,
    artifact_path: Path | None,
    work_dir: Path,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    inspection_bundle_root: Path | None,
    subject_label: str,
) -> dict[str, Any]:
    """Run one host-direct rebuild recipe and compare its single output file against staged bytes."""

    raw_reproducibility = artifact_entry.get("reproducibility")
    if not isinstance(raw_reproducibility, dict):
        return {
            "profile_id": "n/a",
            "verdict": "failed",
            "comparison_mode": "exact-bytes",
            "recipe_source": "canonical-profile",
            "execution_backend": "host-direct",
            "output_paths": [],
            "matches_remote_bytes": None,
            "failure_class": "missing-profile",
            "evidence": [],
            "issues": [
                f"manifest secondary artifact does not declare a reproducibility profile: {artifact_id}"
            ],
        }
    profile_id = required_non_empty_string(raw_reproducibility, "profile_id", source=manifest_url)
    issues: list[str] = []
    output_paths: list[str] = []
    matches_remote_bytes: bool | None = None
    comparison_mode = "exact-bytes"
    failure_class: str | None = None
    evidence: list[dict[str, str]] = []
    if component_config is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires --component-config to resolve profile {profile_id!r}"
        )
    if project_root is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires one verified source checkout"
        )
    if artifact_path is None:
        issues.append(
            f"build-based reproducibility for {artifact_id} requires the staged artifact bytes"
        )
    profile = None
    build_result = None
    if not issues and component_config is not None:
        try:
            profile = resolve_rebuild_profile(
                component_config,
                profile_id,
                expected_kinds=(kind,),
            )
            comparison_mode = str(profile.comparison.get("mode", comparison_mode))
        except Exception as exc:
            issues.append(str(exc))
    if not issues and profile is not None and project_root is not None and artifact_path is not None:
        try:
            build_result = run_host_direct_profile(
                profile_id=profile_id,
                profile=profile,
                project_root=project_root,
                work_dir=work_dir,
                source_date_epoch=source_date_epoch,
            )
            output_paths = [
                str(path.relative_to(project_root))
                for path in build_result.output_paths
            ]
            if len(build_result.output_paths) != 1:
                failure_class = "unexpected-output-count"
                raise ValueError(
                    f"{subject_label} reproducibility profile {profile_id!r} must produce exactly one output file"
                )
            built_artifact_path = build_result.output_paths[0]
            matches_remote_bytes = built_artifact_path.read_bytes() == artifact_path.read_bytes()
            if not matches_remote_bytes:
                failure_class = "byte-mismatch"
                raise ValueError(
                    f"{subject_label} reproducibility output does not match the staged artifact bytes: {artifact_id}"
                )
        except Exception as exc:
            issues.append(str(exc))
    if (
        inspection_bundle_root is not None
        and profile is not None
        and project_root is not None
        and artifact_path is not None
        and build_result is not None
    ):
        rebuilt_outputs = [
            {
                "path": str(path.relative_to(project_root)),
                "sha512": checksum(path, "sha512"),
                "size_bytes": path.stat().st_size,
            }
            for path in build_result.output_paths
        ]
        metadata_path = write_reproducibility_metadata(
            inspection_bundle_root,
            artifact_id=artifact_id,
            payload={
                "artifact_id": artifact_id,
                "kind": kind,
                "profile_id": profile_id,
                "comparison_mode": comparison_mode,
                "failure_class": failure_class,
                "staged_artifact": {
                    "filename": artifact_path.name,
                    "sha512": checksum(artifact_path, "sha512"),
                    "size_bytes": artifact_path.stat().st_size,
                },
                "rebuilt_outputs": rebuilt_outputs,
                "matches_remote_bytes": matches_remote_bytes,
                "issues": issues,
            },
        )
        evidence.append({"label": "comparison-metadata", "path": metadata_path})
        if issues:
            evidence.append(
                {
                    "label": "staged-artifact",
                    "path": retain_evidence_file(
                        inspection_bundle_root,
                        artifact_id=artifact_id,
                        label_directory="staged",
                        source_path=artifact_path,
                    ),
                }
            )
            for index, built_path in enumerate(build_result.output_paths, start=1):
                evidence.append(
                    {
                        "label": "rebuilt-artifact" if index == 1 else f"rebuilt-artifact-{index}",
                        "path": retain_evidence_file(
                            inspection_bundle_root,
                            artifact_id=artifact_id,
                            label_directory=f"rebuilt-{index:02d}",
                            source_path=built_path,
                        ),
                    }
                )
    return {
        "profile_id": profile_id,
        "verdict": "failed" if issues else "verified",
        "comparison_mode": comparison_mode,
        "recipe_source": "canonical-profile",
        "execution_backend": "host-direct",
        "output_paths": output_paths,
        "matches_remote_bytes": matches_remote_bytes,
        "failure_class": failure_class,
        "evidence": evidence,
        "issues": issues,
    }
