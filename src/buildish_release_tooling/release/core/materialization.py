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

"""Provider-neutral binding between reviewed source and generated Git content."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator

from buildish_release_tooling.docs.documentation import RuntimeDerivedModel


def normalized_materialized_paths(paths: list[str]) -> list[str]:
    """Return canonical literal repository paths, never Git pathspecs or escapes."""
    result = []
    for value in paths:
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or value != path.as_posix()
            or any(part in {".", "..", ".git"} for part in path.parts)
            or value == "."
            or "\\" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or any(character in value for character in "*?[]:")
        ):
            raise ValueError(
                "materialized paths must be literal normalized repository-relative paths"
            )
        if value not in result:
            result.append(value)
    return sorted(result)


class MaterializationBinding(RuntimeDerivedModel):
    """Exact generated commit/tree and digest-bound transport, authorized separately by policy."""

    source_commit_sha: str = Field(description="Reviewed source S; sole parent of M.")
    commit_sha: str = Field(description="Exact materialized Action commit M.")
    tree_sha: str = Field(description="Exact Git tree of M.")
    paths: list[str] = Field(
        description="Trusted permitted generated paths, validated against component policy."
    )
    bundle_sha256: str = Field(
        description="SHA-256 of the retained Git bundle carrying M, with S as prerequisite."
    )

    @field_validator("source_commit_sha", "commit_sha", "tree_sha")
    @classmethod
    def _object_identity(cls, value: str) -> str:
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
            raise ValueError(
                "materialization requires full lowercase Git object identities"
            )
        return value

    @field_validator("bundle_sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("materialization bundle requires a SHA-256 digest")
        return value

    @field_validator("paths")
    @classmethod
    def _paths(cls, value: list[str]) -> list[str]:
        result = normalized_materialized_paths(value)
        if not result:
            raise ValueError("materialization requires permitted generated paths")
        return result

    @model_validator(mode="after")
    def _distinct(self) -> MaterializationBinding:
        if self.commit_sha == self.source_commit_sha:
            raise ValueError("materialized commit must differ from source commit")
        return self


def validate_tag_binding(
    source: str, target: str, binding: MaterializationBinding | None
) -> None:
    """Validate serialized identities without pretending to authorize component policy."""
    if binding is not None and binding.source_commit_sha != source:
        raise ValueError("materialization must bind the selected source commit")
    expected = source if binding is None else binding.commit_sha
    if target != expected:
        raise ValueError(
            "tag must target the selected source commit or its bound materialized commit"
        )
