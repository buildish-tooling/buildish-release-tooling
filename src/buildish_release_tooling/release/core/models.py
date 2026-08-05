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

"""Provider-neutral immutable release identities and references."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from buildish_release_tooling.docs.documentation import RuntimeDerivedModel


MAX_RELEASE_NOTES_BYTES = 256 * 1024


def _validate_utc_rfc3339_timestamp(value: str) -> str:
    """Require a real RFC 3339 timestamp expressed in UTC with a trailing Z."""

    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ValueError("timestamp must be a valid UTC RFC 3339 value") from exc
    return value


UtcRfc3339Timestamp = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
    ),
    AfterValidator(_validate_utc_rfc3339_timestamp),
]


def validate_release_notes_source_path(value: str) -> str:
    """Validate one normalized repository-relative release-note path."""

    if (
        not value
        or value != value.strip()
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(
            "release notes path must be a normalized repository-relative path"
        )
    path = PurePosixPath(value)
    if value != path.as_posix():
        raise ValueError(
            "release notes path must be a normalized repository-relative path"
        )
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("release notes path must not escape the repository root")
    return value


class ComponentIdentity(RuntimeDerivedModel):
    """Stable machine and human identity of one released component."""

    id: str = Field(description="Stable machine identifier of the component.")
    display_name: str = Field(description="Human-facing component name.")


class ReleaseIdentity(RuntimeDerivedModel):
    """Stable identity of one component version."""

    component: ComponentIdentity = Field(description="Released component identity.")
    version: str = Field(description="Exact component version.")


class SourceRevision(RuntimeDerivedModel):
    """Exact source repository revision selected for a release."""

    repository: str = Field(
        description="Provider-neutral source repository identity or URL."
    )
    commit_sha: str = Field(description="Exact source commit identifier.")
    source_ref: str | None = Field(
        default=None,
        description="Optional authored or resolved source ref that selected the commit.",
    )


class ReleaseNotes(RuntimeDerivedModel):
    """Exact human-readable notes selected from one release source revision."""

    source_path: str = Field(
        description="Repository-relative path of the notes in the selected source revision."
    )
    sha256: str = Field(
        description="Lowercase SHA-256 of the exact UTF-8 Markdown bytes."
    )
    markdown: str = Field(description="Exact non-empty UTF-8 Markdown fragment.")

    @field_validator("source_path")
    @classmethod
    def _validate_source_path(cls, value: str) -> str:
        return validate_release_notes_source_path(value)

    @model_validator(mode="after")
    def _validate_exact_markdown(self) -> ReleaseNotes:
        if not self.markdown.strip():
            raise ValueError("release notes Markdown must not be empty")
        markdown_bytes = self.markdown.encode("utf-8")
        if len(markdown_bytes) > MAX_RELEASE_NOTES_BYTES:
            raise ValueError(
                f"release notes Markdown exceeds the {MAX_RELEASE_NOTES_BYTES}-byte limit"
            )
        if "\x00" in self.markdown:
            raise ValueError("release notes Markdown must not contain NUL characters")
        expected_digest = hashlib.sha256(markdown_bytes).hexdigest()
        if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
            raise ValueError("release notes sha256 must be a lowercase SHA-256 digest")
        if self.sha256 != expected_digest:
            raise ValueError("release notes sha256 does not match the Markdown bytes")
        return self


class TagIdentity(RuntimeDerivedModel):
    """Immutable identity of one Git tag and its exact target commit."""

    name: str = Field(description="Exact tag name.")
    target_commit: str = Field(description="Exact commit targeted by the tag.")
    purpose: Literal["candidate", "final", "moving-alias"] = Field(
        description="Provider-neutral purpose of the tag."
    )


class CandidateIdentity(RuntimeDerivedModel):
    """Deterministic identity of one exact release candidate."""

    release: ReleaseIdentity = Field(
        description="Release version proposed by the candidate."
    )
    label: str = Field(description="Candidate series label.")
    number: int = Field(ge=0, description="Candidate sequence number.")
    tag: TagIdentity = Field(description="Exact immutable candidate tag.")
    stable_id: str | None = Field(
        default=None,
        description="Deterministic candidate identifier independent of provider object IDs.",
    )

    @model_validator(mode="after")
    def _derive_and_validate_stable_id(self) -> CandidateIdentity:
        expected = (
            f"{self.release.component.id}:{self.release.version}:"
            f"{self.label}:{self.number}:{self.tag.name}"
        )
        if self.stable_id is None:
            self.stable_id = expected
        elif self.stable_id != expected:
            raise ValueError("candidate stable_id does not match its exact identity")
        if self.tag.purpose != "candidate":
            raise ValueError("candidate tag purpose must be candidate")
        return self


class ArtifactReference(RuntimeDerivedModel):
    """Immutable logical artifact identity, digests, size, and locations."""

    kind: str = Field(description="Artifact kind discriminator.")
    logical_name: str = Field(description="Stable logical artifact name.")
    digests: dict[str, str] = Field(
        default_factory=dict,
        description="Immutable content digests keyed by algorithm.",
    )
    size_bytes: int | None = Field(
        default=None, ge=0, description="Artifact size in bytes."
    )
    locations: list[str] = Field(
        default_factory=list,
        description="Known immutable or candidate publication locations.",
    )

    @field_validator("digests")
    @classmethod
    def _validate_digests(cls, value: dict[str, str]) -> dict[str, str]:
        for algorithm, digest in value.items():
            if not algorithm.strip() or re.fullmatch(r"[0-9a-f]+", digest) is None:
                raise ValueError(
                    "artifact digests require a named algorithm and lowercase hex"
                )
        return value


class PublicationReference(RuntimeDerivedModel):
    """Reference to one provider or foundation publication result."""

    target_kind: str = Field(description="Selected publication target discriminator.")
    uri: str = Field(description="Primary URI of the publication result.")
    immutable_id: str | None = Field(
        default=None,
        description="Optional provider-issued immutable publication identifier.",
    )


class VerificationResultReference(RuntimeDerivedModel):
    """Reference to one machine-readable verification result."""

    kind: str = Field(description="Verification result kind.")
    uri: str = Field(description="URI of the verification result.")
    digest: str | None = Field(
        default=None, description="Optional result document digest."
    )
    claims: dict[str, str] = Field(
        default_factory=dict,
        description="Verified identity or subject claims bound to the result document.",
    )


class ToolingInvocationProvenance(RuntimeDerivedModel):
    """Provider-neutral tooling revision and invocation metadata."""

    version: str | None = Field(default=None, description="Installed tooling version.")
    revision: str | None = Field(
        default=None, description="Exact tooling source revision."
    )
    invocation_id: str | None = Field(
        default=None,
        description="Optional workflow- or caller-issued invocation identifier.",
    )
