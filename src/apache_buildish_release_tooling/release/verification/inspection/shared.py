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

"""Shared helpers for inspect-repro analyzers."""

from __future__ import annotations

import difflib
import json
from json import JSONDecodeError
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from apache_buildish_release_tooling.release.contracts import InspectionEvidenceReference

_MAX_INLINE_TEXT_DIFF_LINES = 12
_MAX_INLINE_TEXT_BYTES = 65536
_ModelT = TypeVar("_ModelT", bound=BaseModel)


def evidence_path(
    evidence: list[InspectionEvidenceReference],
    *,
    label: str,
    bundle_root: Path,
) -> Path | None:
    """Resolve one retained evidence file by exact label."""

    for reference in evidence:
        if reference.label == label:
            candidate_path = bundle_root / reference.path
            if candidate_path.exists():
                return candidate_path
    return None


def first_matching_evidence_path(
    evidence: list[InspectionEvidenceReference],
    *,
    label_prefix: str,
    bundle_root: Path,
) -> Path | None:
    """Resolve the first retained evidence file whose label matches one prefix."""

    for reference in evidence:
        if not reference.label.startswith(label_prefix):
            continue
        candidate_path = bundle_root / reference.path
        if candidate_path.exists():
            return candidate_path
    return None


def first_differing_byte(left: bytes, right: bytes) -> int:
    """Return the first differing byte offset between two byte strings."""

    shared_length = min(len(left), len(right))
    for index in range(shared_length):
        if left[index] != right[index]:
            return index
    return shared_length


def text_diff(left: bytes, right: bytes) -> list[str]:
    """Return a small inline unified diff when both payloads look like UTF-8 text."""

    if len(left) > _MAX_INLINE_TEXT_BYTES or len(right) > _MAX_INLINE_TEXT_BYTES:
        return []
    try:
        left_text = left.decode("utf-8")
        right_text = right.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if "\x00" in left_text or "\x00" in right_text:
        return []
    diff_lines = list(
        difflib.unified_diff(
            left_text.splitlines(),
            right_text.splitlines(),
            fromfile="staged",
            tofile="rebuilt",
            lineterm="",
        )
    )
    return diff_lines[:_MAX_INLINE_TEXT_DIFF_LINES]


def load_inspection_metadata_model(
    model_type: type[_ModelT],
    metadata_path: Path,
    *,
    payload_label: str,
) -> _ModelT:
    """Load one retained inspection metadata document with a direct fail-closed error."""

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ValueError(f"{payload_label} is not valid JSON: {metadata_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{payload_label} is not a JSON object: {metadata_path}")
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"{payload_label} payload is malformed: {metadata_path}") from exc
