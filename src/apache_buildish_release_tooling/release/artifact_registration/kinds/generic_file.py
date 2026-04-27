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
from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.common import (
    apply_common_artifact_metadata,
)
from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from apache_buildish_release_tooling.release.source_artifact import sha512

_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")


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
        filename = explicit_filename.strip()
        if not filename:
            raise ValueError("generic-file --filename must not be empty")
        return filename
    if local_file is None:
        raise ValueError("generic-file requires --file or --filename")
    return local_file.name


def build_generic_file_registration(args: Namespace, bundle_dir: Path) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `generic-file` kind."""

    del bundle_dir  # reserved for future inventory-producing variants
    uri = args.uri.strip()
    if not uri:
        raise ValueError("generic-file requires --uri")
    local_file = _resolved_local_file(getattr(args, "file", None))
    digest_value = _normalized_sha512(local_file, getattr(args, "sha512", None))
    filename = _resolved_filename(local_file, getattr(args, "filename", None))
    artifact: dict[str, Any] = {
        "artifact_id": args.artifact_id,
        "kind": "generic-file",
        "filename": filename,
        "uri": uri,
        "checksums": {
            "sha512": {
                "value": digest_value,
            }
        },
        "signatures": [],
    }
    if args.sha512_uri:
        artifact["checksums"]["sha512"]["uri"] = args.sha512_uri.strip()
    apply_common_artifact_metadata(artifact, args)
    return ArtifactRegistrationResult(secondary_artifact=artifact)
