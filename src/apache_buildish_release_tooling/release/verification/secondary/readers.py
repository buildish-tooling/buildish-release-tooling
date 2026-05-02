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

"""Tolerant manifest and inventory readers for secondary-artifact verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from apache_buildish_release_tooling.release.contracts import (
    AnySecondaryArtifact,
    RcVoteManifestReadV1,
    SecondaryArtifactEnvelopeRead,
    StrictSecondaryArtifactAdapter,
)


class _ExternalPayloadReadModel(BaseModel):
    """Base model for tolerant external JSON fragments used by secondary verifiers."""

    model_config = ConfigDict(extra="allow")


class _RawVoteMaterialsRead(_ExternalPayloadReadModel):
    secondary_artifacts: list[AnySecondaryArtifact | SecondaryArtifactEnvelopeRead] | None = None


class _RawManifestRead(_ExternalPayloadReadModel):
    vote_materials: _RawVoteMaterialsRead | None = None


class _RawInventoryEntryRead(_ExternalPayloadReadModel):
    path: str | None = None
    size_bytes: int | None = None
    sha512: str | None = None


class _RawInventoryRead(_ExternalPayloadReadModel):
    schema_version: str | None = None
    inventory_type: str | None = None
    artifact_id: str | None = None
    staging_repository_id: str | None = None
    base_url: str | None = None
    entries: list[_RawInventoryEntryRead] | None = None


@dataclass(frozen=True)
class MalformedSecondaryArtifactEntry:
    """One malformed secondary-artifact manifest entry preserved for fail-closed reporting."""

    raw_payload: SecondaryArtifactEnvelopeRead | object
    artifact_id: str | None = None
    declared_kind: str | None = None


SecondaryArtifactEntry = AnySecondaryArtifact | MalformedSecondaryArtifactEntry


def secondary_artifact_entries(
    manifest_payload: RcVoteManifestReadV1 | Mapping[str, object],
    *,
    source: str,
) -> list[SecondaryArtifactEntry]:
    """Return validated secondary-artifact entries while preserving malformed ones."""

    secondary_artifacts: list[AnySecondaryArtifact | SecondaryArtifactEnvelopeRead] | None
    if isinstance(manifest_payload, RcVoteManifestReadV1):
        secondary_artifacts = list(manifest_payload.vote_materials.secondary_artifacts)
    else:
        raw_manifest = _RawManifestRead.model_validate(manifest_payload)
        vote_materials = raw_manifest.vote_materials
        if vote_materials is None:
            raise ValueError(f"manifest is missing vote_materials: {source}")
        secondary_artifacts = vote_materials.secondary_artifacts
        if secondary_artifacts is None:
            raise ValueError(f"manifest secondary_artifacts must be a list: {source}")
    entries: list[SecondaryArtifactEntry] = []
    for raw_entry in secondary_artifacts:
        if isinstance(raw_entry, SecondaryArtifactEnvelopeRead):
            try:
                entries.append(
                    StrictSecondaryArtifactAdapter.validate_python(
                        raw_entry.model_dump(mode="json", exclude_none=True)
                    )
                )
                continue
            except Exception:
                entries.append(
                    MalformedSecondaryArtifactEntry(
                        raw_payload=raw_entry,
                        artifact_id=raw_entry.artifact_id.strip()
                        if isinstance(raw_entry.artifact_id, str) and raw_entry.artifact_id.strip()
                        else None,
                        declared_kind=raw_entry.kind.strip()
                        if isinstance(raw_entry.kind, str) and raw_entry.kind.strip()
                        else None,
                    )
                )
                continue
        if isinstance(raw_entry, BaseModel):
            entries.append(raw_entry)
    return entries
