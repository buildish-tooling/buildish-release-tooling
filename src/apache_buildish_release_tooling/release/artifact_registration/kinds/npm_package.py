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

"""Handler for the `npm-package` artifact-registration kind."""

from __future__ import annotations

import base64
import binascii
import re
from argparse import Namespace
from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from apache_buildish_release_tooling.release.source_artifact import checksum

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")
_SUPPORTED_INTEGRITY_ALGORITHMS = frozenset({"sha256", "sha512"})
_EXPECTED_DIGEST_LENGTHS = {
    "sha256": 32,
    "sha512": 64,
}


def _resolved_local_file(path_text: str | None) -> Path | None:
    if path_text is None:
        return None
    local_path = Path(path_text).resolve()
    if not local_path.is_file():
        raise ValueError(f"artifact file does not exist: {local_path}")
    return local_path


def _resolved_filename(local_file: Path | None, explicit_filename: str | None) -> str:
    if explicit_filename is not None:
        filename = explicit_filename.strip()
        if not filename:
            raise ValueError("npm-package --filename must not be empty")
        return filename
    if local_file is None:
        raise ValueError("npm-package requires --file or --filename")
    return local_file.name


def _required_text(raw_value: str | None, *, option_name: str) -> str:
    if raw_value is None or not raw_value.strip():
        raise ValueError(f"npm-package requires {option_name}")
    return raw_value.strip()


def _optional_text(raw_value: str | None, *, option_name: str) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"npm-package {option_name} must not be empty")
    return normalized


def _normalized_hex_digest(raw_value: str | None, *, algorithm: str) -> str:
    if raw_value is None:
        raise ValueError(f"npm-package requires --{algorithm}")
    normalized = raw_value.strip().lower()
    pattern = _SHA256_PATTERN if algorithm == "sha256" else _SHA512_PATTERN
    if not pattern.fullmatch(normalized):
        bit_length = 256 if algorithm == "sha256" else 512
        raise ValueError(
            f"npm-package --{algorithm} must be a {bit_length // 4}-character hexadecimal {algorithm.upper()} digest"
        )
    return normalized


def _integrity_from_digest(algorithm: str, digest_value: str) -> str:
    digest_bytes = bytes.fromhex(digest_value)
    encoded = base64.b64encode(digest_bytes).decode("ascii")
    return f"{algorithm}-{encoded}"


def _normalized_integrity(raw_value: str) -> tuple[str, str, str]:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError("npm-package --integrity must not be empty")
    algorithm, separator, encoded_digest = normalized.partition("-")
    normalized_algorithm = algorithm.lower()
    if not separator or not encoded_digest or normalized_algorithm not in _SUPPORTED_INTEGRITY_ALGORITHMS:
        raise ValueError("npm-package --integrity must use sha256-<base64> or sha512-<base64>")
    try:
        digest_bytes = base64.b64decode(encoded_digest, validate=True)
    except binascii.Error as exc:
        raise ValueError("npm-package --integrity must use sha256-<base64> or sha512-<base64>") from exc
    expected_length = _EXPECTED_DIGEST_LENGTHS[normalized_algorithm]
    if len(digest_bytes) != expected_length:
        raise ValueError("npm-package --integrity digest length does not match its declared algorithm")
    digest_value = digest_bytes.hex()
    return normalized_algorithm, digest_value, _integrity_from_digest(normalized_algorithm, digest_value)


def _resolved_integrity_material(
    local_file: Path | None,
    *,
    explicit_integrity: str | None,
    explicit_sha256: str | None,
    explicit_sha512: str | None,
) -> tuple[str, str, str]:
    explicit_inputs = sum(
        value is not None
        for value in (
            explicit_integrity,
            explicit_sha256,
            explicit_sha512,
        )
    )
    if explicit_inputs > 1:
        raise ValueError("npm-package accepts at most one of --integrity, --sha256, or --sha512")
    if explicit_integrity is not None:
        algorithm, digest_value, integrity_value = _normalized_integrity(explicit_integrity)
    elif explicit_sha256 is not None:
        algorithm = "sha256"
        digest_value = _normalized_hex_digest(explicit_sha256, algorithm=algorithm)
        integrity_value = _integrity_from_digest(algorithm, digest_value)
    elif explicit_sha512 is not None:
        algorithm = "sha512"
        digest_value = _normalized_hex_digest(explicit_sha512, algorithm=algorithm)
        integrity_value = _integrity_from_digest(algorithm, digest_value)
    else:
        if local_file is None:
            raise ValueError("npm-package requires --file, --integrity, --sha256, or --sha512")
        algorithm = "sha512"
        digest_value = checksum(local_file, algorithm)
        integrity_value = _integrity_from_digest(algorithm, digest_value)
    if local_file is not None:
        computed_digest = checksum(local_file, algorithm)
        if computed_digest != digest_value:
            option_name = "--integrity" if explicit_integrity is not None else f"--{algorithm}"
            raise ValueError(f"npm-package {option_name} does not match the bytes of --file")
    return algorithm, digest_value, integrity_value


def build_npm_package_registration(args: Namespace, bundle_dir: Path) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `npm-package` kind."""

    del bundle_dir  # reserved for future inventory-producing variants
    local_file = _resolved_local_file(getattr(args, "file", None))
    algorithm, digest_value, integrity_value = _resolved_integrity_material(
        local_file,
        explicit_integrity=getattr(args, "integrity", None),
        explicit_sha256=getattr(args, "sha256", None),
        explicit_sha512=getattr(args, "sha512", None),
    )
    artifact: dict[str, Any] = {
        "artifact_id": args.artifact_id,
        "kind": "npm-package",
        "filename": _resolved_filename(local_file, getattr(args, "filename", None)),
        "uri": _required_text(getattr(args, "uri", None), option_name="--uri"),
        "registry_url": _required_text(getattr(args, "registry_url", None), option_name="--registry-url"),
        "package_name": _required_text(getattr(args, "project_name", None), option_name="--package-name"),
        "version": _required_text(getattr(args, "package_version", None), option_name="--package-version"),
        "integrity": integrity_value,
        "checksums": {
            algorithm: {
                "value": digest_value,
            }
        },
    }
    if args.role:
        artifact["role"] = args.role
    checksum_uri = _optional_text(
        getattr(args, f"{algorithm}_uri", None),
        option_name=f"--{algorithm}-uri",
    )
    if checksum_uri is not None:
        artifact["checksums"][algorithm]["uri"] = checksum_uri
    attestation_repository = _optional_text(
        getattr(args, "attestation_repository", None),
        option_name="--attestation-repository",
    )
    if attestation_repository is not None:
        artifact["authenticity"] = {
            "scheme": "npm-provenance",
            "repository": attestation_repository,
        }
    if args.artifact_origin:
        artifact["artifact_origin"] = args.artifact_origin.strip()
    if args.git_commit_sha:
        artifact["git_commit_sha"] = args.git_commit_sha.strip()
    return ArtifactRegistrationResult(secondary_artifact=artifact)
