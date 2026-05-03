---
title: "Release manifests, inventories, and verification report types"
description: "Typed Buildish release manifests, emitted verification reports, inspection-bundle payloads, and related helper contracts."
---

<!--
Copyright 2026 The Apache Software Foundation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

Typed Buildish release manifests, emitted verification reports, inspection-bundle payloads, and related helper contracts.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

- [ArtifactReproducibilityBuildOverrideReport](#artifactreproducibilitybuildoverridereport) — Sparse local override delta applied to one canonical build recipe.
- [ArtifactReproducibilityCanonicalBuildRecipeReport](#artifactreproducibilitycanonicalbuildrecipereport) — Canonical build recipe declared by the verified source tree for one profile.
- [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) — Canonical repo-defined recipe for one reproducibility profile.
- [ArtifactReproducibilityEffectiveBuildExecutionReport](#artifactreproducibilityeffectivebuildexecutionreport) — Observed build invocation details for one executed reproducibility profile.
- [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) — Effective execution details for one reproducibility run.
- [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) — Structured local override metadata for one reproducibility run.
- [ArtifactReproducibilityReport](#artifactreproducibilityreport) — Observed local rebuild comparison results for one artifact.
- [AsfKeysTrustRoot](#asfkeystrustroot) — Pinned ASF KEYS metadata used as a trust root.
- [AsfKeysTrustRootRead](#asfkeystrustrootread) — Tolerant ASF KEYS trust-root subset accepted by verify-rc readers.
- [AuthoritativeManifestReference](#authoritativemanifestreference) — Reference to the authoritative signed manifest file and sidecars.
- [AuthoritativeManifestReferenceRead](#authoritativemanifestreferenceread) — Tolerant authoritative-manifest reference accepted by verify-rc readers.
- [ChecksumVerificationReport](#checksumverificationreport) — Observed checksum verification results for one downloaded artifact.
- [DraftGithubRelease](#draftgithubrelease) — Convenience pointer to the matching draft GitHub Release.
- [DraftGithubReleaseRead](#draftgithubreleaseread) — Tolerant draft-release pointer accepted by verify-rc readers.
- [FileLikeReproducibilityMetadata](#filelikereproducibilitymetadata) — Retained comparison metadata for one file-like reproducibility failure or drift.
- [GenericFileSecondaryArtifact](#genericfilesecondaryartifact) — A standalone file artifact tracked in the signed vote manifest.
- [GenericFileVerificationReport](#genericfileverificationreport) — Verification report for one generic secondary file.
- [GenericFileWithOpenPgpSecondaryArtifact](#genericfilewithopenpgpsecondaryartifact) — A standalone file artifact that requires at least one detached signature.
- [GithubWorkflowProvenance](#githubworkflowprovenance) — GitHub Actions provenance embedded in emitted manifests.
- [InspectReproCountSummary](#inspectreprocountsummary) — One count bucket emitted by inspect-repro machine-readable summaries.
- [InspectReproReportV1](#inspectreproreportv1) — Machine-readable inspect-repro output for automation and post-processing.
- [InspectReproSummaryV1](#inspectreprosummaryv1) — Top-level summary block for machine-readable inspect-repro output.
- [InspectReproTargetV1](#inspectreprotargetv1) — One selected reproducibility failure reported by inspect-repro JSON mode.
- [InspectionBundleArtifactEntry](#inspectionbundleartifactentry) — One artifact-specific metadata document retained inside an inspection bundle.
- [InspectionBundleManifestV1](#inspectionbundlemanifestv1) — Top-level contract manifest for one curated verify-rc inspection bundle.
- [InspectionBundleSection](#inspectionbundlesection) — Location of the curated reproducibility-inspection bundle for one verify-rc run.
- [InspectionEvidenceReference](#inspectionevidencereference) — One retained evidence file inside the verify-rc inspection bundle.
- [IntegrityVerificationReport](#integrityverificationreport) — Observed integrity verification results for one npm package.
- [InvalidSecondaryArtifactVerificationReport](#invalidsecondaryartifactverificationreport) — Failure record used when one secondary artifact entry is malformed.
- [InventoryVerificationReport](#inventoryverificationreport) — Verification results for one downloaded inventory attachment.
- [LiveMavenRepositoryReport](#livemavenrepositoryreport) — Observed live-repository comparison results for a Maven staging repository.
- [LiveRepositorySignatureVerification](#liverepositorysignatureverification) — One detached signature verified in the live Maven repository.
- [ManifestProvenance](#manifestprovenance) — Top-level provenance block for the RC vote manifest.
- [ManifestTrustRoots](#manifesttrustroots) — Trust roots referenced by the signed manifest.
- [ManifestVerificationMetadataStrict](#manifestverificationmetadatastrict) — Strict verification metadata emitted by finalize-rc-vote-materials.
- [ManifestVerificationSection](#manifestverificationsection) — Manifest-authenticity and tag-binding section of the verify-rc report.
- [MavenRepositoryInventoryEntry](#mavenrepositoryinventoryentry) — One file entry in a signed Maven repository inventory.
- [MavenRepositoryInventoryV1](#mavenrepositoryinventoryv1) — A signed Maven repository inventory attachment.
- [MavenRepositoryPathResultReport](#mavenrepositorypathresultreport) — One comparable staged Maven repository path result retained for inspection.
- [MavenRepositoryPathRuleReport](#mavenrepositorypathrulereport) — One regex-based Maven repository path rule retained for inspection.
- [MavenRepositoryReproducibilityMetadata](#mavenrepositoryreproducibilitymetadata) — Retained comparison metadata for one Maven repository reproducibility run.
- [MavenRepositorySecondaryArtifact](#mavenrepositorysecondaryartifact) — A staged Maven repository validated through a signed inventory.
- [MavenRepositoryVerificationReport](#mavenrepositoryverificationreport) — Verification report for one staged Maven repository.
- [NpmChecksums](#npmchecksums) — A checksum block for npm artifacts, which may use sha256 or sha512.
- [NpmPackageSecondaryArtifact](#npmpackagesecondaryartifact) — A published npm package tarball.
- [NpmPackageVerificationReport](#npmpackageverificationreport) — Verification report for one npm package.
- [NpmProvenanceAuth](#npmprovenanceauth) — Explicit npm provenance metadata.
- [NpmRegistryResolutionReport](#npmregistryresolutionreport) — Resolution details for one npm registry lookup.
- [OciImageReproducibilityMetadata](#ociimagereproducibilitymetadata) — Retained comparison metadata for one OCI image reproducibility run.
- [OciImageSecondaryArtifact](#ociimagesecondaryartifact) — An immutable OCI image reference.
- [OciImageVerificationReport](#ociimageverificationreport) — Verification report for one OCI image.
- [OciInspectionReport](#ociinspectionreport) — Observed registry inspection results for one OCI image.
- [OciPlatformDigest](#ociplatformdigest) — One platform-specific digest declared for an OCI image.
- [PyPiAttestationAuth](#pypiattestationauth) — Explicit PyPI attestation metadata.
- [PythonDistributionSecondaryArtifact](#pythondistributionsecondaryartifact) — A published Python distribution file.
- [PythonDistributionVerificationReport](#pythondistributionverificationreport) — Verification report for one Python distribution.
- [PythonIndexResolutionReport](#pythonindexresolutionreport) — Resolution details for one Python simple-index lookup.
- [RcVoteManifestV1](#rcvotemanifestv1) — Strict authoritative RC vote manifest emitted by buildish-release-tooling.
- [RebuiltOutputSnapshot](#rebuiltoutputsnapshot) — One rebuilt output file described inside an inspection-bundle metadata document.
- [ReproducibilityExecutionSection](#reproducibilityexecutionsection) — Run-level policy and execution summary for build-based reproducibility checks.
- [ReproducibilitySelector](#reproducibilityselector) — Signed manifest selector for one canonical local reproducibility profile.
- [RetainedArtifactSnapshot](#retainedartifactsnapshot) — One retained file snapshot described inside an inspection-bundle metadata document.
- [SecondaryArtifactBase](#secondaryartifactbase) — Common fields shared across supported secondary artifact kinds.
- [SecondaryArtifactManifestV1](#secondaryartifactmanifestv1) — A reusable secondary-artifact manifest fragment.
- [Sha256ChecksumPayload](#sha256checksumpayload) — One sha256 checksum value and optional detached sidecar URI.
- [Sha256Checksums](#sha256checksums) — A checksum block containing one sha256 entry.
- [Sha512ChecksumPayload](#sha512checksumpayload) — One sha512 checksum value and optional detached sidecar URI.
- [Sha512Checksums](#sha512checksums) — A checksum block containing one sha512 entry.
- [ShallowArchiveAnalysisReport](#shallowarchiveanalysisreport) — Durable shallow archive-comparison findings for one retained artifact pair.
- [SignatureReference](#signaturereference) — One detached OpenPGP signature reference.
- [SignatureVerificationPayload](#signatureverificationpayload) — Serialized detached-signature verification details.
- [SourceArtifactContract](#sourceartifactcontract) — The single source artifact under vote.
- [SourceArtifactContractRead](#sourceartifactcontractread) — Tolerant source-artifact contract accepted by verify-rc readers.
- [SourceArtifactReproducibilityMetadata](#sourceartifactreproducibilitymetadata) — Retained comparison metadata for source-artifact reproducibility inspection.
- [SourceArtifactVerificationSection](#sourceartifactverificationsection) — Source-artifact verification section of the verify-rc report.
- [SupplementalInventoryReference](#supplementalinventoryreference) — One staged supplemental inventory attachment.
- [ToolingProvenance](#toolingprovenance) — Tooling repository provenance embedded in emitted manifests.
- [VerificationFailurePayload](#verificationfailurepayload) — One collected verification failure.
- [VerifyRcReportV1](#verifyrcreportv1) — Machine-readable Phase 1a RC verification report.
- [VoteMaterialsRead](#votematerialsread) — Tolerant vote-materials block used by verify-rc readers.
- [VoteMaterialsStrict](#votematerialsstrict) — Strict vote-materials block for authored and emitted manifests.

<a id="artifactreproducibilitybuildoverridereport"></a>
### ArtifactReproducibilityBuildOverrideReport

Sparse local override delta applied to one canonical build recipe.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilitybuildoverridereport-command"></a>`command` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilitybuildoverridereport-working-directory"></a>`working_directory` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilitybuildoverridereport-output-globs"></a>`output_globs` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |
| <a id="artifactreproducibilitybuildoverridereport-env-keys"></a>`env_keys` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Environment variable names referenced by the related recipe or override without exposing their values. |

<a id="artifactreproducibilitycanonicalbuildrecipereport"></a>
### ArtifactReproducibilityCanonicalBuildRecipeReport

Canonical build recipe declared by the verified source tree for one profile.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-command"></a>`command` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-working-directory"></a>`working_directory` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-output-globs"></a>`output_globs` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-env-keys"></a>`env_keys` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Environment variable names referenced by the related recipe or override without exposing their values. |

<a id="artifactreproducibilitycanonicalrecipereport"></a>
### ArtifactReproducibilityCanonicalRecipeReport

Canonical repo-defined recipe for one reproducibility profile.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilitycanonicalrecipereport-build"></a>`build` | [ArtifactReproducibilityCanonicalBuildRecipeReport](#artifactreproducibilitycanonicalbuildrecipereport) | yes | Nested build recipe or effective build execution block for one reproducibility contract. |

<a id="artifactreproducibilityeffectivebuildexecutionreport"></a>
### ArtifactReproducibilityEffectiveBuildExecutionReport

Observed build invocation details for one executed reproducibility profile.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-command"></a>`command` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-working-directory"></a>`working_directory` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-output-paths"></a>`output_paths` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Concrete output paths that Buildish observed from the effective rebuild execution. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-injected-environment-keys"></a>`injected_environment_keys` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Environment variable names that Buildish injected into the effective rebuild subprocess. |

<a id="artifactreproducibilityeffectiveexecutionreport"></a>
### ArtifactReproducibilityEffectiveExecutionReport

Effective execution details for one reproducibility run.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilityeffectiveexecutionreport-backend"></a>`backend` | Literal['host-direct'] | no | Execution backend name that performed the related Buildish action or reproducibility run. |
| <a id="artifactreproducibilityeffectiveexecutionreport-build"></a>`build` | [ArtifactReproducibilityEffectiveBuildExecutionReport](#artifactreproducibilityeffectivebuildexecutionreport) | yes | Nested build recipe or effective build execution block for one reproducibility contract. |

<a id="artifactreproducibilityoverridereport"></a>
### ArtifactReproducibilityOverrideReport

Structured local override metadata for one reproducibility run.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilityoverridereport-applied"></a>`applied` | bool | no | Whether the related local override block was applied to the effective rebuild execution. |
| <a id="artifactreproducibilityoverridereport-build"></a>`build` | [ArtifactReproducibilityBuildOverrideReport](#artifactreproducibilitybuildoverridereport) | no | Nested build recipe or effective build execution block for one reproducibility contract. |

<a id="artifactreproducibilityreport"></a>
### ArtifactReproducibilityReport

Observed local rebuild comparison results for one artifact.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilityreport-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="artifactreproducibilityreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="artifactreproducibilityreport-comparison-mode"></a>`comparison_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="artifactreproducibilityreport-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="artifactreproducibilityreport-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="artifactreproducibilityreport-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="artifactreproducibilityreport-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="artifactreproducibilityreport-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="artifactreproducibilityreport-archive-analysis"></a>`archive_analysis` | [ShallowArchiveAnalysisReport](#shallowarchiveanalysisreport) | no | Shallow top-level archive comparison details retained for reproducibility inspection. |
| <a id="artifactreproducibilityreport-evidence"></a>`evidence` | list[[InspectionEvidenceReference](#inspectionevidencereference)] | no | Inspection-bundle evidence references retained for one reproducibility result. |
| <a id="artifactreproducibilityreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="asfkeystrustroot"></a>
### AsfKeysTrustRoot

Pinned ASF KEYS metadata used as a trust root.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="asfkeystrustroot-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="asfkeystrustroot-known-length-bytes"></a>`known_length_bytes` | int | yes | Expected byte length of the pinned ASF KEYS file when Buildish establishes the trust root. |
| <a id="asfkeystrustroot-known-prefix-sha512"></a>`known_prefix_sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | Pinned SHA-512 digest prefix that Buildish expects the ASF KEYS file to start with. |

<a id="asfkeystrustrootread"></a>
### AsfKeysTrustRootRead

Tolerant ASF KEYS trust-root subset accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`asf-keys-trust-root-read.schema.json`](/components/buildish-release-tooling/schemas/asf-keys-trust-root-read.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="asfkeystrustrootread-uri"></a>`uri` | object | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="asfkeystrustrootread-known-length-bytes"></a>`known_length_bytes` | object | yes | Expected byte length of the pinned ASF KEYS file when Buildish establishes the trust root. |
| <a id="asfkeystrustrootread-known-prefix-sha512"></a>`known_prefix_sha512` | object | yes | Pinned SHA-512 digest prefix that Buildish expects the ASF KEYS file to start with. |

<a id="authoritativemanifestreference"></a>
### AuthoritativeManifestReference

Reference to the authoritative signed manifest file and sidecars.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="authoritativemanifestreference-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="authoritativemanifestreference-checksum-uris"></a>`checksum_uris` | dict[Literal['sha512'], [NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Manifest-relative or absolute URIs of checksum sidecars associated with the authoritative staged manifest. |
| <a id="authoritativemanifestreference-signatures"></a>`signatures` | list[[SignatureReference](#signaturereference)] | yes | Declared detached signature references associated with the related artifact or manifest. |

<a id="authoritativemanifestreferenceread"></a>
### AuthoritativeManifestReferenceRead

Tolerant authoritative-manifest reference accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`authoritative-manifest-reference-read.schema.json`](/components/buildish-release-tooling/schemas/authoritative-manifest-reference-read.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="authoritativemanifestreferenceread-uri"></a>`uri` | object | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="authoritativemanifestreferenceread-checksum-uris"></a>`checksum_uris` | object | yes | Manifest-relative or absolute URIs of checksum sidecars associated with the authoritative staged manifest. |
| <a id="authoritativemanifestreferenceread-signatures"></a>`signatures` | object | yes | Declared detached signature references associated with the related artifact or manifest. |

<a id="checksumverificationreport"></a>
### ChecksumVerificationReport

Observed checksum verification results for one downloaded artifact.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="checksumverificationreport-algorithm"></a>`algorithm` | Literal['sha256', 'sha512'] | no | Checksum or digest algorithm name that Buildish used for the related verification or report entry. |
| <a id="checksumverificationreport-value"></a>`value` | str | no | Declared checksum or digest value recorded in the related payload. |
| <a id="checksumverificationreport-matches-manifest"></a>`matches_manifest` | bool | no | Whether the observed checksum or digest matched the value declared in the authoritative manifest or inventory. |
| <a id="checksumverificationreport-sidecar-verified"></a>`sidecar_verified` | bool | no | Whether the detached checksum sidecar associated with this report entry was fetched and verified successfully. |

<a id="draftgithubrelease"></a>
### DraftGithubRelease

Convenience pointer to the matching draft GitHub Release.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="draftgithubrelease-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="draftgithubrelease-tag"></a>`tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload. |
| <a id="draftgithubrelease-url"></a>`url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical browser or download URL associated with the related record. |

<a id="draftgithubreleaseread"></a>
### DraftGithubReleaseRead

Tolerant draft-release pointer accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`draft-github-release-read.schema.json`](/components/buildish-release-tooling/schemas/draft-github-release-read.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="draftgithubreleaseread-repository"></a>`repository` | object | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="draftgithubreleaseread-tag"></a>`tag` | object | yes | Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload. |
| <a id="draftgithubreleaseread-url"></a>`url` | object | yes | Canonical browser or download URL associated with the related record. |

<a id="filelikereproducibilitymetadata"></a>
### FileLikeReproducibilityMetadata

Retained comparison metadata for one file-like reproducibility failure or drift.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`file-like-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/file-like-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="filelikereproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="filelikereproducibilitymetadata-kind"></a>`kind` | Literal['generic-file', 'generic-file-with-openpgp', 'python-distribution', 'npm-package'] | yes | Declared artifact or report kind discriminator. |
| <a id="filelikereproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="filelikereproducibilitymetadata-comparison-mode"></a>`comparison_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="filelikereproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="filelikereproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="filelikereproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="filelikereproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="filelikereproducibilitymetadata-archive-analysis"></a>`archive_analysis` | [ShallowArchiveAnalysisReport](#shallowarchiveanalysisreport) | no | Shallow top-level archive comparison details retained for reproducibility inspection. |
| <a id="filelikereproducibilitymetadata-staged-artifact"></a>`staged_artifact` | [RetainedArtifactSnapshot](#retainedartifactsnapshot) | yes | Retained snapshot metadata for the staged artifact bytes used as the comparison target. |
| <a id="filelikereproducibilitymetadata-rebuilt-outputs"></a>`rebuilt_outputs` | list[[RebuiltOutputSnapshot](#rebuiltoutputsnapshot)] | no | Snapshot metadata for files or trees produced by a local rebuild step. |
| <a id="filelikereproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="filelikereproducibilitymetadata-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="genericfilesecondaryartifact"></a>
### GenericFileSecondaryArtifact

A standalone file artifact tracked in the signed vote manifest.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="genericfilesecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="genericfilesecondaryartifact-kind"></a>`kind` | Literal['generic-file'] | no | Declared artifact or report kind discriminator. |
| <a id="genericfilesecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="genericfilesecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="genericfilesecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="genericfilesecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="genericfilesecondaryartifact-inventory"></a>`inventory` | object | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="genericfilesecondaryartifact-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfilesecondaryartifact-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="genericfilesecondaryartifact-checksums"></a>`checksums` | [Sha512Checksums](#sha512checksums) | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="genericfilesecondaryartifact-signatures"></a>`signatures` | list[[SignatureReference](#signaturereference)] | no | Declared detached signature references associated with the related artifact or manifest. |

<a id="genericfileverificationreport"></a>
### GenericFileVerificationReport

Verification report for one generic secondary file.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="genericfileverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="genericfileverificationreport-kind"></a>`kind` | Literal['generic-file', 'generic-file-with-openpgp'] | yes | Declared artifact or report kind discriminator. |
| <a id="genericfileverificationreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="genericfileverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="genericfileverificationreport-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfileverificationreport-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="genericfileverificationreport-checksum"></a>`checksum` | [ChecksumVerificationReport](#checksumverificationreport) | yes | Checksum verification details for one downloaded or rebuilt artifact. |
| <a id="genericfileverificationreport-signatures"></a>`signatures` | list[[SignatureVerificationPayload](#signatureverificationpayload)] | no | Declared detached signature references associated with the related artifact or manifest. |
| <a id="genericfileverificationreport-inventory"></a>`inventory` | [InventoryVerificationReport](#inventoryverificationreport) | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="genericfileverificationreport-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

<a id="genericfilewithopenpgpsecondaryartifact"></a>
### GenericFileWithOpenPgpSecondaryArtifact

A standalone file artifact that requires at least one detached signature.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="genericfilewithopenpgpsecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="genericfilewithopenpgpsecondaryartifact-kind"></a>`kind` | Literal['generic-file-with-openpgp'] | no | Declared artifact or report kind discriminator. |
| <a id="genericfilewithopenpgpsecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="genericfilewithopenpgpsecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="genericfilewithopenpgpsecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="genericfilewithopenpgpsecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="genericfilewithopenpgpsecondaryartifact-inventory"></a>`inventory` | object | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="genericfilewithopenpgpsecondaryartifact-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfilewithopenpgpsecondaryartifact-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="genericfilewithopenpgpsecondaryartifact-checksums"></a>`checksums` | [Sha512Checksums](#sha512checksums) | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="genericfilewithopenpgpsecondaryartifact-signatures"></a>`signatures` | list[[SignatureReference](#signaturereference)] | no | Declared detached signature references associated with the related artifact or manifest. |

<a id="githubworkflowprovenance"></a>
### GithubWorkflowProvenance

GitHub Actions provenance embedded in emitted manifests.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="githubworkflowprovenance-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="githubworkflowprovenance-workflow"></a>`workflow` | str | yes | Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance. |
| <a id="githubworkflowprovenance-workflow-ref"></a>`workflow_ref` | str | yes | GitHub Actions workflow ref associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-id"></a>`run_id` | int | yes | GitHub Actions run id associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-attempt"></a>`run_attempt` | int | no | GitHub Actions run attempt number associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-url"></a>`run_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Browser URL of the related GitHub Actions workflow run. |

<a id="inspectreprocountsummary"></a>
### InspectReproCountSummary

One count bucket emitted by inspect-repro machine-readable summaries.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreprocountsummary-key"></a>`key` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable grouping or category key used in one Buildish summary object. |
| <a id="inspectreprocountsummary-count"></a>`count` | int | yes | Count value reported for one grouped summary bucket. |

<a id="inspectreproreportv1"></a>
### InspectReproReportV1

Machine-readable inspect-repro output for automation and post-processing.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`inspect-repro-report-v1.schema.json`](/components/buildish-release-tooling/schemas/inspect-repro-report-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreproreportv1-schema-version"></a>`schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="inspectreproreportv1-report-type"></a>`report_type` | Literal['inspect-repro'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="inspectreproreportv1-verify-rc-report-schema-version"></a>`verify_rc_report_schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | yes | Schema version of the verify-rc JSON report that inspect-repro read before generating its own output. |
| <a id="inspectreproreportv1-bundle-schema-version"></a>`bundle_schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed. |
| <a id="inspectreproreportv1-component-id"></a>`component_id` | str | no | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="inspectreproreportv1-rc-tag"></a>`rc_tag` | str | no | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="inspectreproreportv1-verify-rc-verdict"></a>`verify_rc_verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Final verify-rc verdict that inspect-repro observed in the input verification report. |
| <a id="inspectreproreportv1-build-checks-attempted"></a>`build_checks_attempted` | bool | yes | Whether the command attempted local reproducibility or rebuild checks during this run. |
| <a id="inspectreproreportv1-report-json-path"></a>`report_json_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the verify-rc JSON report consumed by inspect-repro. |
| <a id="inspectreproreportv1-inspection-bundle-path"></a>`inspection_bundle_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the retained inspection bundle directory. |
| <a id="inspectreproreportv1-selected-artifact-ids"></a>`selected_artifact_ids` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Artifact ids that inspect-repro selected for detailed output. |
| <a id="inspectreproreportv1-selected-failure-classes"></a>`selected_failure_classes` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Failure-class filters that inspect-repro applied when selecting targets. |
| <a id="inspectreproreportv1-summary-only"></a>`summary_only` | bool | no | Whether inspect-repro emitted only grouped summaries rather than full per-target detail sections. |
| <a id="inspectreproreportv1-summary"></a>`summary` | [InspectReproSummaryV1](#inspectreprosummaryv1) | yes | Human-readable short summary for the related result or mocked tool behavior. |
| <a id="inspectreproreportv1-targets"></a>`targets` | list[[InspectReproTargetV1](#inspectreprotargetv1)] | no | Selected inspect-repro target entries that Buildish included in the machine-readable report. |

<a id="inspectreprosummaryv1"></a>
### InspectReproSummaryV1

Top-level summary block for machine-readable inspect-repro output.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreprosummaryv1-failure-count"></a>`failure_count` | int | yes | Total number of failing source or secondary reproducibility targets selected for inspect-repro output. |
| <a id="inspectreprosummaryv1-source-failure-count"></a>`source_failure_count` | int | yes | Number of failing source-artifact reproducibility targets selected for inspect-repro output. |
| <a id="inspectreprosummaryv1-secondary-failure-count"></a>`secondary_failure_count` | int | yes | Number of failing secondary-artifact reproducibility targets selected for inspect-repro output. |
| <a id="inspectreprosummaryv1-failure-kinds"></a>`failure_kinds` | list[[InspectReproCountSummary](#inspectreprocountsummary)] | no | Count summary grouped by artifact kind across all selected inspect-repro targets. |
| <a id="inspectreprosummaryv1-failure-classes"></a>`failure_classes` | list[[InspectReproCountSummary](#inspectreprocountsummary)] | no | Count summary grouped by failure-class identifier across all selected inspect-repro targets. |
| <a id="inspectreprosummaryv1-failure-groups"></a>`failure_groups` | list[[InspectReproCountSummary](#inspectreprocountsummary)] | no | Count summary grouped by high-level inspect-repro failure group. |

<a id="inspectreprotargetv1"></a>
### InspectReproTargetV1

One selected reproducibility failure reported by inspect-repro JSON mode.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreprotargetv1-section-label"></a>`section_label` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Human-facing section label that groups related inspect-repro targets. |
| <a id="inspectreprotargetv1-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="inspectreprotargetv1-kind"></a>`kind` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="inspectreprotargetv1-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="inspectreprotargetv1-failure-group"></a>`failure_group` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Higher-level grouping bucket that inspect-repro assigned to the target, such as source-artifact or secondary artifact family. |
| <a id="inspectreprotargetv1-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="inspectreprotargetv1-comparison-mode"></a>`comparison_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="inspectreprotargetv1-recipe-source"></a>`recipe_source` | Literal['verifier-internal', 'canonical-profile', 'local-override'] | yes | Origin of the reproducibility recipe used for this target, such as verifier-internal logic, the canonical profile, or a local override. |
| <a id="inspectreprotargetv1-execution-backend"></a>`execution_backend` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Execution backend that verify-rc used for the recorded reproducibility run. |
| <a id="inspectreprotargetv1-build-command"></a>`build_command` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Literal argv list that inspect-repro or verify-rc recorded as the effective build command for this target. |
| <a id="inspectreprotargetv1-build-working-directory"></a>`build_working_directory` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Repository-root-relative working directory that inspect-repro or verify-rc recorded for the effective build command. |
| <a id="inspectreprotargetv1-injected-environment-keys"></a>`injected_environment_keys` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Environment variable names that Buildish injected into the effective rebuild subprocess. |
| <a id="inspectreprotargetv1-evidence-labels"></a>`evidence_labels` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Short labels naming the retained evidence files that inspect-repro associated with this target. |
| <a id="inspectreprotargetv1-evidence"></a>`evidence` | list[[InspectionEvidenceReference](#inspectionevidencereference)] | no | Inspection-bundle evidence references retained for one reproducibility result. |
| <a id="inspectreprotargetv1-override-fields"></a>`override_fields` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Sparse list of build-recipe fields that a local reproducibility override changed for this target. |

<a id="inspectionbundleartifactentry"></a>
### InspectionBundleArtifactEntry

One artifact-specific metadata document retained inside an inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionbundleartifactentry-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="inspectionbundleartifactentry-kind"></a>`kind` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="inspectionbundleartifactentry-metadata-path"></a>`metadata_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Bundle-relative path to the metadata file for one retained inspection target. |

<a id="inspectionbundlemanifestv1"></a>
### InspectionBundleManifestV1

Top-level contract manifest for one curated verify-rc inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`inspection-bundle-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/inspection-bundle-manifest-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: `inspection-bundle.json`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionbundlemanifestv1-schema-version"></a>`schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="inspectionbundlemanifestv1-bundle-type"></a>`bundle_type` | Literal['verify-rc-inspection'] | no | Stable inspection-bundle manifest discriminator. |
| <a id="inspectionbundlemanifestv1-report-type"></a>`report_type` | Literal['verify-rc'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="inspectionbundlemanifestv1-report-schema-version"></a>`report_schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Supported schema version of the related Buildish report payload. |
| <a id="inspectionbundlemanifestv1-component-id"></a>`component_id` | str | no | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="inspectionbundlemanifestv1-version"></a>`version` | str | no | Release version string without a leading `v` prefix. |
| <a id="inspectionbundlemanifestv1-rc-tag"></a>`rc_tag` | str | no | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="inspectionbundlemanifestv1-artifacts"></a>`artifacts` | list[[InspectionBundleArtifactEntry](#inspectionbundleartifactentry)] | no | Artifact entries retained in the related inspection bundle manifest. |

<a id="inspectionbundlesection"></a>
### InspectionBundleSection

Location of the curated reproducibility-inspection bundle for one verify-rc run.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionbundlesection-relative-path-from-report"></a>`relative_path_from_report` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Path from the verify-rc report directory to the retained inspection bundle directory. |
| <a id="inspectionbundlesection-bundle-schema-version"></a>`bundle_schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed. |
| <a id="inspectionbundlesection-manifest-relative-path"></a>`manifest_relative_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Bundle-relative path to the top-level inspection bundle manifest file. |

<a id="inspectionevidencereference"></a>
### InspectionEvidenceReference

One retained evidence file inside the verify-rc inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionevidencereference-label"></a>`label` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Human-readable label used to name one evidence file or report section. |
| <a id="inspectionevidencereference-path"></a>`path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |

<a id="integrityverificationreport"></a>
### IntegrityVerificationReport

Observed integrity verification results for one npm package.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="integrityverificationreport-algorithm"></a>`algorithm` | Literal['sha256', 'sha512'] | no | Checksum or digest algorithm name that Buildish used for the related verification or report entry. |
| <a id="integrityverificationreport-value"></a>`value` | str | no | Declared checksum or digest value recorded in the related payload. |
| <a id="integrityverificationreport-matches-manifest-checksum"></a>`matches_manifest_checksum` | bool | no | Whether the resolved checksum value matched the checksum declared in the signed manifest. |
| <a id="integrityverificationreport-matches-downloaded-bytes"></a>`matches_downloaded_bytes` | bool | no | Whether the checksum or integrity value matched the bytes that Buildish actually downloaded. |

<a id="invalidsecondaryartifactverificationreport"></a>
### InvalidSecondaryArtifactVerificationReport

Failure record used when one secondary artifact entry is malformed.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="invalidsecondaryartifactverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="invalidsecondaryartifactverificationreport-kind"></a>`kind` | Literal['_invalid-secondary-artifact-entry'] | no | Declared artifact or report kind discriminator. |
| <a id="invalidsecondaryartifactverificationreport-declared-kind"></a>`declared_kind` | str | no | Artifact kind string declared by the malformed secondary-artifact entry that verify-rc could not process normally. |
| <a id="invalidsecondaryartifactverificationreport-verdict"></a>`verdict` | Literal['failed'] | no | Structured verification or reproducibility verdict for the related subject. |
| <a id="invalidsecondaryartifactverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="inventoryverificationreport"></a>
### InventoryVerificationReport

Verification results for one downloaded inventory attachment.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inventoryverificationreport-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="inventoryverificationreport-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="inventoryverificationreport-sha512"></a>`sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="inventoryverificationreport-entry-count"></a>`entry_count` | int | no | Number of entries recorded in the related inventory, repository snapshot, or artifact collection. |
| <a id="inventoryverificationreport-total-size-bytes"></a>`total_size_bytes` | int | no | Total size, in bytes, recorded for the related artifact collection or inventory. |

<a id="livemavenrepositoryreport"></a>
### LiveMavenRepositoryReport

Observed live-repository comparison results for a Maven staging repository.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="livemavenrepositoryreport-entry-count"></a>`entry_count` | int | no | Number of entries recorded in the related inventory, repository snapshot, or artifact collection. |
| <a id="livemavenrepositoryreport-total-size-bytes"></a>`total_size_bytes` | int | yes | Total size, in bytes, recorded for the related artifact collection or inventory. |
| <a id="livemavenrepositoryreport-matches-signed-inventory"></a>`matches_signed_inventory` | bool | yes | Whether the live staged Maven repository contents matched the signed inventory metadata. |
| <a id="livemavenrepositoryreport-signature-verifications"></a>`signature_verifications` | list[[LiveRepositorySignatureVerification](#liverepositorysignatureverification)] | no | Detached-signature verification results collected for live Maven repository sidecars. |

<a id="liverepositorysignatureverification"></a>
### LiveRepositorySignatureVerification

One detached signature verified in the live Maven repository.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="liverepositorysignatureverification-path"></a>`path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="liverepositorysignatureverification-target-path"></a>`target_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Target path that the related detached signature or copy operation refers to. |
| <a id="liverepositorysignatureverification-signature"></a>`signature` | [SignatureVerificationPayload](#signatureverificationpayload) | yes | Signature verification details for the related artifact or manifest. |

<a id="manifestprovenance"></a>
### ManifestProvenance

Top-level provenance block for the RC vote manifest.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifestprovenance-created-at"></a>`created_at` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Timestamp when Buildish created the enclosing manifest or provenance record. |
| <a id="manifestprovenance-tooling"></a>`tooling` | [ToolingProvenance](#toolingprovenance) | yes | Buildish tooling provenance details embedded in the authoritative manifest. |
| <a id="manifestprovenance-github"></a>`github` | [GithubWorkflowProvenance](#githubworkflowprovenance) | no | GitHub workflow provenance metadata embedded in or read from the RC vote manifest. |

<a id="manifesttrustroots"></a>
### ManifestTrustRoots

Trust roots referenced by the signed manifest.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifesttrustroots-asf-keys"></a>`asf_keys` | [AsfKeysTrustRoot](#asfkeystrustroot) | yes | Pinned ASF KEYS trust-root details that Buildish should use when verifying the RC manifest signature chain. |

<a id="manifestverificationmetadatastrict"></a>
### ManifestVerificationMetadataStrict

Strict verification metadata emitted by finalize-rc-vote-materials.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifestverificationmetadatastrict-staging-svn-url"></a>`staging_svn_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF SVN staging directory URL associated with the authoritative RC materials. |
| <a id="manifestverificationmetadatastrict-authoritative-manifest"></a>`authoritative_manifest` | [AuthoritativeManifestReference](#authoritativemanifestreference) | yes | Canonical authoritative RC vote-manifest reference or verification block associated with the enclosing payload. |

<a id="manifestverificationsection"></a>
### ManifestVerificationSection

Manifest-authenticity and tag-binding section of the verify-rc report.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifestverificationsection-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="manifestverificationsection-sha512"></a>`sha512` | str | no | SHA-512 checksum payload associated with the related artifact. |
| <a id="manifestverificationsection-keys-url-matches-manifest"></a>`keys_url_matches_manifest` | bool | yes | Whether the verified KEYS URL matched the authoritative manifest's own recorded KEYS URL. |
| <a id="manifestverificationsection-keys-url-matches-component-config"></a>`keys_url_matches_component_config` | bool | no | Whether the manifest's KEYS URL matched the current component configuration. |
| <a id="manifestverificationsection-signature"></a>`signature` | [SignatureVerificationPayload](#signatureverificationpayload) | no | Signature verification details for the related artifact or manifest. |
| <a id="manifestverificationsection-rc-tag-target-commit"></a>`rc_tag_target_commit` | str | no | Git commit SHA that the RC tag resolved to during verification or publication. |
| <a id="manifestverificationsection-rc-tag-matches-source-commit-sha"></a>`rc_tag_matches_source_commit_sha` | bool | yes | Whether the RC tag resolved to the same commit SHA that the manifest recorded as the authoritative source commit. |
| <a id="manifestverificationsection-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="mavenrepositoryinventoryentry"></a>
### MavenRepositoryInventoryEntry

One file entry in a signed Maven repository inventory.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryinventoryentry-path"></a>`path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="mavenrepositoryinventoryentry-size-bytes"></a>`size_bytes` | int | yes | Byte size recorded for the related artifact, retained snapshot, or inventory entry. |
| <a id="mavenrepositoryinventoryentry-sha512"></a>`sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |

<a id="mavenrepositoryinventoryv1"></a>
### MavenRepositoryInventoryV1

A signed Maven repository inventory attachment.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`maven-repository-inventory-v1.schema.json`](/components/buildish-release-tooling/schemas/maven-repository-inventory-v1.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryinventoryv1-schema-version"></a>`schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="mavenrepositoryinventoryv1-inventory-type"></a>`inventory_type` | Literal['maven-repository'] | no | Stable manifest discriminator for the signed Maven repository inventory file. |
| <a id="mavenrepositoryinventoryv1-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryinventoryv1-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositoryinventoryv1-base-url"></a>`base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |
| <a id="mavenrepositoryinventoryv1-entries"></a>`entries` | list[[MavenRepositoryInventoryEntry](#mavenrepositoryinventoryentry)] | yes | Typed entries recorded in the related manifest, inventory, or report payload. |

<a id="mavenrepositorypathresultreport"></a>
### MavenRepositoryPathResultReport

One comparable staged Maven repository path result retained for inspection.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`maven-repository-path-result-report.schema.json`](/components/buildish-release-tooling/schemas/maven-repository-path-result-report.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositorypathresultreport-path"></a>`path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="mavenrepositorypathresultreport-mode"></a>`mode` | MavenRepositoryPathMode | yes | Comparison mode that Buildish applied when comparing this staged Maven repository path to the rebuilt local path. |
| <a id="mavenrepositorypathresultreport-verdict"></a>`verdict` | MavenRepositoryPathVerdict | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="mavenrepositorypathresultreport-detail"></a>`detail` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Human-readable comparison detail for one verification or reproducibility result entry. |
| <a id="mavenrepositorypathresultreport-raw-bytes-equal"></a>`raw_bytes_equal` | bool | no | Whether raw staged and rebuilt bytes matched before any archive-aware normalization. |
| <a id="mavenrepositorypathresultreport-normalized-match"></a>`normalized_match` | bool | no | Whether the staged and rebuilt repository path matched after applying the selected normalization mode. |
| <a id="mavenrepositorypathresultreport-staged-sha512"></a>`staged_sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | no | SHA-512 digest computed from the staged repository entry or retained artifact bytes. |
| <a id="mavenrepositorypathresultreport-rebuilt-sha512"></a>`rebuilt_sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | no | SHA-512 digest computed from the rebuilt source or secondary artifact bytes. |

<a id="mavenrepositorypathrulereport"></a>
### MavenRepositoryPathRuleReport

One regex-based Maven repository path rule retained for inspection.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`maven-repository-path-rule-report.schema.json`](/components/buildish-release-tooling/schemas/maven-repository-path-rule-report.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositorypathrulereport-pattern"></a>`pattern` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Regular-expression pattern used to match one family of repository paths. |
| <a id="mavenrepositorypathrulereport-mode"></a>`mode` | MavenRepositoryPathMode | yes | Comparison mode that the associated regex path rule applies to matching staged Maven repository paths. |

<a id="mavenrepositoryreproducibilitymetadata"></a>
### MavenRepositoryReproducibilityMetadata

Retained comparison metadata for one Maven repository reproducibility run.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`maven-repository-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/maven-repository-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryreproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryreproducibilitymetadata-kind"></a>`kind` | Literal['maven-repository'] | no | Declared artifact or report kind discriminator. |
| <a id="mavenrepositoryreproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="mavenrepositoryreproducibilitymetadata-comparison-mode"></a>`comparison_mode` | Literal['repository-tree'] | no | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="mavenrepositoryreproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="mavenrepositoryreproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="mavenrepositoryreproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="mavenrepositoryreproducibilitymetadata-repository-dir"></a>`repository_dir` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Repository-root-relative rebuild output directory that should contain the local Maven repository tree. |
| <a id="mavenrepositoryreproducibilitymetadata-require-signatures"></a>`require_signatures` | bool | no | Whether Maven repository reproducibility should require detached signature files to exist and compare successfully. |
| <a id="mavenrepositoryreproducibilitymetadata-path-rules"></a>`path_rules` | list[[MavenRepositoryPathRuleReport](#mavenrepositorypathrulereport)] | no | Regex-based per-path comparison rules that specialize the default Maven repository comparison behavior. |
| <a id="mavenrepositoryreproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="mavenrepositoryreproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="mavenrepositoryreproducibilitymetadata-verified-path-count"></a>`verified_path_count` | int | no | Number of Maven repository paths that Buildish compared locally under the active repository-tree policy. |
| <a id="mavenrepositoryreproducibilitymetadata-failed-path-count"></a>`failed_path_count` | int | no | Number of Maven repository paths whose reproducibility comparison ended in a failure state. |
| <a id="mavenrepositoryreproducibilitymetadata-skipped-path-count"></a>`skipped_path_count` | int | no | Number of Maven repository paths that Buildish skipped from local comparison because policy marked them remote-only. |
| <a id="mavenrepositoryreproducibilitymetadata-path-results"></a>`path_results` | list[[MavenRepositoryPathResultReport](#mavenrepositorypathresultreport)] | no | Per-path Maven repository reproducibility results retained for later inspection or reporting. |
| <a id="mavenrepositoryreproducibilitymetadata-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="mavenrepositorysecondaryartifact"></a>
### MavenRepositorySecondaryArtifact

A staged Maven repository validated through a signed inventory.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositorysecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositorysecondaryartifact-kind"></a>`kind` | Literal['maven-repository'] | no | Declared artifact or report kind discriminator. |
| <a id="mavenrepositorysecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="mavenrepositorysecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="mavenrepositorysecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="mavenrepositorysecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="mavenrepositorysecondaryartifact-inventory"></a>`inventory` | [SupplementalInventoryReference](#supplementalinventoryreference) | yes | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="mavenrepositorysecondaryartifact-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositorysecondaryartifact-base-url"></a>`base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |

<a id="mavenrepositoryverificationreport"></a>
### MavenRepositoryVerificationReport

Verification report for one staged Maven repository.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryverificationreport-kind"></a>`kind` | Literal['maven-repository'] | no | Declared artifact or report kind discriminator. |
| <a id="mavenrepositoryverificationreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="mavenrepositoryverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="mavenrepositoryverificationreport-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositoryverificationreport-base-url"></a>`base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |
| <a id="mavenrepositoryverificationreport-inventory"></a>`inventory` | [InventoryVerificationReport](#inventoryverificationreport) | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="mavenrepositoryverificationreport-live-repository"></a>`live_repository` | [LiveMavenRepositoryReport](#livemavenrepositoryreport) | yes | Live staged Maven repository verification details collected alongside the signed inventory checks. |
| <a id="mavenrepositoryverificationreport-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

<a id="npmchecksums"></a>
### NpmChecksums

A checksum block for npm artifacts, which may use sha256 or sha512.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="npmchecksums-sha256"></a>`sha256` | [Sha256ChecksumPayload](#sha256checksumpayload) | no | SHA-256 checksum payload associated with the related artifact. |
| <a id="npmchecksums-sha512"></a>`sha512` | [Sha512ChecksumPayload](#sha512checksumpayload) | no | SHA-512 checksum payload associated with the related artifact. |

<a id="npmpackagesecondaryartifact"></a>
### NpmPackageSecondaryArtifact

A published npm package tarball.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="npmpackagesecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="npmpackagesecondaryartifact-kind"></a>`kind` | Literal['npm-package'] | no | Declared artifact or report kind discriminator. |
| <a id="npmpackagesecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="npmpackagesecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="npmpackagesecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="npmpackagesecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="npmpackagesecondaryartifact-inventory"></a>`inventory` | object | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="npmpackagesecondaryartifact-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="npmpackagesecondaryartifact-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="npmpackagesecondaryartifact-registry-url"></a>`registry_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Registry metadata URL used for npm package verification. |
| <a id="npmpackagesecondaryartifact-package-name"></a>`package_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Normalized npm package name associated with the related package artifact or registry lookup. |
| <a id="npmpackagesecondaryartifact-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="npmpackagesecondaryartifact-integrity"></a>`integrity` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Integrity verification details derived from registry metadata or sidecar checksums. |
| <a id="npmpackagesecondaryartifact-checksums"></a>`checksums` | [NpmChecksums](#npmchecksums) | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="npmpackagesecondaryartifact-authenticity"></a>`authenticity` | [NpmProvenanceAuth](#npmprovenanceauth) | no | Authenticity metadata, such as provenance or attestation references, associated with the related package artifact. |

<a id="npmpackageverificationreport"></a>
### NpmPackageVerificationReport

Verification report for one npm package.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="npmpackageverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="npmpackageverificationreport-kind"></a>`kind` | Literal['npm-package'] | no | Declared artifact or report kind discriminator. |
| <a id="npmpackageverificationreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="npmpackageverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="npmpackageverificationreport-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="npmpackageverificationreport-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="npmpackageverificationreport-registry-url"></a>`registry_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Registry metadata URL used for npm package verification. |
| <a id="npmpackageverificationreport-package-name"></a>`package_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Normalized npm package name associated with the related package artifact or registry lookup. |
| <a id="npmpackageverificationreport-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="npmpackageverificationreport-integrity"></a>`integrity` | [IntegrityVerificationReport](#integrityverificationreport) | yes | Integrity verification details derived from registry metadata or sidecar checksums. |
| <a id="npmpackageverificationreport-checksum"></a>`checksum` | [ChecksumVerificationReport](#checksumverificationreport) | yes | Checksum verification details for one downloaded or rebuilt artifact. |
| <a id="npmpackageverificationreport-registry-resolution"></a>`registry_resolution` | [NpmRegistryResolutionReport](#npmregistryresolutionreport) | yes | Registry-resolution details collected while verifying the related npm package tarball. |
| <a id="npmpackageverificationreport-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

<a id="npmprovenanceauth"></a>
### NpmProvenanceAuth

Explicit npm provenance metadata.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="npmprovenanceauth-scheme"></a>`scheme` | Literal['npm-provenance'] | no | Stable scheme identifier that names the authenticity or provenance mechanism represented by the related payload. |
| <a id="npmprovenanceauth-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |

<a id="npmregistryresolutionreport"></a>
### NpmRegistryResolutionReport

Resolution details for one npm registry lookup.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="npmregistryresolutionreport-metadata-url"></a>`metadata_url` | str | no | Registry metadata URL that Buildish fetched while resolving npm package verification data. |
| <a id="npmregistryresolutionreport-found-via"></a>`found_via` | str | no | Short note describing how the related package URL or artifact metadata was discovered during verification. |
| <a id="npmregistryresolutionreport-tarball-url-matches-manifest"></a>`tarball_url_matches_manifest` | bool | no | Whether the tarball URL resolved from the npm registry metadata matched the URL declared in the signed manifest. |
| <a id="npmregistryresolutionreport-integrity-matches-manifest"></a>`integrity_matches_manifest` | bool | no | Whether the integrity string or digest resolved from the registry matched the value declared in the signed manifest. |
| <a id="npmregistryresolutionreport-signatures-count"></a>`signatures_count` | int | yes | Number of signature records or provenance signatures that the registry metadata exposed for the related npm package artifact. |

<a id="ociimagereproducibilitymetadata"></a>
### OciImageReproducibilityMetadata

Retained comparison metadata for one OCI image reproducibility run.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`oci-image-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/oci-image-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociimagereproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="ociimagereproducibilitymetadata-kind"></a>`kind` | Literal['oci-image'] | no | Declared artifact or report kind discriminator. |
| <a id="ociimagereproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="ociimagereproducibilitymetadata-comparison-mode"></a>`comparison_mode` | Literal['platform-digest', 'provenance-only'] | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="ociimagereproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="ociimagereproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="ociimagereproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="ociimagereproducibilitymetadata-image-ref"></a>`image_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Fully qualified OCI image reference used for inspection or local rebuild comparison. |
| <a id="ociimagereproducibilitymetadata-declared-digest"></a>`declared_digest` | [OciContentDigest](../release-shared-types-reference/#ocicontentdigest) | yes | Signed or declared digest that the rebuilt value is compared against. |
| <a id="ociimagereproducibilitymetadata-expected-platform-digests"></a>`expected_platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Platform-specific OCI digests that the reproducibility check expected to reproduce for the rebuilt image. |
| <a id="ociimagereproducibilitymetadata-rebuilt-digest"></a>`rebuilt_digest` | [OciContentDigest](../release-shared-types-reference/#ocicontentdigest) | no | Digest produced by rebuilding the related OCI image locally. |
| <a id="ociimagereproducibilitymetadata-rebuilt-platform-digests"></a>`rebuilt_platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Platform digests produced by rebuilding the related multi-platform OCI image. |
| <a id="ociimagereproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="ociimagereproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="ociimagereproducibilitymetadata-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="ociimagesecondaryartifact"></a>
### OciImageSecondaryArtifact

An immutable OCI image reference.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociimagesecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="ociimagesecondaryartifact-kind"></a>`kind` | Literal['oci-image'] | no | Declared artifact or report kind discriminator. |
| <a id="ociimagesecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="ociimagesecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="ociimagesecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="ociimagesecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="ociimagesecondaryartifact-inventory"></a>`inventory` | object | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="ociimagesecondaryartifact-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="ociimagesecondaryartifact-registry"></a>`registry` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Container registry host or namespace that serves the related OCI image. |
| <a id="ociimagesecondaryartifact-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="ociimagesecondaryartifact-digest"></a>`digest` | [OciContentDigest](../release-shared-types-reference/#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |
| <a id="ociimagesecondaryartifact-platform-digests"></a>`platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Per-platform OCI digests declared or observed for a multi-platform image. |

<a id="ociimageverificationreport"></a>
### OciImageVerificationReport

Verification report for one OCI image.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociimageverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="ociimageverificationreport-kind"></a>`kind` | Literal['oci-image'] | no | Declared artifact or report kind discriminator. |
| <a id="ociimageverificationreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="ociimageverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="ociimageverificationreport-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="ociimageverificationreport-registry"></a>`registry` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Container registry host or namespace that serves the related OCI image. |
| <a id="ociimageverificationreport-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="ociimageverificationreport-digest"></a>`digest` | [OciContentDigest](../release-shared-types-reference/#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |
| <a id="ociimageverificationreport-inspection"></a>`inspection` | [OciInspectionReport](#ociinspectionreport) | yes | Live inspection result block for the related artifact or platform resource. |
| <a id="ociimageverificationreport-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

<a id="ociinspectionreport"></a>
### OciInspectionReport

Observed registry inspection results for one OCI image.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociinspectionreport-image-ref"></a>`image_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Fully qualified OCI image reference used for inspection or local rebuild comparison. |
| <a id="ociinspectionreport-digest-matches-manifest"></a>`digest_matches_manifest` | bool | yes | Whether the inspected OCI image digest matched the digest declared in the signed manifest. |
| <a id="ociinspectionreport-platform-digests-match"></a>`platform_digests_match` | bool | no | Whether all inspected OCI platform digests matched the platform digests declared in the signed manifest. |
| <a id="ociinspectionreport-platform-digests"></a>`platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Per-platform OCI digests declared or observed for a multi-platform image. |

<a id="ociplatformdigest"></a>
### OciPlatformDigest

One platform-specific digest declared for an OCI image.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociplatformdigest-platform"></a>`platform` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | OCI platform identifier in `os/arch[/variant]` form. |
| <a id="ociplatformdigest-digest"></a>`digest` | [OciContentDigest](../release-shared-types-reference/#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |

<a id="pypiattestationauth"></a>
### PyPiAttestationAuth

Explicit PyPI attestation metadata.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pypiattestationauth-scheme"></a>`scheme` | Literal['pypi-attestation'] | no | Stable scheme identifier that names the authenticity or provenance mechanism represented by the related payload. |
| <a id="pypiattestationauth-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |

<a id="pythondistributionsecondaryartifact"></a>
### PythonDistributionSecondaryArtifact

A published Python distribution file.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pythondistributionsecondaryartifact-artifact-id"></a>`artifact_id` | object | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="pythondistributionsecondaryartifact-kind"></a>`kind` | Literal['python-distribution'] | no | Declared artifact or report kind discriminator. |
| <a id="pythondistributionsecondaryartifact-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="pythondistributionsecondaryartifact-artifact-origin"></a>`artifact_origin` | object | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="pythondistributionsecondaryartifact-git-commit-sha"></a>`git_commit_sha` | object | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="pythondistributionsecondaryartifact-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="pythondistributionsecondaryartifact-inventory"></a>`inventory` | object | no | Signed inventory or supplemental staging metadata associated with the related artifact. |
| <a id="pythondistributionsecondaryartifact-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="pythondistributionsecondaryartifact-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="pythondistributionsecondaryartifact-index-url"></a>`index_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base Python simple-index URL that Buildish used for package verification. |
| <a id="pythondistributionsecondaryartifact-project-name"></a>`project_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Python package project name associated with the related distribution artifact. |
| <a id="pythondistributionsecondaryartifact-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="pythondistributionsecondaryartifact-checksums"></a>`checksums` | [Sha256Checksums](#sha256checksums) | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="pythondistributionsecondaryartifact-authenticity"></a>`authenticity` | [PyPiAttestationAuth](#pypiattestationauth) | no | Authenticity metadata, such as provenance or attestation references, associated with the related package artifact. |

<a id="pythondistributionverificationreport"></a>
### PythonDistributionVerificationReport

Verification report for one Python distribution.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pythondistributionverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="pythondistributionverificationreport-kind"></a>`kind` | Literal['python-distribution'] | no | Declared artifact or report kind discriminator. |
| <a id="pythondistributionverificationreport-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="pythondistributionverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="pythondistributionverificationreport-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="pythondistributionverificationreport-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="pythondistributionverificationreport-index-url"></a>`index_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base Python simple-index URL that Buildish used for package verification. |
| <a id="pythondistributionverificationreport-project-name"></a>`project_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Python package project name associated with the related distribution artifact. |
| <a id="pythondistributionverificationreport-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="pythondistributionverificationreport-checksum"></a>`checksum` | [ChecksumVerificationReport](#checksumverificationreport) | yes | Checksum verification details for one downloaded or rebuilt artifact. |
| <a id="pythondistributionverificationreport-index-resolution"></a>`index_resolution` | [PythonIndexResolutionReport](#pythonindexresolutionreport) | yes | Python package-index resolution details collected while locating the staged distribution artifact. |
| <a id="pythondistributionverificationreport-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

<a id="pythonindexresolutionreport"></a>
### PythonIndexResolutionReport

Resolution details for one Python simple-index lookup.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pythonindexresolutionreport-project-index-url"></a>`project_index_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved Python simple-index page URL that Buildish used to discover the expected distribution artifact. |
| <a id="pythonindexresolutionreport-resolved-url"></a>`resolved_url` | str | no | Resolved direct distribution or tarball URL that Buildish selected from the related package index. |
| <a id="pythonindexresolutionreport-found-via"></a>`found_via` | str | no | Short note describing how the related package URL or artifact metadata was discovered during verification. |
| <a id="pythonindexresolutionreport-sha256-matches-index"></a>`sha256_matches_index` | bool | no | Whether the distribution hash from the Python simple index matched the digest declared in the signed manifest. |

<a id="rcvotemanifestv1"></a>
### RcVoteManifestV1

Strict authoritative RC vote manifest emitted by buildish-release-tooling.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`rc-vote-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/rc-vote-manifest-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: `rc-vote-manifest.json`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="rcvotemanifestv1-schema-version"></a>`schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="rcvotemanifestv1-manifest-type"></a>`manifest_type` | Literal['rc-vote'] | no | Stable manifest contract discriminator for one Buildish file format. |
| <a id="rcvotemanifestv1-component-id"></a>`component_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="rcvotemanifestv1-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="rcvotemanifestv1-release-line"></a>`release_line` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="rcvotemanifestv1-release-branch"></a>`release_branch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git branch name that Buildish resolved as the authoritative release branch. |
| <a id="rcvotemanifestv1-source-repository-url"></a>`source_repository_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical source repository URL recorded in the RC vote manifest or verification report. |
| <a id="rcvotemanifestv1-source-commit-sha"></a>`source_commit_sha` | [GitCommitSha](../release-shared-types-reference/#gitcommitsha) | yes | Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report. |
| <a id="rcvotemanifestv1-source-date-epoch"></a>`source_date_epoch` | int | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="rcvotemanifestv1-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="rcvotemanifestv1-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="rcvotemanifestv1-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |
| <a id="rcvotemanifestv1-provenance"></a>`provenance` | [ManifestProvenance](#manifestprovenance) | yes | Tooling, workflow, or publication provenance block embedded in or read from the related Buildish contract. |
| <a id="rcvotemanifestv1-trust-roots"></a>`trust_roots` | [ManifestTrustRoots](#manifesttrustroots) | yes | Pinned trust-root material that verify-rc uses to establish authenticity for the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-draft-github-release"></a>`draft_github_release` | [DraftGithubRelease](#draftgithubrelease) | yes | Draft GitHub release metadata embedded in or read from the RC vote manifest. |
| <a id="rcvotemanifestv1-vote-materials"></a>`vote_materials` | [VoteMaterialsStrict](#votematerialsstrict) | yes | Vote-materials reference block embedded in or read from the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-verification"></a>`verification` | [ManifestVerificationMetadataStrict](#manifestverificationmetadatastrict) | yes | Verification metadata block nested inside the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-materialized-commit-sha"></a>`materialized_commit_sha` | [GitCommitSha](../release-shared-types-reference/#gitcommitsha) | no | Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow. |

<a id="rebuiltoutputsnapshot"></a>
### RebuiltOutputSnapshot

One rebuilt output file described inside an inspection-bundle metadata document.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`rebuilt-output-snapshot.schema.json`](/components/buildish-release-tooling/schemas/rebuilt-output-snapshot.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="rebuiltoutputsnapshot-path"></a>`path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="rebuiltoutputsnapshot-sha512"></a>`sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="rebuiltoutputsnapshot-size-bytes"></a>`size_bytes` | int | yes | Byte size recorded for the related artifact, retained snapshot, or inventory entry. |

<a id="reproducibilityexecutionsection"></a>
### ReproducibilityExecutionSection

Run-level policy and execution summary for build-based reproducibility checks.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="reproducibilityexecutionsection-requested-mode"></a>`requested_mode` | Literal['auto', 'integrity-only', 'full'] | yes | Verify-rc mode explicitly requested by the caller. |
| <a id="reproducibilityexecutionsection-effective-mode"></a>`effective_mode` | Literal['integrity-only', 'full'] | yes | Verify mode that Buildish actually executed after evaluating prompts, runtime policy, and caller intent. |
| <a id="reproducibilityexecutionsection-build-checks-attempted"></a>`build_checks_attempted` | bool | yes | Whether the command attempted local reproducibility or rebuild checks during this run. |
| <a id="reproducibilityexecutionsection-execution-backend"></a>`execution_backend` | Literal['none', 'host-direct'] | no | Execution backend that verify-rc used for the recorded reproducibility run. |
| <a id="reproducibilityexecutionsection-inherits-host-home"></a>`inherits_host_home` | bool | no | Whether the reproducibility execution inherited the caller's existing `HOME` rather than using an isolated home directory. |
| <a id="reproducibilityexecutionsection-prompt-used"></a>`prompt_used` | bool | no | Whether Buildish prompted before enabling the recorded reproducibility execution mode. |
| <a id="reproducibilityexecutionsection-prompt-confirmed"></a>`prompt_confirmed` | bool | no | Whether the caller confirmed a prompt before Buildish escalated from integrity-only verification to full local rebuild checks. |
| <a id="reproducibilityexecutionsection-skipped-reason"></a>`skipped_reason` | str | no | Reason why Buildish skipped local rebuild execution after evaluating the requested verify mode and runtime constraints. |

<a id="reproducibilityselector"></a>
### ReproducibilitySelector

Signed manifest selector for one canonical local reproducibility profile.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="reproducibilityselector-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |

<a id="retainedartifactsnapshot"></a>
### RetainedArtifactSnapshot

One retained file snapshot described inside an inspection-bundle metadata document.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`retained-artifact-snapshot.schema.json`](/components/buildish-release-tooling/schemas/retained-artifact-snapshot.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="retainedartifactsnapshot-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="retainedartifactsnapshot-sha512"></a>`sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="retainedartifactsnapshot-size-bytes"></a>`size_bytes` | int | yes | Byte size recorded for the related artifact, retained snapshot, or inventory entry. |

<a id="secondaryartifactbase"></a>
### SecondaryArtifactBase

Common fields shared across supported secondary artifact kinds.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`secondary-artifact-base.schema.json`](/components/buildish-release-tooling/schemas/secondary-artifact-base.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="secondaryartifactbase-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="secondaryartifactbase-kind"></a>`kind` | str | yes | Declared artifact or report kind discriminator. |
| <a id="secondaryartifactbase-role"></a>`role` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="secondaryartifactbase-artifact-origin"></a>`artifact_origin` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="secondaryartifactbase-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](../release-shared-types-reference/#gitcommitsha) | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="secondaryartifactbase-reproducibility"></a>`reproducibility` | [ReproducibilitySelector](#reproducibilityselector) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="secondaryartifactbase-inventory"></a>`inventory` | [SupplementalInventoryReference](#supplementalinventoryreference) | no | Signed inventory or supplemental staging metadata associated with the related artifact. |

<a id="secondaryartifactmanifestv1"></a>
### SecondaryArtifactManifestV1

A reusable secondary-artifact manifest fragment.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`secondary-artifact-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/secondary-artifact-manifest-v1.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: `artifact-manifest.json`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="secondaryartifactmanifestv1-secondary-artifacts"></a>`secondary_artifacts` | list[AnySecondaryArtifact] | yes | Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest. |

<a id="sha256checksumpayload"></a>
### Sha256ChecksumPayload

One sha256 checksum value and optional detached sidecar URI.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sha256checksumpayload-value"></a>`value` | [Sha256Hex](../release-shared-types-reference/#sha256hex) | yes | Declared checksum or digest value recorded in the related payload. |
| <a id="sha256checksumpayload-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

<a id="sha256checksums"></a>
### Sha256Checksums

A checksum block containing one sha256 entry.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sha256checksums-sha256"></a>`sha256` | [Sha256ChecksumPayload](#sha256checksumpayload) | yes | SHA-256 checksum payload associated with the related artifact. |

<a id="sha512checksumpayload"></a>
### Sha512ChecksumPayload

One sha512 checksum value and optional detached sidecar URI.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sha512checksumpayload-value"></a>`value` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | Declared checksum or digest value recorded in the related payload. |
| <a id="sha512checksumpayload-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

<a id="sha512checksums"></a>
### Sha512Checksums

A checksum block containing one sha512 entry.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sha512checksums-sha512"></a>`sha512` | [Sha512ChecksumPayload](#sha512checksumpayload) | yes | SHA-512 checksum payload associated with the related artifact. |

<a id="shallowarchiveanalysisreport"></a>
### ShallowArchiveAnalysisReport

Durable shallow archive-comparison findings for one retained artifact pair.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="shallowarchiveanalysisreport-classification"></a>`classification` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | High-level shallow-comparison classification that summarizes the most important archive drift pattern Buildish observed. |
| <a id="shallowarchiveanalysisreport-raw-bytes-equal"></a>`raw_bytes_equal` | bool | yes | Whether raw staged and rebuilt bytes matched before any archive-aware normalization. |
| <a id="shallowarchiveanalysisreport-archive-format"></a>`archive_format` | Literal['tar', 'zip'] | no | Detected top-level archive format of the compared artifact when shallow archive inspection succeeded. |
| <a id="shallowarchiveanalysisreport-staged-archive-format"></a>`staged_archive_format` | ArchiveAnalysisFormat | yes | Detected top-level archive format of the staged artifact retained for shallow archive inspection. |
| <a id="shallowarchiveanalysisreport-rebuilt-archive-format"></a>`rebuilt_archive_format` | ArchiveAnalysisFormat | yes | Detected top-level archive format of the rebuilt artifact retained for shallow archive inspection. |
| <a id="shallowarchiveanalysisreport-staged-entry-count"></a>`staged_entry_count` | int | no | Number of top-level archive entries found in the staged artifact during shallow inspection. |
| <a id="shallowarchiveanalysisreport-rebuilt-entry-count"></a>`rebuilt_entry_count` | int | no | Number of top-level archive entries found in the rebuilt artifact during shallow inspection. |
| <a id="shallowarchiveanalysisreport-missing-paths"></a>`missing_paths` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Archive or repository paths that were present in the staged artifact but missing from the rebuilt artifact. |
| <a id="shallowarchiveanalysisreport-unexpected-paths"></a>`unexpected_paths` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Archive or repository paths that were present only in the rebuilt artifact and not in the staged artifact. |
| <a id="shallowarchiveanalysisreport-entry-order-mismatches"></a>`entry_order_mismatches` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Archive-entry ordering differences detected between the staged and rebuilt artifacts during shallow comparison. |
| <a id="shallowarchiveanalysisreport-metadata-mismatches"></a>`metadata_mismatches` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Archive-entry metadata differences, such as timestamps, modes, owners, or file-type drift, found during shallow comparison. |
| <a id="shallowarchiveanalysisreport-content-mismatches"></a>`content_mismatches` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | no | Archive member paths whose direct top-level content bytes differed between the staged and rebuilt artifacts during shallow comparison. |

<a id="signaturereference"></a>
### SignatureReference

One detached OpenPGP signature reference.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="signaturereference-type"></a>`type` | Literal['openpgp-detached-ascii-armored'] | no | Stable subtype discriminator or signature-reference type for the related payload. |
| <a id="signaturereference-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

<a id="signatureverificationpayload"></a>
### SignatureVerificationPayload

Serialized detached-signature verification details.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="signatureverificationpayload-signer-fingerprint"></a>`signer_fingerprint` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | OpenPGP fingerprint of the key that verified the related detached signature. |
| <a id="signatureverificationpayload-signer-user-id"></a>`signer_user_id` | str | no | Primary user id string reported by GnuPG for the key that verified the related detached signature. |
| <a id="signatureverificationpayload-trust-label"></a>`trust_label` | str | no | Human-readable GnuPG trust label returned by signature verification. |
| <a id="signatureverificationpayload-key-algorithm"></a>`key_algorithm` | str | no | Public-key algorithm reported for the signing key that verified the related detached signature. |
| <a id="signatureverificationpayload-key-size-bits"></a>`key_size_bits` | int | no | Public-key size, in bits, reported for the signing key that verified the related detached signature. |

<a id="sourceartifactcontract"></a>
### SourceArtifactContract

The single source artifact under vote.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sourceartifactcontract-role"></a>`role` | Literal['asf-source-release'] | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="sourceartifactcontract-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="sourceartifactcontract-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="sourceartifactcontract-artifact-origin"></a>`artifact_origin` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="sourceartifactcontract-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](../release-shared-types-reference/#gitcommitsha) | yes | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="sourceartifactcontract-reproducibility"></a>`reproducibility` | [ReproducibilitySelector](#reproducibilityselector) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="sourceartifactcontract-checksums"></a>`checksums` | [Sha512Checksums](#sha512checksums) | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="sourceartifactcontract-signatures"></a>`signatures` | list[[SignatureReference](#signaturereference)] | yes | Declared detached signature references associated with the related artifact or manifest. |

<a id="sourceartifactcontractread"></a>
### SourceArtifactContractRead

Tolerant source-artifact contract accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sourceartifactcontractread-role"></a>`role` | object | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="sourceartifactcontractread-filename"></a>`filename` | object | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="sourceartifactcontractread-uri"></a>`uri` | object | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="sourceartifactcontractread-artifact-origin"></a>`artifact_origin` | object | yes | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="sourceartifactcontractread-git-commit-sha"></a>`git_commit_sha` | object | yes | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="sourceartifactcontractread-reproducibility"></a>`reproducibility` | object | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="sourceartifactcontractread-checksums"></a>`checksums` | object | yes | Declared checksum sidecars or signed checksum values associated with this artifact. |
| <a id="sourceartifactcontractread-signatures"></a>`signatures` | object | yes | Declared detached signature references associated with the related artifact or manifest. |

<a id="sourceartifactreproducibilitymetadata"></a>
### SourceArtifactReproducibilityMetadata

Retained comparison metadata for source-artifact reproducibility inspection.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`source-artifact-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/source-artifact-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sourceartifactreproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="sourceartifactreproducibilitymetadata-comparison-mode"></a>`comparison_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="sourceartifactreproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="sourceartifactreproducibilitymetadata-archive-analysis"></a>`archive_analysis` | [ShallowArchiveAnalysisReport](#shallowarchiveanalysisreport) | no | Shallow top-level archive comparison details retained for reproducibility inspection. |
| <a id="sourceartifactreproducibilitymetadata-staged-artifact"></a>`staged_artifact` | [RetainedArtifactSnapshot](#retainedartifactsnapshot) | yes | Retained snapshot metadata for the staged artifact bytes used as the comparison target. |
| <a id="sourceartifactreproducibilitymetadata-rebuilt-artifact"></a>`rebuilt_artifact` | [RetainedArtifactSnapshot](#retainedartifactsnapshot) | no | Retained snapshot metadata for one rebuilt artifact copy in the inspection bundle. |
| <a id="sourceartifactreproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="sourceartifactreproducibilitymetadata-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="sourceartifactverificationsection"></a>
### SourceArtifactVerificationSection

Source-artifact verification section of the verify-rc report.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sourceartifactverificationsection-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="sourceartifactverificationsection-filename"></a>`filename` | str | no | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="sourceartifactverificationsection-uri"></a>`uri` | str | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="sourceartifactverificationsection-sha512"></a>`sha512` | str | no | SHA-512 checksum payload associated with the related artifact. |
| <a id="sourceartifactverificationsection-sha512-sidecar-verified"></a>`sha512_sidecar_verified` | bool | yes | Whether the staged source-artifact `.sha512` sidecar was fetched and verified successfully. |
| <a id="sourceartifactverificationsection-signature"></a>`signature` | [SignatureVerificationPayload](#signatureverificationpayload) | no | Signature verification details for the related artifact or manifest. |
| <a id="sourceartifactverificationsection-rebuilt-sha512"></a>`rebuilt_sha512` | str | no | SHA-512 digest computed from the rebuilt source or secondary artifact bytes. |
| <a id="sourceartifactverificationsection-matches-source-commit-sha"></a>`matches_source_commit_sha` | bool | yes | Whether the rebuilt source artifact bytes matched the source commit selected by the authoritative manifest. |
| <a id="sourceartifactverificationsection-reproducibility"></a>`reproducibility` | [ArtifactReproducibilityReport](#artifactreproducibilityreport) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="sourceartifactverificationsection-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |

<a id="supplementalinventoryreference"></a>
### SupplementalInventoryReference

One staged supplemental inventory attachment.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="supplementalinventoryreference-filename"></a>`filename` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="supplementalinventoryreference-sha512"></a>`sha512` | [Sha512Hex](../release-shared-types-reference/#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="supplementalinventoryreference-uri"></a>`uri` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="supplementalinventoryreference-entry-count"></a>`entry_count` | int | no | Number of entries recorded in the related inventory, repository snapshot, or artifact collection. |
| <a id="supplementalinventoryreference-total-size-bytes"></a>`total_size_bytes` | int | no | Total size, in bytes, recorded for the related artifact collection or inventory. |

<a id="toolingprovenance"></a>
### ToolingProvenance

Tooling repository provenance embedded in emitted manifests.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="toolingprovenance-repository"></a>`repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="toolingprovenance-repository-url"></a>`repository_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical clone or browser URL for the related repository. |
| <a id="toolingprovenance-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](../release-shared-types-reference/#gitcommitsha) | yes | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="toolingprovenance-git-ref"></a>`git_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Git ref name recorded in tooling provenance for the related manifest or emitted file. |
| <a id="toolingprovenance-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | no | Release version string without a leading `v` prefix. |

<a id="verificationfailurepayload"></a>
### VerificationFailurePayload

One collected verification failure.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verificationfailurepayload-scope"></a>`scope` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Machine-readable scope label that identifies which verification surface produced the related failure record. |
| <a id="verificationfailurepayload-subject"></a>`subject` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Human-facing verification failure subject that identifies what failed. |
| <a id="verificationfailurepayload-message"></a>`message` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |

<a id="verifyrcreportv1"></a>
### VerifyRcReportV1

Machine-readable Phase 1a RC verification report.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`verify-rc-report-v1.schema.json`](/components/buildish-release-tooling/schemas/verify-rc-report-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcreportv1-schema-version"></a>`schema_version` | [SchemaVersionV1](../release-shared-types-reference/#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="verifyrcreportv1-report-type"></a>`report_type` | Literal['verify-rc'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="verifyrcreportv1-component-id"></a>`component_id` | str | no | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="verifyrcreportv1-version"></a>`version` | str | no | Release version string without a leading `v` prefix. |
| <a id="verifyrcreportv1-rc-tag"></a>`rc_tag` | str | no | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="verifyrcreportv1-source-commit-sha"></a>`source_commit_sha` | str | no | Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report. |
| <a id="verifyrcreportv1-source-date-epoch"></a>`source_date_epoch` | int | no | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="verifyrcreportv1-source-repository-url"></a>`source_repository_url` | str | no | Canonical source repository URL recorded in the RC vote manifest or verification report. |
| <a id="verifyrcreportv1-manifest-url"></a>`manifest_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | URL of the RC vote manifest that Buildish fetched or verified. |
| <a id="verifyrcreportv1-keys-url"></a>`keys_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF KEYS URL that Buildish used or expected while establishing the RC trust roots. |
| <a id="verifyrcreportv1-verdict"></a>`verdict` | [VerificationVerdict](../release-shared-types-reference/#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="verifyrcreportv1-work-dir"></a>`work_dir` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the verify-rc working directory where retained reports, logs, and downloaded artifacts were stored. |
| <a id="verifyrcreportv1-failures"></a>`failures` | list[[VerificationFailurePayload](#verificationfailurepayload)] | no | Collected verification failures that caused the enclosing report verdict to fail. |
| <a id="verifyrcreportv1-manifest-verification"></a>`manifest_verification` | [ManifestVerificationSection](#manifestverificationsection) | yes | Manifest trust-chain verification section of the verify-rc report. |
| <a id="verifyrcreportv1-source-artifact-verification"></a>`source_artifact_verification` | [SourceArtifactVerificationSection](#sourceartifactverificationsection) | yes | Source-artifact verification section of the verify-rc report. |
| <a id="verifyrcreportv1-reproducibility-execution"></a>`reproducibility_execution` | [ReproducibilityExecutionSection](#reproducibilityexecutionsection) | yes | Run-level reproducibility execution policy and outcome block retained in the verify-rc report. |
| <a id="verifyrcreportv1-inspection-bundle"></a>`inspection_bundle` | [InspectionBundleSection](#inspectionbundlesection) | no | Inspection-bundle location block retained in the verify-rc report for later inspect-repro analysis. |
| <a id="verifyrcreportv1-secondary-artifact-verifications"></a>`secondary_artifact_verifications` | list[AnySecondaryArtifactVerification] | no | Per-artifact verification sections for all secondary artifacts processed during verify-rc. |

<a id="votematerialsread"></a>
### VoteMaterialsRead

Tolerant vote-materials block used by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`vote-materials-read.schema.json`](/components/buildish-release-tooling/schemas/vote-materials-read.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="votematerialsread-source-artifacts"></a>`source_artifacts` | list[[SourceArtifactContractRead](#sourceartifactcontractread)] | yes | Manifest entries that describe the primary staged source artifact and any additional source-release materials. |
| <a id="votematerialsread-secondary-artifacts"></a>`secondary_artifacts` | list[AnySecondaryArtifact \| SecondaryArtifactEnvelopeRead] | no | Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest, including tolerant read-side envelopes for malformed entries. |

<a id="votematerialsstrict"></a>
### VoteMaterialsStrict

Strict vote-materials block for authored and emitted manifests.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`vote-materials-strict.schema.json`](/components/buildish-release-tooling/schemas/vote-materials-strict.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="votematerialsstrict-source-artifacts"></a>`source_artifacts` | list[[SourceArtifactContract](#sourceartifactcontract)] | yes | Manifest entries that describe the primary staged source artifact and any additional source-release materials. |
| <a id="votematerialsstrict-secondary-artifacts"></a>`secondary_artifacts` | list[AnySecondaryArtifact] | no | Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest. |

