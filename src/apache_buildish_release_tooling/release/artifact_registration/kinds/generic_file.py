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

"""Handler for the `generic-file` artifact-registration kind."""

from __future__ import annotations

import re
from argparse import Namespace
from pathlib import Path
from urllib.parse import urlparse

from apache_buildish_release_tooling.release.artifact_registration.common import (
    common_artifact_metadata,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from apache_buildish_release_tooling.release.contracts import (
    GenericFileSecondaryArtifact,
    Sha512ChecksumPayload,
    Sha512Checksums,
)
from apache_buildish_release_tooling.release.path_validation import validate_simple_filename
from apache_buildish_release_tooling.release.source_artifact import sha512

_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")


def _required_https_uri(raw_value: str, *, option_name: str) -> str:
    uri = raw_value.strip()
    if not uri:
        raise ValueError(f"generic-file requires {option_name}")
    parsed = urlparse(uri)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"generic-file {option_name} must be an https:// URI")
    return uri


def _resolved_local_file(path_text: str | None) -> Path | None:
    if path_text is None:
        return None
    local_path = Path(path_text).resolve()
    if not local_path.is_file():
        raise ValueError(f"artifact file does not exist: {local_path}")
    return local_path


def _normalized_sha512(local_file: Path | None, explicit_sha512: str | None) -> str:
    if explicit_sha512 is None:
        if local_file is None:
            raise ValueError("generic-file requires --file or --sha512")
        return sha512(local_file)
    normalized = explicit_sha512.strip().lower()
    if not _SHA512_PATTERN.fullmatch(normalized):
        raise ValueError("generic-file --sha512 must be a 128-character hexadecimal SHA512 digest")
    if local_file is None:
        return normalized
    computed = sha512(local_file)
    if computed != normalized:
        raise ValueError("generic-file --sha512 does not match the bytes of --file")
    return normalized


def _resolved_filename(local_file: Path | None, explicit_filename: str | None) -> str:
    if explicit_filename is not None:
        return validate_simple_filename(
            explicit_filename,
            field_name="generic-file --filename",
        )
    if local_file is None:
        raise ValueError("generic-file requires --file or --filename")
    return validate_simple_filename(local_file.name, field_name="generic-file filename")


def build_generic_file_registration(args: Namespace, bundle_dir: Path) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `generic-file` kind."""

    del bundle_dir  # reserved for future inventory-producing variants
    uri = _required_https_uri(args.uri, option_name="--uri")
    local_file = _resolved_local_file(getattr(args, "file", None))
    digest_value = _normalized_sha512(local_file, getattr(args, "sha512", None))
    filename = _resolved_filename(local_file, getattr(args, "filename", None))
    common_metadata = common_artifact_metadata(args)
    return ArtifactRegistrationResult(
        secondary_artifact=GenericFileSecondaryArtifact(
            artifact_id=args.artifact_id,
            role=common_metadata.role,
            artifact_origin=common_metadata.artifact_origin,
            git_commit_sha=common_metadata.git_commit_sha,
            reproducibility=common_metadata.reproducibility,
            filename=filename,
            uri=uri,
            checksums=Sha512Checksums(
                sha512=Sha512ChecksumPayload(
                    value=digest_value,
                    uri=(
                        _required_https_uri(args.sha512_uri, option_name="--sha512-uri")
                        if args.sha512_uri
                        else None
                    ),
                )
            ),
            signatures=[],
        )
    )
