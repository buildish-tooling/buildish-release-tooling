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

"""Compose and validate PyPI publication and PEP 740 provenance evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

from buildish_release_tooling.release.core.models import (
    PublicationReference,
    VerificationResultReference,
)
from buildish_release_tooling.release.manifests import ReleaseManifestV1
from buildish_release_tooling.release.publications._adapter import (
    AdapterEvidence,
    DurableEvidenceAsset,
    FinalReleaseState,
    PublicationEvidenceAdapter,
)
from buildish_release_tooling.release.publications.pypi.config import (
    PyPiPublicationConfig,
)
from buildish_release_tooling.release.publications.pypi.distributions import (
    is_project_distribution,
    normalized_pypi_version,
    pypi_publish_attestation_asset_name,
)
from buildish_release_tooling.release.publications.pypi.manifests import (
    VerifyPyPiAttestationsManifest,
    VerifyPyPiPublicationManifest,
)
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)
from buildish_release_tooling.shared.io import hash_file


@dataclass(frozen=True, slots=True)
class PyPiEvidenceAdapter:
    """Translate PyPI-owned command evidence to and from neutral references."""

    key: str = "pypi"
    publication_actions: frozenset[str] = frozenset({"verify-pypi-publication"})
    verification_actions: frozenset[str] = frozenset({"verify-pypi-attestations"})
    publication_target_kinds: frozenset[str] = frozenset({"pypi"})
    verification_result_kinds: frozenset[str] = frozenset({"pypi-publish-attestation"})
    config_kinds: frozenset[str] = frozenset({"pypi"})

    def recoverable_evidence_asset_names(
        self,
        state: FinalReleaseState,
        config: object,
    ) -> frozenset[str]:
        """Derive exact reserved asset names from the bound distribution inventory."""

        if not isinstance(config, PyPiPublicationConfig):
            raise TypeError("PyPI evidence requires PyPiPublicationConfig")
        return frozenset(
            pypi_publish_attestation_asset_name(artifact.logical_name)
            for artifact in state.artifacts
            if is_project_distribution(
                artifact.logical_name,
                project_name=config.project_name,
                version=state.release.version,
            )
        )

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
        """Validate PyPI command manifests and emit provider-neutral references."""

        if not isinstance(config, PyPiPublicationConfig):
            raise TypeError("PyPI evidence requires PyPiPublicationConfig")
        if len(publication_results) != 1 or len(verification_results) != 1:
            raise ValueError(
                "configured PyPI publication requires one publication result and one attestation result"
            )
        publications: list[PublicationReference] = []
        pypi_publications: dict[tuple[str, str], VerifyPyPiPublicationManifest] = {}
        state_digest = hash_file(release_state_path, algorithm="sha256")
        expected_distributions = {
            artifact.logical_name: artifact
            for artifact in state.artifacts
            if is_project_distribution(
                artifact.logical_name,
                project_name=config.project_name,
                version=state.release.version,
            )
        }
        for result_path in publication_results:
            publication_result = read_pydantic_json_file_bounded(
                VerifyPyPiPublicationManifest,
                result_path,
                max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
            )
            if (
                publication_result.component != state.release.component.id
                or publication_result.project_name != config.project_name
                or publication_result.version != state.release.version
                or publication_result.source_commit != state.source.commit_sha
            ):
                raise ValueError(
                    "PyPI publication result does not match final-release state"
                )
            expected_project_url = config.project_url_template.format(
                project=quote(config.project_name, safe=""),
                version=quote(
                    normalized_pypi_version(state.release.version),
                    safe="",
                ),
            )
            configured_urls = (
                publication_result.repository_api_url
                == config.repository_api_url.rstrip("/")
                and publication_result.project_url == expected_project_url
            )
            if test_target_mode and not configured_urls:
                project_host = urlparse(publication_result.project_url).hostname or ""
                repository_scheme = urlparse(
                    publication_result.repository_api_url
                ).scheme
                if not project_host.endswith(".invalid") or repository_scheme not in {
                    "file",
                    "https",
                }:
                    raise ValueError(
                        "harness PyPI publication uses unsafe service URLs"
                    )
            elif not test_target_mode and not configured_urls:
                raise ValueError(
                    "PyPI publication result does not match configured service URLs"
                )
            if publication_result.release_state_sha256 != state_digest:
                raise ValueError(
                    "PyPI publication result is not bound to final-release state"
                )
            if publication_result.publication_state != "complete":
                raise ValueError("PyPI publication result is not complete")
            published_distributions = {
                artifact.logical_name: artifact
                for artifact in publication_result.published_files
            }
            if not expected_distributions or (
                set(published_distributions) != set(expected_distributions)
            ):
                raise ValueError(
                    "PyPI publication files do not match final-release artifacts"
                )
            for filename, expected_artifact in expected_distributions.items():
                published_artifact = published_distributions[filename]
                if (
                    published_artifact.kind != "python-distribution"
                    or published_artifact.size_bytes != expected_artifact.size_bytes
                    or published_artifact.digests.get("sha256")
                    != expected_artifact.digests.get("sha256")
                ):
                    raise ValueError(
                        "PyPI publication file differs from final-release artifact: "
                        f"{filename}"
                    )
            key = (publication_result.project_name, publication_result.version)
            if key in pypi_publications:
                raise ValueError(
                    "duplicate PyPI publication result: "
                    f"{publication_result.project_name}=={publication_result.version}"
                )
            pypi_publications[key] = publication_result
            publications.append(
                PublicationReference(
                    target_kind="pypi",
                    uri=publication_result.project_url,
                    immutable_id=(
                        f"{publication_result.project_name}=="
                        f"{normalized_pypi_version(publication_result.version)}"
                    ),
                )
            )

        verifications: list[VerificationResultReference] = []
        for result_path in verification_results:
            attestation_result = read_pydantic_json_file_bounded(
                VerifyPyPiAttestationsManifest,
                result_path,
                max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
            )
            if (
                attestation_result.component != state.release.component.id
                or attestation_result.version != state.release.version
            ):
                raise ValueError(
                    "PyPI attestation result does not match final-release state"
                )
            publication = pypi_publications.get(
                (attestation_result.project_name, attestation_result.version)
            )
            if publication is None:
                raise ValueError(
                    "PyPI attestation result has no matching PyPI publication"
                )
            published_files = {
                artifact.logical_name: artifact
                for artifact in publication.published_files
            }
            evidence_files = {item.filename: item for item in attestation_result.files}
            if len(evidence_files) != len(attestation_result.files) or set(
                evidence_files
            ) != set(published_files):
                raise ValueError("PyPI attestation files do not match PyPI publication")
            integrity_base_url = attestation_result.integrity_base_url.rstrip("/")
            if not integrity_base_url.startswith("https://"):
                raise ValueError("PyPI Integrity API URL must use HTTPS")
            if (
                test_target_mode
                and integrity_base_url != config.integrity_api_url.rstrip("/")
            ):
                integrity_host = urlparse(integrity_base_url).hostname or ""
                if not integrity_host.endswith(".invalid"):
                    raise ValueError(
                        "harness PyPI Integrity API must use a .invalid host"
                    )
            elif integrity_base_url != config.integrity_api_url.rstrip("/"):
                raise ValueError(
                    "PyPI attestation result uses an unexpected Integrity API"
                )
            if (
                attestation_result.publisher.kind != config.trusted_publisher.kind
                or attestation_result.publisher.repository
                != config.trusted_publisher.repository
                or attestation_result.publisher.workflow
                != config.trusted_publisher.workflow
                or attestation_result.publisher.environment
                != config.trusted_publisher.environment
            ):
                raise ValueError(
                    "PyPI attestation publisher does not match configuration"
                )
            for filename, evidence in sorted(evidence_files.items()):
                published = published_files[filename]
                if evidence.evidence_filename != pypi_publish_attestation_asset_name(
                    filename
                ):
                    raise ValueError(
                        f"PyPI publish-attestation evidence name is not canonical: {filename}"
                    )
                if evidence.distribution_sha256 != published.digests.get("sha256"):
                    raise ValueError(
                        "PyPI attestation distribution differs from PyPI publication: "
                        f"{filename}"
                    )
                expected_url = (
                    f"{integrity_base_url}/{attestation_result.project_name}/"
                    f"{normalized_pypi_version(attestation_result.version)}/"
                    f"{filename}/provenance"
                )
                if evidence.source_provenance_url != expected_url:
                    raise ValueError(
                        f"PyPI attestation provenance URL is unexpected: {filename}"
                    )
                retained = durable_evidence_assets.get(evidence.evidence_filename)
                if (
                    retained is None
                    or retained.sha256 != evidence.evidence_sha256
                    or retained.size_bytes != evidence.evidence_size_bytes
                ):
                    raise ValueError(
                        f"PyPI publish-attestation evidence was not retained exactly: {filename}"
                    )
                verifications.append(
                    VerificationResultReference(
                        kind="pypi-publish-attestation",
                        uri=retained.uri,
                        digest=evidence.evidence_sha256,
                        claims={
                            "distribution_filename": filename,
                            "distribution_sha256": evidence.distribution_sha256,
                            "evidence_asset_name": evidence.evidence_filename,
                            "evidence_size_bytes": str(evidence.evidence_size_bytes),
                            "integrity_base_url": integrity_base_url,
                            "project_name": attestation_result.project_name,
                            "version": attestation_result.version,
                            "publisher_kind": attestation_result.publisher.kind,
                            "publisher_repository": attestation_result.publisher.repository,
                            "publisher_workflow": attestation_result.publisher.workflow,
                            "publisher_environment": attestation_result.publisher.environment,
                        },
                    )
                )
        return AdapterEvidence(tuple(publications), tuple(verifications))

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
        """Revalidate PyPI references independently of the hosting adapter."""

        if not isinstance(config, PyPiPublicationConfig):
            raise TypeError("PyPI evidence requires PyPiPublicationConfig")
        pypi_publications = {publication.immutable_id for publication in publications}
        if not pypi_publications:
            raise ValueError(
                "configured PyPI publication is missing from the release manifest"
            )
        if len(publications) != 1:
            raise ValueError("release manifest requires exactly one PyPI publication")
        expected_immutable_id = (
            f"{config.project_name}=="
            f"{normalized_pypi_version(manifest.release.version)}"
        )
        expected_project_url = config.project_url_template.format(
            project=quote(config.project_name, safe=""),
            version=quote(
                normalized_pypi_version(manifest.release.version),
                safe="",
            ),
        )
        publication = publications[0]
        if publication.immutable_id != expected_immutable_id:
            raise ValueError("PyPI publication identity does not match configuration")
        if test_target_mode and publication.uri != expected_project_url:
            publication_host = urlparse(publication.uri).hostname or ""
            if not publication_host.endswith(".invalid"):
                raise ValueError("harness PyPI publication must use a .invalid host")
        elif publication.uri != expected_project_url:
            raise ValueError("PyPI publication URI does not match configuration")
        expected_distributions = {
            artifact.logical_name: artifact.digests.get("sha256")
            for artifact in manifest.artifacts
            if is_project_distribution(
                artifact.logical_name,
                project_name=config.project_name,
                version=state.release.version,
            )
        }
        verified_distributions: set[str] = set()
        required_claims = {
            "distribution_filename",
            "distribution_sha256",
            "evidence_asset_name",
            "evidence_size_bytes",
            "integrity_base_url",
            "project_name",
            "version",
            "publisher_kind",
            "publisher_repository",
            "publisher_workflow",
            "publisher_environment",
        }
        for result in verification_results:
            if (
                result.digest is None
                or re.fullmatch(r"[0-9a-f]{64}", result.digest) is None
            ):
                raise ValueError("PyPI attestation verification has an invalid digest")
            if not required_claims.issubset(result.claims):
                raise ValueError("PyPI attestation verification has incomplete claims")
            claims = result.claims
            filename = claims["distribution_filename"]
            if filename in verified_distributions:
                raise ValueError("PyPI attestation verification repeats a distribution")
            if expected_distributions.get(filename) != claims["distribution_sha256"]:
                raise ValueError(
                    "PyPI attestation verification does not match a release artifact"
                )
            if claims["evidence_asset_name"] != pypi_publish_attestation_asset_name(
                filename
            ):
                raise ValueError(
                    "PyPI attestation verification evidence name is not canonical"
                )
            if claims["version"] != manifest.release.version:
                raise ValueError(
                    "PyPI attestation verification has an unexpected version"
                )
            if claims["project_name"] != config.project_name:
                raise ValueError(
                    "PyPI attestation verification has an unexpected project"
                )
            if (
                f"{claims['project_name']}=="
                f"{normalized_pypi_version(claims['version'])}" not in pypi_publications
            ):
                raise ValueError(
                    "PyPI attestation verification has no matching publication"
                )
            integrity_base_url = claims["integrity_base_url"].rstrip("/")
            if not integrity_base_url.startswith("https://"):
                raise ValueError("PyPI attestation verification URL must use HTTPS")
            if (
                test_target_mode
                and integrity_base_url != config.integrity_api_url.rstrip("/")
            ):
                integrity_host = urlparse(integrity_base_url).hostname or ""
                if not integrity_host.endswith(".invalid"):
                    raise ValueError(
                        "harness PyPI attestation verification must use a .invalid host"
                    )
            elif integrity_base_url != config.integrity_api_url.rstrip("/"):
                raise ValueError(
                    "PyPI attestation verification uses an unexpected Integrity API"
                )
            expected_uri_suffix = (
                f"/releases/download/{state.final_tag.name}/"
                f"{quote(claims['evidence_asset_name'], safe='')}"
            )
            parsed_result_uri = urlparse(result.uri)
            if (
                parsed_result_uri.scheme != "https"
                or parsed_result_uri.hostname != "github.com"
                or not parsed_result_uri.path.endswith(expected_uri_suffix)
            ):
                raise ValueError(
                    "PyPI attestation verification is not a durable GitHub Release asset"
                )
            try:
                evidence_size = int(claims["evidence_size_bytes"])
            except ValueError as exc:
                raise ValueError(
                    "PyPI attestation verification has an invalid evidence size"
                ) from exc
            if evidence_size < 1:
                raise ValueError(
                    "PyPI attestation verification has an invalid evidence size"
                )
            if (
                claims["publisher_kind"] != config.trusted_publisher.kind
                or claims["publisher_repository"] != config.trusted_publisher.repository
                or claims["publisher_workflow"] != config.trusted_publisher.workflow
                or claims["publisher_environment"]
                != config.trusted_publisher.environment
            ):
                raise ValueError("PyPI attestation verification publisher is invalid")
            verified_distributions.add(filename)
        if verified_distributions != set(expected_distributions):
            raise ValueError(
                "PyPI attestation verifications do not cover all release distributions"
            )


PYPI_EVIDENCE_ADAPTER: PublicationEvidenceAdapter = PyPiEvidenceAdapter()
