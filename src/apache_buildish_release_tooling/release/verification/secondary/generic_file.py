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

"""Generic secondary-file verifier kinds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.rc_vote_manifest import read_uri_bytes
from apache_buildish_release_tooling.release.source_artifact import checksum
from apache_buildish_release_tooling.release.verification.common import (
    GpgVerifier,
    signature_payload,
    validate_fetch_uri,
    verify_checksum_sidecar,
)

from .shared import (
    downloaded_inventory,
    preferred_checksum_payload,
    required_non_empty_string,
    verified_openpgp_signatures,
)


def verify_generic_file(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    verifier: GpgVerifier,
    allow_non_production_release_targets: bool,
    require_signature: bool,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    kind = required_non_empty_string(artifact_entry, "kind", source=manifest_url)
    filename = required_non_empty_string(artifact_entry, "filename", source=manifest_url)
    artifact_uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    validate_fetch_uri(
        artifact_uri,
        allow_non_production_release_targets=allow_non_production_release_targets,
        purpose=f"secondary artifact URL for {artifact_id}",
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = work_dir / filename
    artifact_path.write_bytes(read_uri_bytes(artifact_uri))

    checksum_algorithm, checksum_value, checksum_uri = preferred_checksum_payload(
        artifact_entry,
        source=manifest_url,
    )
    actual_checksum = checksum(artifact_path, checksum_algorithm)
    if actual_checksum != checksum_value:
        raise ValueError(
            "secondary artifact checksum does not match the signed manifest: "
            f"{artifact_id} {actual_checksum} != {checksum_value}"
        )

    checksum_sidecar_verified = False
    if checksum_uri is not None:
        validate_fetch_uri(
            checksum_uri,
            allow_non_production_release_targets=allow_non_production_release_targets,
            purpose=f"secondary artifact checksum sidecar URL for {artifact_id}",
        )
        sidecar_path = work_dir / f"{filename}.{checksum_algorithm}"
        sidecar_path.write_bytes(read_uri_bytes(checksum_uri))
        verify_checksum_sidecar(
            artifact_path,
            sidecar_path,
            algorithm=checksum_algorithm,
            purpose=f"secondary artifact {artifact_id}",
        )
        checksum_sidecar_verified = True

    signature_verifications = verified_openpgp_signatures(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        artifact_path=artifact_path,
        work_dir=work_dir,
        verifier=verifier,
        allow_non_production_release_targets=allow_non_production_release_targets,
        require_signature=require_signature,
    )
    inventory_verification = downloaded_inventory(
        artifact_entry,
        manifest_url=manifest_url,
        artifact_id=artifact_id,
        work_dir=work_dir,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )

    verification: dict[str, Any] = {
        "artifact_id": artifact_id,
        "kind": kind,
        "verdict": "verified",
        "filename": filename,
        "uri": artifact_uri,
        "checksum": {
            "algorithm": checksum_algorithm,
            "value": actual_checksum,
            "sidecar_verified": checksum_sidecar_verified,
        },
        "signatures": [signature_payload(signature) for signature in signature_verifications],
    }
    if inventory_verification is not None:
        verification["inventory"] = inventory_verification.report_payload
    return verification
