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

"""Generic dispatch for secondary-publication evidence adapters."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from buildish_release_tooling.release.command_manifests import (
    AttachGitHubReleaseAssetsManifest,
)

from buildish_release_tooling.release.core.models import (
    PublicationReference,
    VerificationResultReference,
)
from buildish_release_tooling.release.manifests import ReleaseManifestV1
from buildish_release_tooling.release.publications._adapter import (
    AdapterEvidence,
    DURABLE_EVIDENCE_ASSET_PREFIX,
    DurableEvidenceAsset,
    FinalReleaseState,
    PublicationEvidenceAdapter,
)
from buildish_release_tooling.release.publications.pypi.evidence import (
    PYPI_EVIDENCE_ADAPTER,
)
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_json_object_file_bounded,
    read_pydantic_json_file_bounded,
)


def _validated_adapters(
    adapters: tuple[PublicationEvidenceAdapter, ...],
) -> tuple[PublicationEvidenceAdapter, ...]:
    dimensions = (
        "publication_actions",
        "verification_actions",
        "publication_target_kinds",
        "verification_result_kinds",
        "config_kinds",
    )
    keys: set[str] = set()
    owners: dict[tuple[str, str], str] = {}
    for adapter in adapters:
        if adapter.key in keys:
            raise ValueError(f"duplicate publication adapter key: {adapter.key}")
        keys.add(adapter.key)
        for dimension in dimensions:
            for discriminator in getattr(adapter, dimension):
                collision_key = (dimension, discriminator)
                prior = owners.get(collision_key)
                if prior is not None:
                    raise ValueError(
                        f"publication adapter discriminator collision for {dimension} "
                        f"{discriminator!r}: {prior}, {adapter.key}"
                    )
                owners[collision_key] = adapter.key
    return adapters


_ADAPTERS: tuple[PublicationEvidenceAdapter, ...] = _validated_adapters(
    (PYPI_EVIDENCE_ADAPTER,)
)


def _durable_evidence_assets(
    state: FinalReleaseState,
    result_paths: tuple[Path, ...],
) -> dict[str, DurableEvidenceAsset]:
    assets: dict[str, DurableEvidenceAsset] = {}
    for path in result_paths:
        result = read_pydantic_json_file_bounded(
            AttachGitHubReleaseAssetsManifest,
            path,
            max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
        )
        if (
            result.component != state.release.component.id
            or result.version != state.release.version
            or result.release_tag != state.final_tag.name
        ):
            raise ValueError(
                "verification-evidence publication does not match final-release state"
            )
        if set(result.primary_asset_names) != {
            asset.logical_name for asset in result.primary_assets
        }:
            raise ValueError(
                "verification-evidence publication has inconsistent primary assets"
            )
        if any(
            asset.kind != "verification-evidence" for asset in result.primary_assets
        ):
            raise ValueError(
                "verification-evidence publication was not created in immutable mode"
            )
        if any(
            not asset.logical_name.startswith(DURABLE_EVIDENCE_ASSET_PREFIX)
            for asset in result.primary_assets
        ):
            raise ValueError(
                "verification-evidence publication violates the reserved asset namespace"
            )
        if (
            result.generated_checksum_asset_names
            or result.generated_signature_asset_names
            or result.checksum_algorithms
            or result.gpg_fingerprint
        ):
            raise ValueError(
                "verification-evidence publication must not contain mutable sidecars"
            )
        base_uri = (
            f"https://github.com/{result.repository_slug}/releases/download/"
            f"{quote(result.release_tag, safe='')}"
        )
        for asset in result.primary_assets:
            digest = asset.digests.get("sha256")
            if (
                asset.logical_name in assets
                or digest is None
                or asset.size_bytes is None
            ):
                raise ValueError(
                    f"duplicate or unhashed verification-evidence asset: {asset.logical_name}"
                )
            assets[asset.logical_name] = DurableEvidenceAsset(
                uri=f"{base_uri}/{quote(asset.logical_name, safe='')}",
                sha256=digest,
                size_bytes=asset.size_bytes,
            )
    return assets


def _action(path: Path) -> str:
    payload = read_json_object_file_bounded(
        path,
        max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    )
    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise ValueError(f"secondary evidence has no action discriminator: {path}")
    return action


def _adapter_for_action(
    action: str, *, verification: bool
) -> PublicationEvidenceAdapter:
    matching = [
        adapter
        for adapter in _ADAPTERS
        if action
        in (
            adapter.verification_actions
            if verification
            else adapter.publication_actions
        )
    ]
    if len(matching) != 1:
        evidence_kind = "verification" if verification else "publication"
        raise ValueError(f"unsupported secondary {evidence_kind} action: {action}")
    return matching[0]


def _config_for_adapter(
    adapter: PublicationEvidenceAdapter,
    secondary_target_configs: tuple[object, ...],
) -> object:
    matching = [
        config
        for config in secondary_target_configs
        if getattr(config, "kind", None) in adapter.config_kinds
    ]
    if len(matching) != 1:
        kinds = ", ".join(sorted(adapter.config_kinds))
        raise ValueError(
            f"secondary evidence requires exactly one configured target of kind: {kinds}"
        )
    return matching[0]


def _configured_adapter(
    adapter: PublicationEvidenceAdapter,
    secondary_target_configs: tuple[object, ...],
) -> object | None:
    matching = [
        config
        for config in secondary_target_configs
        if getattr(config, "kind", None) in adapter.config_kinds
    ]
    if len(matching) > 1:
        kinds = ", ".join(sorted(adapter.config_kinds))
        raise ValueError(f"duplicate configured secondary target of kind: {kinds}")
    return matching[0] if matching else None


def configured_recoverable_evidence_asset_names(
    state: FinalReleaseState,
    secondary_target_configs: tuple[object, ...],
) -> frozenset[str]:
    """Derive exact reserved orphan names that configured adapters can reconcile."""

    names: set[str] = set()
    for adapter in _ADAPTERS:
        config = _configured_adapter(adapter, secondary_target_configs)
        if config is None:
            continue
        adapter_names = adapter.recoverable_evidence_asset_names(state, config)
        collisions = names & adapter_names
        if collisions:
            raise ValueError(
                "configured publication adapters have colliding evidence asset names: "
                + ", ".join(sorted(collisions))
            )
        names.update(adapter_names)
    return frozenset(names)


def _adapter_for_reference_kind(
    kind: str, *, verification: bool
) -> PublicationEvidenceAdapter:
    matching = [
        adapter
        for adapter in _ADAPTERS
        if kind
        in (
            adapter.verification_result_kinds
            if verification
            else adapter.publication_target_kinds
        )
    ]
    if len(matching) != 1:
        evidence_kind = "verification result" if verification else "publication"
        raise ValueError(
            f"unsupported or ambiguously owned secondary {evidence_kind} kind: {kind}"
        )
    return matching[0]


def compose_secondary_release_evidence(
    state: FinalReleaseState,
    release_state_path: Path,
    secondary_target_configs: tuple[object, ...],
    publication_results: tuple[Path, ...],
    verification_results: tuple[Path, ...],
    *,
    test_target_mode: bool,
    evidence_publication_results: tuple[Path, ...] = (),
) -> AdapterEvidence:
    """Dispatch adapter-owned command manifests and collect neutral evidence."""

    durable_evidence_assets = _durable_evidence_assets(
        state, evidence_publication_results
    )
    grouped_publications: dict[PublicationEvidenceAdapter, list[Path]] = {}
    grouped_verifications: dict[PublicationEvidenceAdapter, list[Path]] = {}
    for path in publication_results:
        grouped_publications.setdefault(
            _adapter_for_action(_action(path), verification=False), []
        ).append(path)
    for path in verification_results:
        grouped_verifications.setdefault(
            _adapter_for_action(_action(path), verification=True), []
        ).append(path)

    publications: list[PublicationReference] = []
    verifications: list[VerificationResultReference] = []
    for adapter in _ADAPTERS:
        adapter_publications = tuple(grouped_publications.get(adapter, ()))
        adapter_verifications = tuple(grouped_verifications.get(adapter, ()))
        adapter_config = _configured_adapter(adapter, secondary_target_configs)
        if (
            adapter_config is None
            and not adapter_publications
            and not adapter_verifications
        ):
            continue
        if adapter_config is None:
            adapter_config = _config_for_adapter(adapter, secondary_target_configs)
        evidence = adapter.compose(
            state,
            release_state_path,
            adapter_config,
            adapter_publications,
            adapter_verifications,
            durable_evidence_assets,
            test_target_mode=test_target_mode,
        )
        publications.extend(evidence.publications)
        verifications.extend(evidence.verification_results)
    return AdapterEvidence(tuple(publications), tuple(verifications))


def validate_secondary_release_evidence(
    manifest: ReleaseManifestV1,
    state: FinalReleaseState,
    secondary_target_configs: tuple[object, ...],
    *,
    test_target_mode: bool,
) -> None:
    """Revalidate all adapter-owned post-state evidence in a stable manifest."""

    grouped_publications: dict[
        PublicationEvidenceAdapter, list[PublicationReference]
    ] = {}
    for publication in manifest.secondary_publications:
        adapter = _adapter_for_reference_kind(
            publication.target_kind,
            verification=False,
        )
        grouped_publications.setdefault(adapter, []).append(publication)
    grouped_verifications: dict[
        PublicationEvidenceAdapter, list[VerificationResultReference]
    ] = {}
    for result in manifest.verification_results[len(state.verification_results) :]:
        adapter = _adapter_for_reference_kind(result.kind, verification=True)
        grouped_verifications.setdefault(adapter, []).append(result)
    adapters_to_validate = set(grouped_publications) | set(grouped_verifications)
    adapters_to_validate.update(
        adapter
        for adapter in _ADAPTERS
        if _configured_adapter(adapter, secondary_target_configs) is not None
    )
    for adapter in adapters_to_validate:
        adapter.validate_manifest(
            manifest,
            state,
            _config_for_adapter(adapter, secondary_target_configs),
            tuple(grouped_publications.get(adapter, ())),
            tuple(grouped_verifications.get(adapter, ())),
            test_target_mode=test_target_mode,
        )
