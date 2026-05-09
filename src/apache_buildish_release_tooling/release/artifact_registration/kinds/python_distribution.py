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

"""Handler for the `python-distribution` artifact-registration kind."""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path

from apache_buildish_release_tooling.release.artifact_registration.common import (
    common_artifact_metadata,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from apache_buildish_release_tooling.release.contracts import (
    PyPiAttestationAuth,
    Sha256ChecksumPayload,
    Sha256Checksums,
    PythonDistributionSecondaryArtifact,
)
from apache_buildish_release_tooling.release.path_validation import validate_simple_filename
from apache_buildish_release_tooling.release.source_artifact import checksum

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _resolved_local_file(path_text: str | None) -> Path | None:
    if path_text is None:
        return None
    local_path = Path(path_text).resolve()
    if not local_path.is_file():
        raise ValueError(f"artifact file does not exist: {local_path}")
    return local_path


def _normalized_sha256(local_file: Path | None, explicit_sha256: str | None) -> str:
    if explicit_sha256 is None:
        if local_file is None:
            raise ValueError("python-distribution requires --file or --sha256")
        return checksum(local_file, "sha256")
    normalized = explicit_sha256.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError("python-distribution --sha256 must be a 64-character hexadecimal SHA256 digest")
    if local_file is None:
        return normalized
    computed = checksum(local_file, "sha256")
    if computed != normalized:
        raise ValueError("python-distribution --sha256 does not match the bytes of --file")
    return normalized


def _resolved_filename(local_file: Path | None, explicit_filename: str | None) -> str:
    if explicit_filename is not None:
        return validate_simple_filename(
            explicit_filename,
            field_name="python-distribution --filename",
        )
    if local_file is None:
        raise ValueError("python-distribution requires --file or --filename")
    return validate_simple_filename(local_file.name, field_name="python-distribution filename")


def _required_text(raw_value: str | None, *, option_name: str) -> str:
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"python-distribution requires {option_name}")
    return raw_value.strip()


def _optional_text(raw_value: str | None, *, option_name: str) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"python-distribution {option_name} must not be empty")
    return normalized


def build_python_distribution_registration(
    args: Namespace,
    bundle_dir: Path,
) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `python-distribution` kind."""

    del bundle_dir  # reserved for future inventory-producing variants
    local_file = _resolved_local_file(getattr(args, "file", None))
    common_metadata = common_artifact_metadata(args)
    sha256_uri = _optional_text(getattr(args, "sha256_uri", None), option_name="--sha256-uri")
    attestation_repository = _optional_text(
        getattr(args, "attestation_repository", None),
        option_name="--attestation-repository",
    )
    return ArtifactRegistrationResult(
        secondary_artifact=PythonDistributionSecondaryArtifact(
            artifact_id=args.artifact_id,
            role=common_metadata.role,
            artifact_origin=common_metadata.artifact_origin,
            git_commit_sha=common_metadata.git_commit_sha,
            reproducibility=common_metadata.reproducibility,
            filename=_resolved_filename(local_file, getattr(args, "filename", None)),
            uri=_required_text(getattr(args, "uri", None), option_name="--uri"),
            index_url=_required_text(getattr(args, "index_url", None), option_name="--index-url"),
            project_name=_required_text(
                getattr(args, "project_name", None),
                option_name="--project-name",
            ),
            version=_required_text(getattr(args, "package_version", None), option_name="--package-version"),
            checksums=Sha256Checksums(
                sha256=Sha256ChecksumPayload(
                    value=_normalized_sha256(local_file, getattr(args, "sha256", None)),
                    uri=sha256_uri,
                )
            ),
            authenticity=(
                PyPiAttestationAuth(repository=attestation_repository)
                if attestation_repository is not None
                else None
            ),
        )
    )
