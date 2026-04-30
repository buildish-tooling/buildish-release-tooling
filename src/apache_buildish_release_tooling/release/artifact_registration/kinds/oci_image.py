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

"""Handler for the `oci-image` artifact-registration kind."""

from __future__ import annotations

import json
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
from apache_buildish_release_tooling.release.contracts import OciImageSecondaryArtifact
from apache_buildish_release_tooling.release.process import (
    CommandExecutionError,
    run_logged_command,
)

_DIGEST_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+.-]*:[0-9a-fA-F]{32,}$")


def _required_text(raw_value: object | None, *, option_name: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"oci-image requires {option_name}")
    return raw_value.strip()


def _optional_text(raw_value: object | None, *, option_name: str) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ValueError(f"oci-image {option_name} must be a string")
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"oci-image {option_name} must not be empty")
    return normalized


def _normalized_registry(raw_value: object | None) -> str:
    registry = _required_text(raw_value, option_name="--registry")
    if "://" in registry or "/" in registry:
        raise ValueError("oci-image --registry must be a registry host without a scheme or path")
    return registry


def _normalized_repository(raw_value: object | None) -> str:
    repository = _required_text(raw_value, option_name="--repository")
    if "://" in repository or repository.startswith("/") or repository.endswith("/") or "@" in repository:
        raise ValueError(
            "oci-image --repository must be a slash-delimited image repository without a scheme or digest"
        )
    return repository


def _normalized_digest(raw_value: object | None, *, option_name: str) -> str:
    digest = _required_text(raw_value, option_name=option_name).lower()
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise ValueError(f"oci-image {option_name} must be an OCI content digest like sha256:<hex>")
    return digest


def _platform_digest_entries(raw_values: list[str] | None) -> list[dict[str, str]]:
    if not raw_values:
        return []
    entries: list[dict[str, str]] = []
    seen_platforms: set[str] = set()
    for raw_entry in raw_values:
        if "=" not in raw_entry:
            raise ValueError("oci-image --platform-digest must use the form <platform>=<digest>")
        platform_value, digest_value = raw_entry.split("=", 1)
        platform = platform_value.strip()
        if not platform or any(character.isspace() for character in platform):
            raise ValueError("oci-image --platform-digest platform must be a non-empty token like linux/amd64")
        if platform in seen_platforms:
            raise ValueError(f"oci-image --platform-digest declared platform more than once: {platform}")
        seen_platforms.add(platform)
        entries.append(
            {
                "platform": platform,
                "digest": _normalized_digest(digest_value, option_name="--platform-digest"),
            }
        )
    return entries


def _default_reference_uri(registry: str, repository: str, digest: str) -> str:
    return f"oci://{registry}/{repository}@{digest}"


def _normalized_image_ref(raw_value: object | None) -> str:
    image_ref = _required_text(raw_value, option_name="--image-ref")
    if "://" in image_ref:
        raise ValueError("oci-image --image-ref must be a container image reference without a URI scheme")
    return image_ref


def _derived_registry_and_repository(image_ref: str) -> tuple[str, str]:
    main_part, _at_sign, _digest_value = image_ref.partition("@")
    last_slash = main_part.rfind("/")
    last_colon = main_part.rfind(":")
    name_part = main_part if last_colon <= last_slash else main_part[:last_colon]
    if not name_part:
        raise ValueError(f"oci-image --image-ref is not a valid image reference: {image_ref}")
    first_component, separator, remainder = name_part.partition("/")
    if separator and ("." in first_component or ":" in first_component or first_component == "localhost"):
        if not remainder:
            raise ValueError(f"oci-image --image-ref must include a repository path: {image_ref}")
        return first_component, remainder
    repository = name_part if separator else f"library/{name_part}"
    return "docker.io", repository


def _platform_string(platform_payload: dict[str, Any]) -> str | None:
    os_name = platform_payload.get("os")
    architecture = platform_payload.get("architecture")
    if not isinstance(os_name, str) or not os_name or os_name == "unknown":
        return None
    if not isinstance(architecture, str) or not architecture or architecture == "unknown":
        return None
    variant = platform_payload.get("variant")
    if isinstance(variant, str) and variant:
        return f"{os_name}/{architecture}/{variant}"
    return f"{os_name}/{architecture}"


def _derived_platform_digest_entries(manifest_payload: dict[str, Any]) -> list[dict[str, str]]:
    manifest_entries = manifest_payload.get("manifests")
    if not isinstance(manifest_entries, list):
        return []
    platform_digests: list[dict[str, str]] = []
    seen_platforms: set[str] = set()
    for manifest_entry in manifest_entries:
        if not isinstance(manifest_entry, dict):
            continue
        platform_payload = manifest_entry.get("platform")
        if not isinstance(platform_payload, dict):
            continue
        platform = _platform_string(platform_payload)
        if platform is None:
            continue
        if platform in seen_platforms:
            raise ValueError(f"oci-image registry manifest declared platform more than once: {platform}")
        seen_platforms.add(platform)
        platform_digests.append(
            {
                "platform": platform,
                "digest": _normalized_digest(manifest_entry.get("digest"), option_name="registry manifest digest"),
            }
        )
    return platform_digests


def _inspect_image_ref(
    image_ref: str,
    *,
    log_commands: bool = True,
) -> tuple[str, str, str, list[dict[str, str]]]:
    try:
        completed = run_logged_command(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                "--format",
                "{{json .Manifest}}",
                image_ref,
            ],
            log_command=log_commands,
        )
    except CommandExecutionError as exc:
        raise ValueError(f"oci-image failed to inspect --image-ref {image_ref}: {exc}") from exc
    try:
        manifest_payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"oci-image docker buildx imagetools inspect returned invalid JSON for --image-ref {image_ref}"
        ) from exc
    if not isinstance(manifest_payload, dict):
        raise ValueError(
            f"oci-image docker buildx imagetools inspect did not return a manifest object for --image-ref {image_ref}"
        )
    registry, repository = _derived_registry_and_repository(image_ref)
    digest = _normalized_digest(manifest_payload.get("digest"), option_name="registry manifest digest")
    return registry, repository, digest, _derived_platform_digest_entries(manifest_payload)


def _manual_or_derived_details(args: Namespace) -> tuple[str, str, str, list[dict[str, str]]]:
    image_ref = getattr(args, "image_ref", None)
    if image_ref is not None:
        if any(
            (
                getattr(args, "registry", None),
                getattr(args, "repository", None),
                getattr(args, "digest", None),
                getattr(args, "platform_digests", None),
            )
        ):
            raise ValueError(
                "oci-image --image-ref cannot be combined with --registry, --repository, --digest, or --platform-digest"
            )
        return _inspect_image_ref(_normalized_image_ref(image_ref))
    return (
        _normalized_registry(getattr(args, "registry", None)),
        _normalized_repository(getattr(args, "repository", None)),
        _normalized_digest(getattr(args, "digest", None), option_name="--digest"),
        _platform_digest_entries(getattr(args, "platform_digests", None)),
    )


def build_oci_image_registration(args: Namespace, bundle_dir: Path) -> ArtifactRegistrationResult:
    """Build one typed secondary-artifact fragment for the `oci-image` kind."""

    del bundle_dir  # reserved for future inventory-producing variants
    registry, repository, digest, platform_digests = _manual_or_derived_details(args)
    uri = _optional_text(getattr(args, "uri", None), option_name="--uri")
    artifact: dict[str, Any] = {
        "artifact_id": args.artifact_id,
        "kind": "oci-image",
        "uri": uri or _default_reference_uri(registry, repository, digest),
        "registry": registry,
        "repository": repository,
        "digest": digest,
    }
    if platform_digests:
        artifact["platform_digests"] = platform_digests
    apply_common_artifact_metadata(artifact, args)
    return ArtifactRegistrationResult(
        secondary_artifact=OciImageSecondaryArtifact.model_validate(artifact)
    )
