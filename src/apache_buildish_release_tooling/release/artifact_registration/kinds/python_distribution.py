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
from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.common import (
    apply_common_artifact_metadata,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
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
        filename = explicit_filename.strip()
        if not filename:
            raise ValueError("python-distribution --filename must not be empty")
        return filename
    if local_file is None:
        raise ValueError("python-distribution requires --file or --filename")
    return local_file.name


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
    artifact: dict[str, Any] = {
        "artifact_id": args.artifact_id,
        "kind": "python-distribution",
        "filename": _resolved_filename(local_file, getattr(args, "filename", None)),
        "uri": _required_text(getattr(args, "uri", None), option_name="--uri"),
        "index_url": _required_text(getattr(args, "index_url", None), option_name="--index-url"),
        "project_name": _required_text(getattr(args, "project_name", None), option_name="--project-name"),
        "version": _required_text(getattr(args, "package_version", None), option_name="--package-version"),
        "checksums": {
            "sha256": {
                "value": _normalized_sha256(local_file, getattr(args, "sha256", None)),
            }
        },
    }
    sha256_uri = _optional_text(getattr(args, "sha256_uri", None), option_name="--sha256-uri")
    if sha256_uri is not None:
        artifact["checksums"]["sha256"]["uri"] = sha256_uri
    attestation_repository = _optional_text(
        getattr(args, "attestation_repository", None),
        option_name="--attestation-repository",
    )
    if attestation_repository is not None:
        artifact["authenticity"] = {
            "scheme": "pypi-attestation",
            "repository": attestation_repository,
        }
    apply_common_artifact_metadata(artifact, args)
    return ArtifactRegistrationResult(secondary_artifact=artifact)
