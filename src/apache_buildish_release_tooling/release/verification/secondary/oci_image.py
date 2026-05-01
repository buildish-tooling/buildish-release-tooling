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

from pathlib import Path
from typing import Any

from apache_buildish_release_tooling.release.artifact_registration.kinds.oci_image import (
    _inspect_image_ref,
)
from apache_buildish_release_tooling.release.models import ComponentConfig, VerifyRcOverrideConfig
from apache_buildish_release_tooling.release.verification.inspection_bundle import (
    write_reproducibility_metadata,
)
from apache_buildish_release_tooling.release.verification.rebuild import (
    ResolvedRebuildProfile,
    canonical_recipe_payload,
    effective_execution_payload,
    override_payload,
    resolve_effective_rebuild_profile,
    run_host_direct_profile,
)

from .shared import required_non_empty_string


def verify_oci_image(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    work_dir: Path,
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    build_checks_allowed: bool,
    inspection_bundle_root: Path | None,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> dict[str, Any]:
    artifact_id = required_non_empty_string(artifact_entry, "artifact_id", source=manifest_url)
    registry = required_non_empty_string(artifact_entry, "registry", source=manifest_url)
    repository = required_non_empty_string(artifact_entry, "repository", source=manifest_url)
    declared_digest = required_non_empty_string(artifact_entry, "digest", source=manifest_url).lower()
    uri = required_non_empty_string(artifact_entry, "uri", source=manifest_url)
    image_ref = f"{registry}/{repository}@{declared_digest}"
    issues: list[str] = []
    live_digest: str | None = None
    live_platform_digests: list[dict[str, str]] = []
    try:
        _inspected_registry, _inspected_repository, live_digest, live_platform_digests = _inspect_image_ref(
            image_ref,
            log_commands=False,
        )
    except Exception as exc:
        issues.append(str(exc))
    digest_matches_manifest = live_digest == declared_digest if live_digest is not None else False
    if live_digest is not None and not digest_matches_manifest:
        issues.append(
            "oci-image digest does not match the signed manifest: "
            f"{live_digest} != {declared_digest}"
        )
    platform_digests_match: bool | None = None
    try:
        expected_platform_digests = _platform_digests_from_manifest(artifact_entry, source=manifest_url)
    except Exception as exc:
        issues.append(str(exc))
        expected_platform_digests = []
    if expected_platform_digests and live_digest is not None:
        expected_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in expected_platform_digests
        }
        live_by_platform = {
            entry["platform"]: entry["digest"]
            for entry in live_platform_digests
        }
        platform_digests_match = live_by_platform == expected_by_platform
        if not platform_digests_match:
            issues.append(
                "oci-image platform digests do not match the signed manifest: "
                f"{live_by_platform} != {expected_by_platform}"
            )
    reproducibility_verification: dict[str, Any] | None = None
    if build_checks_allowed and artifact_entry.get("reproducibility") is not None:
        reproducibility_verification = _verify_oci_image_reproducibility(
            artifact_entry,
            manifest_url=manifest_url,
            artifact_id=artifact_id,
            declared_digest=declared_digest,
            expected_platform_digests=expected_platform_digests,
            component_config=component_config,
            project_root=project_root,
            source_date_epoch=source_date_epoch,
            inspection_bundle_root=inspection_bundle_root,
            work_dir=work_dir / "reproducibility",
            profile_overrides=profile_overrides,
        )
        issues.extend(str(issue) for issue in reproducibility_verification.get("issues", []))
    return {
        "artifact_id": artifact_id,
        "kind": "oci-image",
        "verdict": "failed" if issues else "verified",
        "issues": issues,
        "uri": uri,
        "registry": registry,
        "repository": repository,
        "digest": declared_digest,
        "inspection": {
            "image_ref": image_ref,
            "digest_matches_manifest": digest_matches_manifest,
            "platform_digests_match": platform_digests_match,
            "platform_digests": live_platform_digests,
        },
        "reproducibility": reproducibility_verification,
    }


def _verify_oci_image_reproducibility(
    artifact_entry: dict[str, Any],
    *,
    manifest_url: str,
    artifact_id: str,
    declared_digest: str,
    expected_platform_digests: list[dict[str, str]],
    component_config: ComponentConfig | None,
    project_root: Path | None,
    source_date_epoch: int | None,
    inspection_bundle_root: Path | None,
    work_dir: Path,
    profile_overrides: VerifyRcOverrideConfig | None,
) -> dict[str, Any]:
    raw_reproducibility = artifact_entry.get("reproducibility")
    if not isinstance(raw_reproducibility, dict):
        return {
            "profile_id": "n/a",
            "verdict": "failed",
            "comparison_mode": "platform-digest",
            "canonical_recipe": None,
            "effective_execution": None,
            "override": {"applied": False},
            "matches_remote_bytes": None,
            "failure_class": "missing-profile",
            "evidence": [],
            "issues": [
                f"manifest secondary artifact does not declare a reproducibility profile: {artifact_id}"
            ],
        }
    profile_id = required_non_empty_string(raw_reproducibility, "profile_id", source=manifest_url)
    issues: list[str] = []
    matches_remote_bytes: bool | None = None
    comparison_mode = "platform-digest"
    failure_class: str | None = None
    evidence: list[dict[str, str]] = []
    image_ref: str | None = None
    rebuilt_digest: str | None = None
    rebuilt_platform_digests: list[dict[str, str]] = []
    resolved_profile: ResolvedRebuildProfile | None = None
    build_result = None
    if component_config is None:
        failure_class = failure_class or "missing-component-config"
        issues.append(
            f"build-based reproducibility for {artifact_id} requires --component-config to resolve profile {profile_id!r}"
        )
    if project_root is None:
        failure_class = failure_class or "missing-project-root"
        issues.append(
            f"build-based reproducibility for {artifact_id} requires one verified source checkout"
        )
    profile = None
    if not issues and component_config is not None:
        try:
            resolved_profile = resolve_effective_rebuild_profile(
                component_config,
                profile_id,
                expected_kinds=("oci-image",),
                profile_overrides=profile_overrides,
            )
            profile = resolved_profile.profile
            comparison_mode = required_non_empty_string(
                profile.comparison,
                "mode",
                source=f"verify_rc profile {profile_id!r}",
            )
            if comparison_mode not in {"platform-digest", "provenance-only"}:
                raise ValueError(
                    f"verify_rc profile {profile_id!r} must use comparison.mode 'platform-digest' or 'provenance-only' for oci-image artifacts"
                )
            image_ref = required_non_empty_string(
                profile.comparison,
                "image_ref",
                source=f"verify_rc profile {profile_id!r}",
            )
        except Exception as exc:
            failure_class = failure_class or "invalid-profile"
            issues.append(str(exc))
    if not issues and profile is not None and project_root is not None and image_ref is not None:
        try:
            build_result = run_host_direct_profile(
                profile_id=profile_id,
                profile=profile,
                project_root=project_root,
                work_dir=work_dir,
                source_date_epoch=source_date_epoch,
            )
            _rebuilt_registry, _rebuilt_repository, rebuilt_digest, rebuilt_platform_digests = _inspect_image_ref(
                image_ref,
                log_commands=False,
            )
            if comparison_mode == "platform-digest":
                if rebuilt_digest != declared_digest:
                    failure_class = failure_class or "digest-mismatch"
                    issues.append(
                        "oci-image reproducibility digest does not match the signed manifest: "
                        f"{rebuilt_digest} != {declared_digest}"
                    )
                if expected_platform_digests:
                    expected_by_platform = {
                        entry["platform"]: entry["digest"]
                        for entry in expected_platform_digests
                    }
                    rebuilt_by_platform = {
                        entry["platform"]: entry["digest"]
                        for entry in rebuilt_platform_digests
                    }
                    if rebuilt_by_platform != expected_by_platform:
                        failure_class = failure_class or "platform-digest-mismatch"
                        issues.append(
                            "oci-image reproducibility platform digests do not match the signed manifest: "
                            f"{rebuilt_by_platform} != {expected_by_platform}"
                        )
                matches_remote_bytes = not issues
        except Exception as exc:
            if failure_class is None:
                failure_class = "build-failed"
            issues.append(str(exc))
    if inspection_bundle_root is not None:
        metadata_path = write_reproducibility_metadata(
            inspection_bundle_root,
            artifact_id=artifact_id,
            payload={
                "artifact_id": artifact_id,
                "kind": "oci-image",
                "profile_id": profile_id,
                "comparison_mode": comparison_mode,
                "canonical_recipe": canonical_recipe_payload(resolved_profile),
                "effective_execution": effective_execution_payload(
                    build_result=build_result,
                    project_root=project_root,
                ),
                "override": override_payload(resolved_profile),
                "image_ref": image_ref,
                "declared_digest": declared_digest,
                "expected_platform_digests": expected_platform_digests,
                "rebuilt_digest": rebuilt_digest,
                "rebuilt_platform_digests": rebuilt_platform_digests,
                "matches_remote_bytes": matches_remote_bytes,
                "failure_class": failure_class,
                "issues": issues,
            },
        )
        evidence.append({"label": "comparison-metadata", "path": metadata_path})
    return {
        "profile_id": profile_id,
        "verdict": "failed" if issues else "verified",
        "comparison_mode": comparison_mode,
        "canonical_recipe": canonical_recipe_payload(resolved_profile),
        "effective_execution": effective_execution_payload(
            build_result=build_result,
            project_root=project_root,
        ),
        "override": override_payload(resolved_profile),
        "matches_remote_bytes": matches_remote_bytes,
        "failure_class": failure_class,
        "evidence": evidence,
        "issues": issues,
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
