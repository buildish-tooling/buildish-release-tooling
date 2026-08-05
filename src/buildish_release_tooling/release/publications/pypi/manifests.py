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

"""PyPI publication and provenance command-manifest contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from buildish_release_tooling.docs.documentation import (
    SchemaExportSpecification,
    ToolingDerivedModel,
)
from buildish_release_tooling.release.command_manifests import (
    CommandActionManifest,
    NonEmptyString,
)
from buildish_release_tooling.release.core.models import ArtifactReference

LowercaseSha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _internal_manifest_export(
    model: type[CommandActionManifest], *, filename: str
) -> SchemaExportSpecification:
    action = model.model_fields["action"].default
    return SchemaExportSpecification(
        filename=filename,
        audience="internal",
        stability="unstable",
        summary=f"Internal unstable JSON action manifest emitted by `{action}`.",
        description=(
            f"{model.__doc__ or ''} This command manifest is internal Buildish "
            "workflow I/O and is not a supported external API."
        ),
        reference_group="internal-unstable-root",
    )


class VerifyPyPiPublicationManifest(CommandActionManifest):
    """Action manifest proving exact distributions published through the PyPI API."""

    action: Literal["verify-pypi-publication"] = Field(
        default="verify-pypi-publication",
        description="Stable command action identifier written by one Buildish command manifest.",
    )
    project_name: NonEmptyString = Field(description="PyPI project name.")
    version: NonEmptyString = Field(description="Published project version.")
    repository_api_url: NonEmptyString = Field(
        description="PyPI JSON API base URL used for verification."
    )
    project_url: NonEmptyString = Field(
        description="Human-facing immutable project-version URL."
    )
    lifecycle: Literal["direct", "candidate-promotion"] = Field(
        description="Buildish lifecycle state kind that authorized the publication."
    )
    source_commit: NonEmptyString = Field(
        description="Exact source commit bound by the authorizing release state."
    )
    release_state_sha256: LowercaseSha256 = Field(
        description="SHA-256 of the exact DirectReleaseState or PromotionState input."
    )
    publication_state: Literal["absent", "partial", "complete"] = Field(
        description="Observed PyPI state relative to the expected distribution set."
    )
    published_files: list[ArtifactReference] = Field(
        description="Exact distribution files and SHA-256 digests verified through PyPI."
    )


VerifyPyPiPublicationManifest.schema_export = _internal_manifest_export(
    VerifyPyPiPublicationManifest,
    filename="verify-pypi-publication-manifest.schema.json",
)


class PyPiAttestationPublisher(ToolingDerivedModel):
    """Expected GitHub Trusted Publisher identity verified for PyPI attestations."""

    kind: Literal["GitHub"] = Field(description="Trusted Publisher kind.")
    repository: NonEmptyString = Field(
        description="GitHub repository owner/name identity."
    )
    workflow: NonEmptyString = Field(
        description="GitHub Actions workflow filename identity."
    )
    environment: NonEmptyString = Field(description="GitHub Environment identity.")


class PyPiAttestationFileEvidence(ToolingDerivedModel):
    """Durable verified PyPI publish-attestation evidence for one distribution."""

    filename: NonEmptyString = Field(description="Exact distribution filename.")
    distribution_sha256: LowercaseSha256 = Field(
        description="SHA-256 of the verified distribution bytes."
    )
    evidence_filename: NonEmptyString = Field(
        description="GitHub Release asset name containing selected publish attestations."
    )
    evidence_sha256: LowercaseSha256 = Field(
        description="SHA-256 of the exact retained publish-attestation document."
    )
    evidence_size_bytes: int = Field(
        ge=1, description="Size of the retained publish-attestation document."
    )
    source_provenance_url: NonEmptyString = Field(
        description="Mutable PyPI Integrity API provenance URL used as the evidence source."
    )
    publish_attestation_count: int = Field(
        ge=1, description="Number of verified PyPI Publish Attestations retained."
    )


class PyPiPublishAttestationEvidence(ToolingDerivedModel):
    """Exact selected PyPI Publish Attestations retained as release evidence."""

    kind: Literal["pypi-publish-attestation-evidence"] = Field(
        default="pypi-publish-attestation-evidence",
        description="Evidence-document discriminator.",
    )
    schema_version: Literal["1"] = Field(
        default="1", description="Evidence schema version."
    )
    publisher: PyPiAttestationPublisher = Field(
        description="Exact verified Trusted Publisher identity."
    )
    distribution_filename: NonEmptyString = Field(
        description="Exact verified distribution filename."
    )
    distribution_sha256: LowercaseSha256 = Field(
        description="SHA-256 of the verified distribution bytes."
    )
    source_provenance_url: NonEmptyString = Field(
        description="Mutable PyPI provenance URL from which attestations were selected."
    )
    attestations: list[dict[str, object]] = Field(
        min_length=1,
        description="Exact cryptographically verified PyPI Publish Attestation objects.",
    )


PyPiPublishAttestationEvidence.schema_export = SchemaExportSpecification(
    filename="pypi-publish-attestation-evidence.schema.json",
    summary="Stable exact PyPI Publish Attestation evidence retained with a release.",
    reference_group="supported-emitted-root",
)


class VerifyPyPiAttestationsManifest(CommandActionManifest):
    """Action manifest binding verified PyPI PEP 740 provenance to distributions."""

    kind: Literal["pypi-attestation-verification"] = Field(
        default="pypi-attestation-verification",
        description="Evidence-document discriminator.",
    )
    action: Literal["verify-pypi-attestations"] = Field(
        default="verify-pypi-attestations",
        description="Stable command action identifier written by one Buildish command manifest.",
    )
    schema_version: Literal["1"] = Field(
        default="1", description="Evidence schema version."
    )
    project_name: NonEmptyString = Field(description="PyPI project name.")
    version: NonEmptyString = Field(description="Published project version.")
    integrity_base_url: NonEmptyString = Field(
        description="PyPI Integrity API base URL."
    )
    publisher: PyPiAttestationPublisher = Field(
        description="Exact verified Trusted Publisher identity."
    )
    files: list[PyPiAttestationFileEvidence] = Field(
        min_length=1,
        description="Exact distributions and retained publish attestations verified successfully.",
    )


VerifyPyPiAttestationsManifest.schema_export = _internal_manifest_export(
    VerifyPyPiAttestationsManifest,
    filename="verify-pypi-attestations-manifest.schema.json",
)
