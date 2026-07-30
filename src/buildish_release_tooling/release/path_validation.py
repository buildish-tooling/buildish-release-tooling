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

"""Shared path validators for release metadata."""

from __future__ import annotations

from pathlib import Path


def validate_simple_filename(value: str, *, field_name: str) -> str:
    """Return a trimmed file name that cannot name a parent or nested path."""

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.name != normalized or ".." in candidate.parts:
        raise ValueError(f"{field_name} must be a simple file name")
    return normalized


def validate_project_relative_path(value: str, *, field_name: str) -> str:
    """Return a trimmed project-relative path that cannot escape the project root."""

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError(f"{field_name} must be relative to the project root")
    if ".." in candidate.parts:
        raise ValueError(f"{field_name} must not escape the project root")
    return normalized


def resolve_project_relative_path(root: Path, value: str, *, field_name: str) -> Path:
    """Resolve a validated project-relative path below a project root."""

    root_path = root.resolve()
    candidate = (root_path / validate_project_relative_path(value, field_name=field_name)).resolve()
    if not candidate.is_relative_to(root_path):
        raise ValueError(f"{field_name} must not escape the project root")
    return candidate
