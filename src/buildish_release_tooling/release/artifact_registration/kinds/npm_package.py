# Copyright 2026 The Buildish Authors
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
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from buildish_release_tooling.release.artifact_registration.common import (
    common_artifact_metadata,
)
from buildish_release_tooling.release.artifact_registration.models import (
    ArtifactRegistrationResult,
)
from buildish_release_tooling.release.contracts import (
    NpmChecksums,
    NpmPackageSecondaryArtifact,
    NpmProvenanceAuth,
    Sha256ChecksumPayload,
    Sha512ChecksumPayload,
)
from buildish_release_tooling.release.path_validation import validate_simple_filename
from buildish_release_tooling.release.source_artifact import checksum

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_SHA512_PATTERN = re.compile(r"^[0-9a-fA-F]{128}$")
_SUPPORTED_INTEGRITY_ALGORITHMS = frozenset({"sha256", "sha512"})
_EXPECTED_DIGEST_LENGTHS = {
    "sha256": 32,
    "sha512": 64,
}


@dataclass(frozen=True)
class _NpmPublication:
    uri: str
    registry_url: str
    package_name: str
    version: str
    filename: str


def _resolved_local_file(path_text: str | None) -> Path | None:
    if path_text is None:
        return None
    local_path = Path(path_text).resolve()
    if not local_path.is_file():
        raise ValueError(f"artifact file does not exist: {local_path}")
    return local_path


def _resolved_filename(
    explicit_filename: str | None,
    *,
    explicit_uri: str | None,
    package_name: str,
    version: str,
) -> str:
    if explicit_filename is not None:
        filename = validate_simple_filename(
            explicit_filename,
            field_name="npm-package --filename",
        )
        if explicit_uri is not None:
            uri_filename = _filename_from_uri(explicit_uri)
            if uri_filename is not None and uri_filename != filename:
                raise ValueError("npm-package --filename does not match the filename encoded in --uri")
        return filename
    uri_filename = _filename_from_uri(explicit_uri) if explicit_uri is not None else None
    if uri_filename is not None:
        return validate_simple_filename(uri_filename, field_name="npm-package URI filename")
    return validate_simple_filename(
        _canonical_tarball_filename(package_name, version),
        field_name="npm-package filename",
    )


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


def _normalized_registry_url(raw_value: str | None, *, option_name: str) -> str:
    normalized = _required_text(raw_value, option_name=option_name).rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"npm-package {option_name} must be an https:// registry URL")
    return f"{normalized}/"


def _optional_registry_url(raw_value: str | None, *, option_name: str) -> str | None:
    if raw_value is None:
        return None
    return _normalized_registry_url(raw_value, option_name=option_name)


def _validated_package_name(package_name: str, *, option_name: str) -> str:
    if package_name.startswith("/") or package_name.endswith("/") or package_name.count("/") > 1:
        raise ValueError(f"npm-package {option_name} must be a valid npm package name")
    if "/" in package_name:
        scope, separator, name = package_name.partition("/")
        if not separator or not scope.startswith("@") or len(scope) == 1 or not name:
            raise ValueError(f"npm-package {option_name} must be a valid npm package name")
        return package_name
    if package_name.startswith("@"):
        raise ValueError(f"npm-package {option_name} must be a valid npm package name")
    return package_name


def _normalized_package_name(raw_value: str | None, *, option_name: str) -> str:
    return _validated_package_name(_required_text(raw_value, option_name=option_name), option_name=option_name)


def _optional_package_name(raw_value: str | None, *, option_name: str) -> str | None:
    if raw_value is None:
        return None
    return _validated_package_name(_optional_text(raw_value, option_name=option_name) or "", option_name=option_name)


def _filename_from_uri(uri: str) -> str | None:
    filename = Path(urlparse(uri).path).name
    if not filename:
        return None
    return filename


def _canonical_tarball_filename(package_name: str, version: str) -> str:
    return f"{package_name.rsplit('/', 1)[-1]}-{version}.tgz"


def _canonical_publication_uri(registry_url: str, package_name: str, version: str) -> str:
    return f"{registry_url.rstrip('/')}/{package_name}/-/{_canonical_tarball_filename(package_name, version)}"


def _parsed_canonical_publication(uri: str) -> _NpmPublication:
    parsed = urlparse(uri)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(
            "npm-package --uri must use a canonical npm tarball URL to derive registry and package metadata"
        )
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if len(path_segments) < 3 or path_segments[-2] != "-":
        raise ValueError(
            "npm-package --uri must use a canonical npm tarball URL to derive registry and package metadata"
        )
    filename = path_segments[-1]
    if not filename.endswith(".tgz"):
        raise ValueError(
            "npm-package --uri must use a canonical npm tarball URL to derive registry and package metadata"
        )
    package_segments = path_segments[:-2]
    package_leaf = package_segments[-1]
    filename_stem = filename.removesuffix(".tgz")
    expected_prefix = f"{package_leaf}-"
    if not filename_stem.startswith(expected_prefix) or filename_stem == expected_prefix:
        raise ValueError(
            "npm-package --uri must use a canonical npm tarball URL to derive registry and package metadata"
        )
    version = filename_stem.removeprefix(expected_prefix)
    if len(package_segments) >= 2 and package_segments[-2].startswith("@"):
        package_name = f"{package_segments[-2]}/{package_leaf}"
        registry_segments = package_segments[:-2]
    else:
        package_name = package_leaf
        registry_segments = package_segments[:-1]
    registry_path = "/".join(registry_segments)
    registry_url = f"{parsed.scheme}://{parsed.netloc}/"
    if registry_path:
        registry_url = f"{registry_url}{registry_path}/"
    return _NpmPublication(
        uri=uri,
        registry_url=registry_url,
        package_name=package_name,
        version=version,
        filename=filename,
    )


def _resolved_publication(
    args: Namespace,
) -> _NpmPublication:
    explicit_uri = _optional_text(getattr(args, "uri", None), option_name="--uri")
    explicit_registry_url = _optional_registry_url(getattr(args, "registry_url", None), option_name="--registry-url")
    explicit_package_name = _optional_package_name(getattr(args, "project_name", None), option_name="--package-name")
    explicit_version = _optional_text(getattr(args, "package_version", None), option_name="--package-version")
    explicit_filename = _optional_text(getattr(args, "filename", None), option_name="--filename")

    parsed_publication: _NpmPublication | None = None
    if explicit_uri is not None:
        try:
            parsed_publication = _parsed_canonical_publication(explicit_uri)
        except ValueError:
            parsed_publication = None
    if explicit_uri is None and (
        explicit_registry_url is None or explicit_package_name is None or explicit_version is None
    ):
        raise ValueError("npm-package requires --uri or the combination of --registry-url, --package-name, and --package-version")
    if explicit_uri is not None and (
        explicit_registry_url is None or explicit_package_name is None or explicit_version is None
    ) and parsed_publication is None:
        raise ValueError(
            "npm-package requires --registry-url, --package-name, and --package-version when --uri is not a canonical npm tarball URL"
        )

    registry_url = explicit_registry_url or (parsed_publication.registry_url if parsed_publication is not None else None)
    package_name = explicit_package_name or (parsed_publication.package_name if parsed_publication is not None else None)
    version = explicit_version or (parsed_publication.version if parsed_publication is not None else None)
    if registry_url is None or package_name is None or version is None:
        raise ValueError("npm-package requires complete registry, package, and version metadata")
    if parsed_publication is not None:
        if explicit_registry_url is not None and explicit_registry_url != parsed_publication.registry_url:
            raise ValueError("npm-package --registry-url does not match the canonical registry URL encoded in --uri")
        if explicit_package_name is not None and explicit_package_name != parsed_publication.package_name:
            raise ValueError("npm-package --package-name does not match the canonical package name encoded in --uri")
        if explicit_version is not None and explicit_version != parsed_publication.version:
            raise ValueError("npm-package --package-version does not match the canonical version encoded in --uri")
    uri = explicit_uri or _canonical_publication_uri(registry_url, package_name, version)
    if urlparse(uri).scheme != "https" or not urlparse(uri).netloc:
        raise ValueError("npm-package --uri must be an https:// URI")
    return _NpmPublication(
        uri=uri,
        registry_url=registry_url,
        package_name=package_name,
        version=version,
        filename=_resolved_filename(
            explicit_filename,
            explicit_uri=uri,
            package_name=package_name,
            version=version,
        ),
    )


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
    publication = _resolved_publication(args)
    algorithm, digest_value, integrity_value = _resolved_integrity_material(
        local_file,
        explicit_integrity=getattr(args, "integrity", None),
        explicit_sha256=getattr(args, "sha256", None),
        explicit_sha512=getattr(args, "sha512", None),
    )
    common_metadata = common_artifact_metadata(args)
    checksum_uri = _optional_text(
        getattr(args, f"{algorithm}_uri", None),
        option_name=f"--{algorithm}-uri",
    )
    if checksum_uri is not None:
        parsed_checksum_uri = urlparse(checksum_uri)
        if parsed_checksum_uri.scheme != "https" or not parsed_checksum_uri.netloc:
            raise ValueError(f"npm-package --{algorithm}-uri must be an https:// URI")
    attestation_repository = _optional_text(
        getattr(args, "attestation_repository", None),
        option_name="--attestation-repository",
    )
    checksums = (
        NpmChecksums(
            sha256=Sha256ChecksumPayload(value=digest_value, uri=checksum_uri),
        )
        if algorithm == "sha256"
        else NpmChecksums(
            sha512=Sha512ChecksumPayload(value=digest_value, uri=checksum_uri),
        )
    )
    return ArtifactRegistrationResult(
        secondary_artifact=NpmPackageSecondaryArtifact(
            artifact_id=args.artifact_id,
            role=common_metadata.role,
            artifact_origin=common_metadata.artifact_origin,
            git_commit_sha=common_metadata.git_commit_sha,
            reproducibility=common_metadata.reproducibility,
            filename=publication.filename,
            uri=publication.uri,
            registry_url=publication.registry_url,
            package_name=publication.package_name,
            version=publication.version,
            integrity=integrity_value,
            checksums=checksums,
            authenticity=(
                NpmProvenanceAuth(repository=attestation_repository)
                if attestation_repository is not None
                else None
            ),
        )
    )
