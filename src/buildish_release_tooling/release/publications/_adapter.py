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

"""Internal secondary-publication adapter contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from buildish_release_tooling.release.core.models import (
    PublicationReference,
    VerificationResultReference,
)
from buildish_release_tooling.release.core.state import (
    DirectReleaseState,
    PromotionState,
)
from buildish_release_tooling.release.manifests import ReleaseManifestV1

FinalReleaseState = DirectReleaseState | PromotionState
DURABLE_EVIDENCE_ASSET_PREFIX = "buildish-verification-evidence--"


@dataclass(frozen=True, slots=True)
class AdapterEvidence:
    """Provider-neutral evidence produced by one publication adapter."""

    publications: tuple[PublicationReference, ...] = ()
    verification_results: tuple[VerificationResultReference, ...] = ()


@dataclass(frozen=True, slots=True)
class DurableEvidenceAsset:
    """One exact verification-evidence document retained by the primary publisher."""

    uri: str
    sha256: str
    size_bytes: int


class PublicationEvidenceAdapter(Protocol):
    """Adapter hooks used by generic final-manifest composition and validation."""

    @property
    def key(self) -> str:
        """Stable internal registry key for this adapter."""

    @property
    def publication_actions(self) -> frozenset[str]:
        """Command actions that produce publication results for this adapter."""

    @property
    def verification_actions(self) -> frozenset[str]:
        """Command actions that produce verification results for this adapter."""

    @property
    def publication_target_kinds(self) -> frozenset[str]:
        """Neutral publication target kinds owned by this adapter."""

    @property
    def verification_result_kinds(self) -> frozenset[str]:
        """Neutral verification-result kinds owned by this adapter."""

    @property
    def config_kinds(self) -> frozenset[str]:
        """Authored secondary-target discriminators owned by this adapter."""

    def compose(
        self,
        state: FinalReleaseState,
        release_state_path: Path,
        config: object,
        publication_results: tuple[Path, ...],
        verification_results: tuple[Path, ...],
        durable_evidence_assets: Mapping[str, DurableEvidenceAsset],
        *,
        test_target_mode: bool,
    ) -> AdapterEvidence:
        """Validate adapter manifests and convert them to neutral references."""

    def recoverable_evidence_asset_names(
        self,
        state: FinalReleaseState,
        config: object,
    ) -> frozenset[str]:
        """Derive reserved durable-evidence names that a full rerun may reconcile."""

    def validate_manifest(
        self,
        manifest: ReleaseManifestV1,
        state: FinalReleaseState,
        config: object,
        publications: tuple[PublicationReference, ...],
        verification_results: tuple[VerificationResultReference, ...],
        *,
        test_target_mode: bool,
    ) -> None:
        """Revalidate adapter-owned evidence in a stable release manifest."""
