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

"""OCI image secondary-artifact verification."""

from __future__ import annotations

from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    _inspect_image_ref,
)

from .shared import required_non_empty_string


def verify_oci_image(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    registry = required_non_empty_string(artifact_entry, "registry", source=manifest_url)
    repository = required_non_empty_string(artifact_entry, "repository", source=manifest_url)
    declared_digest = required_non_empty_string(artifact_entry, "digest", source=manifest_url).lower()
    uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    image_ref = f"{registry}/{repository}@{declared_digest}"
    _inspected_registry, _inspected_repository, live_digest, live_platform_digests = _inspect_image_ref(image_ref)
    if live_digest != declared_digest:
        raise ValueError(
            "oci-image digest does not match the signed manifest: "
            f"{live_digest} != {declared_digest}"
        )
    expected_platform_digests = _platform_digests_from_manifest(artifact_entry, source=manifest_url)
    platform_digests_match = True
    if expected_platform_digests:
        expected_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in expected_platform_digests
        }
        live_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in live_platform_digests
        }
        if live_by_platform != expected_by_platform:
            raise ValueError(
                "oci-image platform digests do not match the signed manifest: "
                f"{live_by_platform} != {expected_by_platform}"
            )
    return {
        "artifact_id": artifact_id,
        "kind": "oci-image",
        "verdict": "verified",
        "uri": uri,
        "registry": registry,
        "repository": repository,
        "digest": declared_digest,
        "inspection": {
            "image_ref": image_ref,
            "digest_matches_manifest": True,
            "platform_digests_match": platform_digests_match,
            "platform_digests": live_platform_digests,
        },
    }


def _platform_digests_from_manifest(
    artifact_entry: dict[str, Any],
    *,
    source: str,
) -> list[dict[str, str]]:
    raw_entries = artifact_entry.get("platform_digests")
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        raise ValueError(f"oci-image platform_digests must be a list: {source}")
    entries: list[dict[str, str]] = []
    seen_platforms: set[str] = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError(f"oci-image platform_digests entries must be objects: {source}")
        platform = required_non_empty_string(raw_entry, "platform", source=source)
        if platform in seen_platforms:
            raise ValueError(f"oci-image platform declared more than once in manifest: {platform}")
        seen_platforms.add(platform)
        digest_value = required_non_empty_string(raw_entry, "digest", source=source).lower()
        entries.append({"platform": platform, "digest": digest_value})
    return entries
