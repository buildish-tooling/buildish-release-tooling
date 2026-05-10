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

"""Schema-version-aware report and bundle loading for `inspect-repro`."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from apache_buildish_release_tooling.release.verification.schemas import (
    InspectionBundleManifestV1,
    VerifyRcReportV1,
)
from apache_buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_json_file_bounded,
)


def _load_json_object(path: Path, *, payload_label: str) -> dict[str, object]:
    try:
        raw_payload = read_json_file_bounded(path, max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES)
    except ValueError as exc:
        raise ValueError(f"{payload_label} is not valid JSON: {path}") from exc
    if not isinstance(raw_payload, dict):
        raise ValueError(f"{payload_label} is not a JSON object: {path}")
    return raw_payload


def resolve_contained_relative_path(root: Path, relative_path: str, *, field_name: str) -> Path:
    """Resolve a contract relative path while rejecting escapes from its declared root."""

    raw_path = Path(relative_path)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise ValueError(f"{field_name} must be relative and remain under {root}: {relative_path}")
    resolved_root = root.resolve(strict=False)
    resolved_path = (resolved_root / raw_path).resolve(strict=False)
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"{field_name} must be relative and remain under {root}: {relative_path}")
    return resolved_path


def load_supported_verify_rc_report(report_path: Path) -> VerifyRcReportV1:
    """Load and validate one supported verify-rc report JSON document."""

    raw_payload = _load_json_object(report_path, payload_label="verify-rc report")
    schema_version = raw_payload.get("schema_version")
    if schema_version != "1":
        raise ValueError(
            f"unsupported verify-rc report schema version: {schema_version!r}; supported: 1"
        )
    try:
        return VerifyRcReportV1.model_validate(raw_payload)
    except ValidationError as exc:
        raise ValueError(f"verify-rc report payload is malformed: {report_path}") from exc


def load_supported_bundle_manifest(
    *,
    bundle_root: Path,
    report: VerifyRcReportV1,
) -> InspectionBundleManifestV1 | None:
    """Load the inspection-bundle manifest referenced by one verify-rc report."""

    inspection_bundle = report.inspection_bundle
    if inspection_bundle is None:
        raise ValueError("verify-rc report does not reference an inspection bundle")
    manifest_relative_path = inspection_bundle.manifest_relative_path
    bundle_schema_version = inspection_bundle.bundle_schema_version
    if manifest_relative_path is None and bundle_schema_version is None:
        return None
    if manifest_relative_path is None or bundle_schema_version is None:
        raise ValueError(
            "inspection bundle contract fields are incomplete; expected both "
            "inspection_bundle.bundle_schema_version and inspection_bundle.manifest_relative_path"
        )
    if bundle_schema_version != "1":
        raise ValueError(
            f"unsupported inspection bundle schema version: {bundle_schema_version!r}; supported: 1"
        )
    manifest_path = resolve_contained_relative_path(
        bundle_root,
        manifest_relative_path,
        field_name="inspection_bundle.manifest_relative_path",
    )
    if not manifest_path.exists():
        raise ValueError(f"inspection bundle manifest does not exist: {manifest_path}")
    raw_payload = _load_json_object(
        manifest_path,
        payload_label="inspection bundle manifest",
    )
    if raw_payload.get("schema_version") != "1":
        raise ValueError(
            "unsupported inspection bundle manifest schema version: "
            f"{raw_payload.get('schema_version')!r}; supported: 1"
        )
    try:
        manifest = InspectionBundleManifestV1.model_validate(raw_payload)
    except ValidationError as exc:
        raise ValueError(f"inspection bundle manifest payload is malformed: {manifest_path}") from exc
    if manifest.report_schema_version != report.schema_version:
        raise ValueError(
            "inspection bundle manifest report schema version does not match the verify-rc report: "
            f"{manifest.report_schema_version!r} != {report.schema_version!r}"
        )
    if manifest.report_type != report.report_type:
        raise ValueError(
            "inspection bundle manifest report_type does not match the verify-rc report: "
            f"{manifest.report_type!r} != {report.report_type!r}"
        )
    return manifest
