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

"""Secondary-artifact verification helpers for `verify-rc`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.verification.common import GpgVerifier

from .generic_file import verify_generic_file
from .maven_repository import verify_maven_repository
from .npm_package import verify_npm_package
from .oci_image import verify_oci_image
from .python_distribution import verify_python_distribution
from .shared import required_non_empty_string, safe_path_component, secondary_artifact_entries

__all__ = ["verify_secondary_artifacts"]


def verify_secondary_artifacts(
    manifest_payload: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
) -> list[dict[str, Any]]:
    """Verify all supported secondary artifacts declared in the signed vote manifest."""

    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_entries = secondary_artifact_entries(manifest_payload, source=manifest_url)
    verifications: list[dict[str, Any]] = []
    for index, artifact_entry in enumerate(artifact_entries, start=1):
        artifact_id = required_non_empty_string(
            artifact_entry,
            "artifact_id",
            source=manifest_url,
        )
        kind = required_non_empty_string(artifact_entry, "kind", source=manifest_url)
        artifact_work_dir = work_dir / f"{index:02d}-{safe_path_component(artifact_id)}"
        if kind == "generic-file":
            verifications.append(
                verify_generic_file(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=False,
                )
            )
            continue
        if kind == "generic-file-with-openpgp":
            verifications.append(
                verify_generic_file(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                    require_signature=True,
                )
            )
            continue
        if kind == "maven-repository":
            verifications.append(
                verify_maven_repository(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    verifier=verifier,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                )
            )
            continue
        if kind == "python-distribution":
            verifications.append(
                verify_python_distribution(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                )
            )
            continue
        if kind == "npm-package":
            verifications.append(
                verify_npm_package(
                    artifact_entry,
                    manifest_url=manifest_url,
                    work_dir=artifact_work_dir,
                    allow_non_production_release_targets=allow_non_production_release_targets,
                )
            )
            continue
        if kind == "oci-image":
            verifications.append(
                verify_oci_image(
                    artifact_entry,
                    manifest_url=manifest_url,
                )
            )
            continue
        raise ValueError(f"unsupported secondary artifact kind in manifest: {kind}")
    return verifications
