---
title: "Release model schema reference"
description: "This reference is generated from the Buildish Release Tooling Pydantic models and checked-in reference metadata. Do not edit it by hand; regenerate it with `make schemas`."
weight: 30
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

This reference describes the typed Buildish Release Tooling contracts that are checked into this repository.
It covers supported external configuration and verification/report contracts, plus internal runtime contracts and internal unstable command action manifests.
Use the contract-file tables to find the governing file or schema root, then follow the linked type sections below for exact field-level structure.

## How to read this reference

- contract-file tables identify stable checked-in file contracts where one exists
- `audience` distinguishes supported external contracts from Buildish-owned internal contracts
- `stability` distinguishes stable supported/internal contracts from intentionally unstable internal machine I/O
- field names are shown in their wire-format aliases
- type, enum, and alias names link to their definitions below
- schema files link to the published JSON Schema contract for the matching root type

## File contract index

### Supported authored file contracts

Consumer-authored or component-authored file contracts that are part of the supported external release-tooling surface.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `release-config.yaml` | [ComponentConfig](#componentconfig) | [`buildish-release-tooling-component-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-component-config.schema.json) | `supported` | `stable` | Component-authored `release-config.yaml` contract for release policy and target integration settings. |

### Supported emitted file contracts

Stable emitted Buildish file contracts that workflows or humans may intentionally consume.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `inspection-bundle.json` | [InspectionBundleManifestV1](#inspectionbundlemanifestv1) | [`buildish-release-tooling-inspection-bundle-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspection-bundle-manifest-v1.schema.json) | `supported` | `stable` | Top-level manifest for a retained verify-rc inspection bundle. |
| `rc-vote-manifest.json` | [RcVoteManifestV1](#rcvotemanifestv1) | [`buildish-release-tooling-rc-vote-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rc-vote-manifest-v1.schema.json) | `supported` | `stable` | Signed RC vote manifest that declares the source artifact, trust roots, and secondary artifacts that verifiers must inspect. |

### Supported emitted non-file root contracts

Supported emitted JSON contract roots that do not correspond to one fixed checked-in path.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [InspectReproReportV1](#inspectreproreportv1) | [`buildish-release-tooling-inspect-repro-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspect-repro-report-v1.schema.json) | `supported` | `stable` | Machine-readable `inspect-repro --json` output contract. |
| [VerifyRcReportV1](#verifyrcreportv1) | [`buildish-release-tooling-verify-rc-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-report-v1.schema.json) | `supported` | `stable` | Machine-readable `verify-rc` report contract, typically written through `--report-json`. |

### Internal stable file contracts

Buildish-owned internal file contracts that are documented here for maintainability but are not part of the supported external API.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `harness/scenarios/*.yaml` | [HarnessScenario](#harnessscenario) | [`buildish-release-tooling-harness-scenario.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-scenario.schema.json) | `internal` | `stable` | Harness scenario contract for synthetic or `act`-backed release-workflow integration tests. |
| `harness/release-harness.yaml` | [ReleaseHarnessConfig](#releaseharnessconfig) | [`buildish-release-tooling-release-harness-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-harness-config.schema.json) | `internal` | `stable` | Committed harness configuration contract for local repository bindings and optional overrides. |
| `artifact-manifest.json` | [SecondaryArtifactManifestV1](#secondaryartifactmanifestv1) | [`buildish-release-tooling-secondary-artifact-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-manifest-v1.schema.json) | `internal` | `stable` | Typed secondary-artifact registration manifest fragment written by `record-artifact`. |

### Internal stable non-file root contracts

Buildish-owned internal root contracts and runtime payloads with stable current semantics but no external support promise.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AsfKeysTrustRootRead](#asfkeystrustrootread) | [`buildish-release-tooling-asf-keys-trust-root-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-asf-keys-trust-root-read.schema.json) | `internal` | `stable` | Tolerant read model for ASF KEYS trust-root references carried through vote-materials loading. |
| [AuthoritativeManifestReferenceRead](#authoritativemanifestreferenceread) | [`buildish-release-tooling-authoritative-manifest-reference-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-authoritative-manifest-reference-read.schema.json) | `internal` | `stable` | Tolerant read model for the authoritative signed manifest reference used by vote-materials loading. |
| [CommandContext](#commandcontext) | [`buildish-release-tooling-command-context.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-context.schema.json) | `internal` | `stable` | Runtime command context built from CLI arguments and validated component configuration. |
| [DraftGithubReleaseRead](#draftgithubreleaseread) | [`buildish-release-tooling-draft-github-release-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-draft-github-release-read.schema.json) | `internal` | `stable` | Tolerant read model for draft GitHub release coordinates recorded in vote materials. |
| [FileLikeReproducibilityMetadata](#filelikereproducibilitymetadata) | [`buildish-release-tooling-file-like-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-file-like-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for file-like reproducibility comparisons. |
| [HarnessBuiltinGhRefMutationPayload](#harnessbuiltinghrefmutationpayload) | [`buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json) | `internal` | `stable` | Harness shim builtin payload describing a synthetic GitHub ref mutation request. |
| [HarnessCommandTraceEntry](#harnesscommandtraceentry) | [`buildish-release-tooling-harness-command-trace-entry.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-command-trace-entry.schema.json) | `internal` | `stable` | Structured command-trace record emitted by the harness shim for one intercepted invocation. |
| [HarnessRunResultJson](#harnessrunresultjson) | [`buildish-release-tooling-harness-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for one harness scenario run. |
| [HarnessSequenceRunResultJson](#harnesssequencerunresultjson) | [`buildish-release-tooling-harness-sequence-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-sequence-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for a multi-scenario harness sequence run. |
| [HarnessShimState](#harnessshimstate) | [`buildish-release-tooling-harness-shim-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-shim-state.schema.json) | `internal` | `stable` | Persisted subprocess-facing harness shim state used by intercepted tool wrappers. |
| [MavenRepositoryInventoryV1](#mavenrepositoryinventoryv1) | [`buildish-release-tooling-maven-repository-inventory-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-inventory-v1.schema.json) | `internal` | `stable` | Signed Maven repository inventory contract emitted for staged Maven repository verification. |
| [MavenRepositoryPathResultReport](#mavenrepositorypathresultreport) | [`buildish-release-tooling-maven-repository-path-result-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-result-report.schema.json) | `internal` | `stable` | Per-path Maven repository reproducibility comparison result retained in bundle metadata. |
| [MavenRepositoryPathRuleReport](#mavenrepositorypathrulereport) | [`buildish-release-tooling-maven-repository-path-rule-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-rule-report.schema.json) | `internal` | `stable` | Rendered Maven repository per-path comparison rule retained in reproducibility metadata. |
| [MavenRepositoryReproducibilityMetadata](#mavenrepositoryreproducibilitymetadata) | [`buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for Maven repository reproducibility evidence. |
| [OciImageReproducibilityMetadata](#ociimagereproducibilitymetadata) | [`buildish-release-tooling-oci-image-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-oci-image-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for OCI image reproducibility evidence. |
| [PrepareRcState](#preparercstate) | [`buildish-release-tooling-prepare-rc-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-state.schema.json) | `internal` | `stable` | Resolved prepare-rc state persisted between release workflow steps. |
| [RebuiltOutputSnapshot](#rebuiltoutputsnapshot) | [`buildish-release-tooling-rebuilt-output-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rebuilt-output-snapshot.schema.json) | `internal` | `stable` | Snapshot of one rebuilt output retained in reproducibility metadata. |
| [ReleaseVersionState](#releaseversionstate) | [`buildish-release-tooling-release-version-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-state.schema.json) | `internal` | `stable` | Resolved release-version state persisted across final release workflow steps. |
| [ResolvedReleaseHarnessConfigJson](#resolvedreleaseharnessconfigjson) | [`buildish-release-tooling-resolved-release-harness-config-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-resolved-release-harness-config-json.schema.json) | `internal` | `stable` | Machine-readable JSON payload for one resolved harness configuration. |
| [RetainedArtifactSnapshot](#retainedartifactsnapshot) | [`buildish-release-tooling-retained-artifact-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-retained-artifact-snapshot.schema.json) | `internal` | `stable` | Snapshot of one retained staged or rebuilt artifact captured in reproducibility metadata. |
| [SecondaryArtifactBase](#secondaryartifactbase) | [`buildish-release-tooling-secondary-artifact-base.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-base.schema.json) | `internal` | `stable` | Common base shape shared across supported secondary-artifact manifest entries. |
| [SourceArtifactReproducibilityMetadata](#sourceartifactreproducibilitymetadata) | [`buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for source-artifact reproducibility evidence. |
| [VerifyRcOverrideFileConfig](#verifyrcoverridefileconfig) | [`buildish-release-tooling-verify-rc-override-file-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-override-file-config.schema.json) | `internal` | `stable` | Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`. |
| [VoteMaterialsRead](#votematerialsread) | [`buildish-release-tooling-vote-materials-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-read.schema.json) | `internal` | `stable` | Tolerant read model for vote materials consumed during verification and bootstrap workflows. |
| [VoteMaterialsStrict](#votematerialsstrict) | [`buildish-release-tooling-vote-materials-strict.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-strict.schema.json) | `internal` | `stable` | Strict typed vote-materials bundle assembled by release-tooling before RC publication. |

### Internal unstable command action manifests

Internal workflow-coordination manifests written by commands. These are documented to aid maintenance and debugging, but they are intentionally unstable.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AttachGithubReleaseAssetsManifest](#attachgithubreleaseassetsmanifest) | [`buildish-release-tooling-attach-github-release-assets-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-attach-github-release-assets-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `attach-github-release-assets`. |
| [BuildSourceRcManifest](#buildsourcercmanifest) | [`buildish-release-tooling-build-source-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-build-source-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `build-source-rc`. |
| [CleanupDevSvnRcsManifest](#cleanupdevsvnrcsmanifest) | [`buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `cleanup-dev-svn-rcs`. |
| [CommandActionManifest](#commandactionmanifest) | [`buildish-release-tooling-command-action-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-action-manifest.schema.json) | `internal` | `unstable` | Common top-level shape for internal unstable command action manifests written through `MANIFEST_PATH`. |
| [CreateFinalTagManifest](#createfinaltagmanifest) | [`buildish-release-tooling-create-final-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-final-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-final-tag`. |
| [CreateRcMaterializationTagManifest](#creatercmaterializationtagmanifest) | [`buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-rc-materialization-tag`. |
| [CreateReleaseBranchManifest](#createreleasebranchmanifest) | [`buildish-release-tooling-create-release-branch-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-release-branch-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-release-branch`. |
| [CreateSourceArtifactManifest](#createsourceartifactmanifest) | [`buildish-release-tooling-create-source-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-source-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-source-artifact`. |
| [FinalizeDraftGithubReleaseManifest](#finalizedraftgithubreleasemanifest) | [`buildish-release-tooling-finalize-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-draft-github-release`. |
| [FinalizeRcVoteMaterialsManifest](#finalizercvotematerialsmanifest) | [`buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-rc-vote-materials`. |
| [MaterializeRcGitContentManifest](#materializercgitcontentmanifest) | [`buildish-release-tooling-materialize-rc-git-content-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-materialize-rc-git-content-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `materialize-rc-git-content`. |
| [PrepareRcManifest](#preparercmanifest) | [`buildish-release-tooling-prepare-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prepare-rc`. |
| [PruneOlderLineReleasesManifest](#pruneolderlinereleasesmanifest) | [`buildish-release-tooling-prune-older-line-releases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prune-older-line-releases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prune-older-line-releases`. |
| [PublishAtrCandidateManifest](#publishatrcandidatemanifest) | [`buildish-release-tooling-publish-atr-candidate-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-atr-candidate-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-atr-candidate`. |
| [PublishDockerhubMovingTagsManifest](#publishdockerhubmovingtagsmanifest) | [`buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-dockerhub-moving-tags`. |
| [PublishSourceReleaseSvnManifest](#publishsourcereleasesvnmanifest) | [`buildish-release-tooling-publish-source-release-svn-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-source-release-svn-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-source-release-svn`. |
| [RecordArtifactManifest](#recordartifactmanifest) | [`buildish-release-tooling-record-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-record-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `record-artifact`. |
| [ReleaseVersionManifest](#releaseversionmanifest) | [`buildish-release-tooling-release-version-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `release-version`. |
| [ReportAtrChecksManifest](#reportatrchecksmanifest) | [`buildish-release-tooling-report-atr-checks-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-report-atr-checks-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `report-atr-checks`. |
| [SyncDraftGithubReleaseManifest](#syncdraftgithubreleasemanifest) | [`buildish-release-tooling-sync-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-sync-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `sync-draft-github-release`. |
| [UpdateMovingImageAliasesManifest](#updatemovingimagealiasesmanifest) | [`buildish-release-tooling-update-moving-image-aliases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-image-aliases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-image-aliases`. |
| [UpdateMovingTagsManifest](#updatemovingtagsmanifest) | [`buildish-release-tooling-update-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-tags`. |

## Shared aliases and literal sets

| Type | Base type | Description |
| --- | --- | --- |
| <a id="nonemptystring"></a>`NonEmptyString` | `String` | Trimmed string value with a minimum length of one character. |
| <a id="schemaversionv1"></a>`SchemaVersionV1` | `Literal set` | Current schema-version marker for Buildish v1 wire contracts. |
| <a id="verificationverdict"></a>`VerificationVerdict` | `Literal set` | Verification outcome literal, currently `verified` or `failed`. |
| <a id="artifactkind"></a>`ArtifactKind` | `Literal set` | Supported signed secondary-artifact kind names. |
| <a id="secondaryverificationkind"></a>`SecondaryVerificationKind` | `Literal set` | Verification report kind names, including the synthetic invalid-entry sentinel. |
| <a id="sha256hex"></a>`Sha256Hex` | `String` | Lowercase 64-character hexadecimal SHA-256 digest. |
| <a id="sha512hex"></a>`Sha512Hex` | `String` | Lowercase 128-character hexadecimal SHA-512 digest. |
| <a id="gitcommitsha"></a>`GitCommitSha` | `String` | Lowercase 40-character hexadecimal Git commit SHA. |
| <a id="ocicontentdigest"></a>`OciContentDigest` | `String` | Normalized OCI content digest in `algorithm:<hex>` form. |
| <a id="selfrepositorycheckoutmode"></a>`SelfRepositoryCheckoutMode` | `Literal set` | Harness self-repository checkout policy for the workflow repository under test. |
| <a id="repositoryoverridecheckoutmode"></a>`RepositoryOverrideCheckoutMode` | `Literal set` | Harness checkout policy for an explicit repository override binding. |
| <a id="harnessbackendname"></a>`HarnessBackendName` | `Literal set` | Supported harness execution backend names. |
| <a id="gpgfixturemode"></a>`GpgFixtureMode` | `Literal set` | Harness GPG fixture modes used by workflow scenarios. |
| <a id="harnessjobstatus"></a>`HarnessJobStatus` | `Literal set` | Harness job-result status values retained in machine-readable run results. |
| <a id="svninitialstate"></a>`SvnInitialState` | `Literal set` | Named harness SVN fixture presets for simulated ASF dist state. |


## Type index

### Release configuration and authored override types

Consumer-owned and component-owned authored configuration models, including `release-config.yaml` and local verify-rc override payloads.

- [AtrConfig](#atrconfig) — Validated optional ATR integration policy and release coordinates.
- [CommandContext](#commandcontext) — Common runtime context passed into command handlers.
- [ComponentConfig](#componentconfig) — Validated component policy and release-target configuration.
- [PrepareRcState](#preparercstate) — Resolved source and artifact state for an RC workflow run.
- [ReleaseVersionState](#releaseversionstate) — Resolved final-release state for a release workflow run.
- [VerifyRcBuildConfig](#verifyrcbuildconfig) — Host-direct rebuild recipe configuration for one reproducibility profile.
- [VerifyRcBuildOverrideConfig](#verifyrcbuildoverrideconfig) — Local non-canonical rebuild overrides for one reproducibility profile.
- [VerifyRcConfig](#verifyrcconfig) — Structured verify-rc configuration for rebuild recipes and profile selection.
- [VerifyRcExactBytesComparisonConfig](#verifyrcexactbytescomparisonconfig) — Exact-byte comparison policy for source and file-like reproducibility profiles.
- [VerifyRcMavenPathRuleConfig](#verifyrcmavenpathruleconfig) — One regex-based per-path comparison override inside a Maven repository profile.
- [VerifyRcMavenRepositoryComparisonConfig](#verifyrcmavenrepositorycomparisonconfig) — Repository-tree comparison policy for Maven repository reproducibility profiles.
- [VerifyRcOciImageComparisonConfig](#verifyrcociimagecomparisonconfig) — Digest-based OCI image comparison policy for image reproducibility profiles.
- [VerifyRcOverrideConfig](#verifyrcoverrideconfig) — Top-level local reproducibility override mapping keyed by profile_id.
- [VerifyRcOverrideFileConfig](#verifyrcoverridefileconfig) — Validated local override file for non-canonical reproducibility runs.
- [VerifyRcProfileConfig](#verifyrcprofileconfig) — One canonical reproducibility profile selected by signed manifest metadata.
- [VerifyRcProfileOverrideConfig](#verifyrcprofileoverrideconfig) — Local non-canonical override for one canonical reproducibility profile.
- [VerifyRcSelectionConfig](#verifyrcselectionconfig) — One canonical reproducibility profile selection.
- [VerifyRcSourceConfig](#verifyrcsourceconfig) — Source-artifact verification policy for verify-rc.

### Release manifests, inventories, and verification report types

Typed Buildish release manifests, emitted verification reports, inspection-bundle payloads, and related helper contracts.

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

### Internal unstable command action manifest types

Machine-readable command action manifests written for workflow coordination. These are Buildish-owned internal input/output contracts and are intentionally unstable.

- [AttachGithubReleaseAssetsManifest](#attachgithubreleaseassetsmanifest) — Action manifest emitted after uploading primary and derived assets to a GitHub release.
- [BuildSourceRcManifest](#buildsourcercmanifest) — Action manifest emitted after building and staging the signed source RC bundle.
- [CleanupDevSvnRcsManifest](#cleanupdevsvnrcsmanifest) — Action manifest emitted after old or conflicting RC staging directories are removed.
- [CommandActionManifest](#commandactionmanifest) — Common top-level shape for command action manifests.
- [CreateFinalTagManifest](#createfinaltagmanifest) — Action manifest emitted after creating or validating the final immutable release tag.
- [CreateRcMaterializationTagManifest](#creatercmaterializationtagmanifest) — Action manifest emitted after tagging one detached RC materialization commit.
- [CreateReleaseBranchManifest](#createreleasebranchmanifest) — Action manifest emitted after resolving or creating a release branch.
- [CreateSourceArtifactManifest](#createsourceartifactmanifest) — Action manifest emitted after creating one local source release artifact.
- [FinalizeDraftGithubReleaseManifest](#finalizedraftgithubreleasemanifest) — Action manifest emitted after finalizing a selected GitHub draft release.
- [FinalizeRcVoteMaterialsManifest](#finalizercvotematerialsmanifest) — Action manifest emitted after publishing and signing final RC vote materials.
- [MaterializeRcGitContentManifest](#materializercgitcontentmanifest) — Action manifest emitted after building detached RC materialization Git content.
- [PrepareRcManifest](#preparercmanifest) — Action manifest emitted after prepare-rc resolves one RC workflow state bundle.
- [PruneOlderLineReleasesManifest](#pruneolderlinereleasesmanifest) — Action manifest emitted after pruning older same-line releases from dist/release.
- [PublishAtrCandidateManifest](#publishatrcandidatemanifest) — Action manifest emitted after publishing one release candidate to ATR.
- [PublishDockerhubMovingTagsManifest](#publishdockerhubmovingtagsmanifest) — Action manifest emitted after publishing moving Docker Hub image aliases.
- [PublishSourceReleaseSvnManifest](#publishsourcereleasesvnmanifest) — Action manifest emitted after promoting a verified source artifact into dist/release.
- [RecordArtifactManifest](#recordartifactmanifest) — Action manifest emitted after writing one typed secondary-artifact bundle.
- [ReleaseVersionManifest](#releaseversionmanifest) — Action manifest emitted after a full release-version orchestration run completes.
- [ReportAtrChecksManifest](#reportatrchecksmanifest) — Action manifest emitted after summarizing ATR checks for one candidate revision.
- [SyncDraftGithubReleaseManifest](#syncdraftgithubreleasemanifest) — Action manifest emitted after synchronizing the draft GitHub release with staged RC artifacts.
- [UpdateMovingImageAliasesManifest](#updatemovingimagealiasesmanifest) — Action manifest emitted after resolving moving OCI image aliases for publication.
- [UpdateMovingTagsManifest](#updatemovingtagsmanifest) — Action manifest emitted after updating moving Git tags for a final release.

### Harness configuration types

Committed and resolved release-harness configuration models.

- [ReleaseHarnessConfig](#releaseharnessconfig) — Committed `release-harness.yaml` plus optional local overrides.
- [RepositoryOverrideConfig](#repositoryoverrideconfig) — Committed harness settings for one explicit repository override.
- [ResolvedReleaseHarnessConfigJson](#resolvedreleaseharnessconfigjson) — Machine-readable JSON payload for one resolved harness config file.
- [ResolvedRepositoryBindingJson](#resolvedrepositorybindingjson) — Machine-readable JSON payload for one resolved harness repository binding.
- [SelfRepositoryConfig](#selfrepositoryconfig) — Committed harness settings for the workflow repository under test.

### Harness scenario and runtime result types

Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results.

- [FileWriteAction](#filewriteaction) — A file write that a mocked tool invocation should perform.
- [GitRepositoryFixture](#gitrepositoryfixture) — A disposable Git repository that should be initialized inside the workspace.
- [HarnessBuiltinGhTagObject](#harnessbuiltinghtagobject) — Synthetic GitHub tag-object payload retained by the harness shim.
- [HarnessCommandTraceEntry](#harnesscommandtraceentry) — One persisted command-trace entry recorded by harness tool shims.
- [HarnessInspectablePaths](#harnessinspectablepaths) — Stable inspectable workspace paths exposed by the harness CLI.
- [HarnessRunResultJson](#harnessrunresultjson) — Machine-readable JSON payload for one harness run or rerun.
- [HarnessScenario](#harnessscenario) — A runner-agnostic integration-test scenario.
- [HarnessSequenceEntryJson](#harnesssequenceentryjson) — One sequence-run entry returned by the harness CLI.
- [HarnessSequenceRunResultJson](#harnesssequencerunresultjson) — Machine-readable JSON payload for one harness sequence run.
- [HarnessShimState](#harnessshimstate) — Persisted subprocess-facing harness shim state.
- [InvocationMatch](#invocationmatch) — A matcher for a single intercepted tool invocation.
- [JobScenario](#jobscenario) — A job in the harness scenario.
- [StepScenario](#stepscenario) — A single shell step in a harness job.
- [SvnRepositoryFixture](#svnrepositoryfixture) — Initial ASF SVN state to create inside one harness `act` workspace.
- [ToolBehavior](#toolbehavior) — A scripted behavior for an intercepted tool invocation.
- [ToolBehaviorResult](#toolbehaviorresult) — The mocked result of an intercepted tool invocation.
- [WorkflowRepositoryBranchFixture](#workflowrepositorybranchfixture) — A branch that should exist in the workflow repository checkout before execution.
- [WorkflowRepositoryFixture](#workflowrepositoryfixture) — Git refs that should be created in the workflow repository checkout before execution.
- [WorkflowRepositoryTagFixture](#workflowrepositorytagfixture) — A tag that should exist in the workflow repository checkout before execution.
- [WorkflowScenario](#workflowscenario) — A real workflow-YAML invocation executed by the `act` backend.
- [WorkspaceFile](#workspacefile) — A file that should exist in the scenario workspace before job execution starts.

### Harness shim builtin payload types

Small runtime payloads used by the harness shim to emulate GitHub and other tools.

- [HarnessBuiltinGhRefMutationPayload](#harnessbuiltinghrefmutationpayload) — Synthetic GitHub tag-ref mutation payload consumed by the harness shim.

## Release configuration and authored override types

Consumer-owned and component-owned authored configuration models, including `release-config.yaml` and local verify-rc override payloads.

<a id="atrconfig"></a>
### AtrConfig

Validated optional ATR integration policy and release coordinates.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="atrconfig-enabled"></a>`enabled` | bool | no | Whether the related optional integration or policy block is enabled for this component. |
| <a id="atrconfig-base-url"></a>`base_url` | str | no | Base URL used to discover or publish the related artifact or service resource. |
| <a id="atrconfig-committee"></a>`committee` | str | no | ASF committee slug that owns the component or ATR publication target. |
| <a id="atrconfig-product-line"></a>`product_line` | str | no | ATR product-line identifier used for the related candidate publication. |
| <a id="atrconfig-source-artifact-paths"></a>`source_artifact_paths` | list[str] | no | Path globs that select staged source artifacts for the related ATR publication or verification policy. |
| <a id="atrconfig-binary-artifact-paths"></a>`binary_artifact_paths` | list[str] | no | Path globs that select staged binary artifacts for ATR publication. |
| <a id="atrconfig-strict-checking"></a>`strict_checking` | bool | no | Whether the related check or reporting step should fail the command when warnings or failures are present. |
| <a id="atrconfig-license-check-mode"></a>`license_check_mode` | str | no | ATR license-check flavor that Buildish should request or report for the related publication run. |

<a id="commandcontext"></a>
### CommandContext

Common runtime context passed into command handlers.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-command-context.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-context.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="commandcontext-component-config"></a>`component_config` | [ComponentConfig](#componentconfig) | yes | Validated component configuration resolved for the current Buildish command run. |
| <a id="commandcontext-component-config-path"></a>`component_config_path` | Path | no | Filesystem path of the component configuration file used for the current Buildish command run. |

<a id="componentconfig"></a>
### ComponentConfig

Validated component policy and release-target configuration.

- category: `authored`
- ownership: `component-owned`
- schema file: [`buildish-release-tooling-component-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-component-config.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: `release-config.yaml`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="componentconfig-component-id"></a>`component_id` | str | yes | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="componentconfig-source-artifact-prefix"></a>`source_artifact_prefix` | str | yes | Configured top-level directory prefix that the component's source archive should unpack to. |
| <a id="componentconfig-asf-dist-dev-base"></a>`asf_dist_dev_base` | str | yes | Configured ASF `dist/dev` base URL under which RC materials are staged for this component. |
| <a id="componentconfig-asf-dist-release-base"></a>`asf_dist_release_base` | str | yes | Configured ASF `dist/release` base URL under which final source releases are published for this component. |
| <a id="componentconfig-asf-keys-url"></a>`asf_keys_url` | str | yes | Configured ASF KEYS URL that this component treats as authoritative for RC signature verification. |
| <a id="componentconfig-moving-tags-enabled"></a>`moving_tags_enabled` | bool | yes | Whether this component maintains moving release-line tags that are updated during final release publication. |
| <a id="componentconfig-latest-tag-enabled"></a>`latest_tag_enabled` | bool | yes | Whether this component publishes a moving `latest` tag in addition to line-specific moving tags. |
| <a id="componentconfig-secondary-targets"></a>`secondary_targets` | list[str] | yes | Configured secondary target families that the component publishes in addition to the source artifact. |
| <a id="componentconfig-final-tag-mode"></a>`final_tag_mode` | str | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |
| <a id="componentconfig-vote-release-name"></a>`vote_release_name` | str | yes | Human-facing release name that Buildish should use in vote mails, release summaries, and other user-visible output. |
| <a id="componentconfig-incubator-vote-enabled"></a>`incubator_vote_enabled` | bool | no | Whether the component's vote materials should include Apache Incubator-specific voting language and process guidance. |
| <a id="componentconfig-release-summary-include-final-tag-mode"></a>`release_summary_include_final_tag_mode` | bool | no | Whether release summary output should explicitly include the configured final-tag mode. |
| <a id="componentconfig-release-verification-guide-url"></a>`release_verification_guide_url` | str | yes | User-facing guide URL that Buildish should include when pointing verifiers at the release verification instructions. |
| <a id="componentconfig-verify-rc-instructions"></a>`verify_rc_instructions` | str | yes | Human-facing verification instructions that Buildish should include for this component's RC vote materials. |
| <a id="componentconfig-prepare-rc-runs-tests"></a>`prepare_rc_runs_tests` | bool | no | Whether the component's canonical prepare-rc workflow is expected to run project test steps. |
| <a id="componentconfig-release-branch-ci-required"></a>`release_branch_ci_required` | bool | no | Whether this component requires a green release-branch CI signal before final publication can proceed. |
| <a id="componentconfig-atr"></a>`atr` | [AtrConfig](#atrconfig) | no | Nested ATR integration configuration for this component. |
| <a id="componentconfig-verify-rc"></a>`verify_rc` | [VerifyRcConfig](#verifyrcconfig) | no | Nested verify-rc configuration block for the component or local override file. |

<a id="preparercstate"></a>
### PrepareRcState

Resolved source and artifact state for an RC workflow run.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-prepare-rc-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-state.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="preparercstate-resolved-release-branch"></a>`resolved_release_branch` | str | yes | Release branch name that Buildish resolved for the selected version. |
| <a id="preparercstate-resolved-source-ref"></a>`resolved_source_ref` | str | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="preparercstate-source-date-epoch"></a>`source_date_epoch` | int | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="preparercstate-rc-number"></a>`rc_number` | int | yes | Numeric RC sequence selected for the related version. |
| <a id="preparercstate-rc-tag"></a>`rc_tag` | str | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="preparercstate-final-tag"></a>`final_tag` | str | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="preparercstate-source-artifact-name"></a>`source_artifact_name` | str | yes | Filename of the staged source release artifact. |
| <a id="preparercstate-source-artifact-root-name"></a>`source_artifact_root_name` | str | yes | Root directory name that the source release archive should unpack to. |
| <a id="preparercstate-source-artifact-prefix-path"></a>`source_artifact_prefix_path` | str | yes | Top-level path prefix inside the source release archive. |
| <a id="preparercstate-staging-url"></a>`staging_url` | str | yes | ASF dev/dist staging directory URL selected for the current RC. |

<a id="releaseversionstate"></a>
### ReleaseVersionState

Resolved final-release state for a release workflow run.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-release-version-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-state.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="releaseversionstate-selected-rc-tag"></a>`selected_rc_tag` | str | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="releaseversionstate-final-tag"></a>`final_tag` | str | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="releaseversionstate-archive-versions"></a>`archive_versions` | list[str] | yes | Older same-line release versions that Buildish resolved for archival pruning. |
| <a id="releaseversionstate-release-url"></a>`release_url` | str | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="releaseversionstate-moving-tags"></a>`moving_tags` | list[str] | yes | Derived moving tags or aliases that should point at the final released version. |

<a id="verifyrcbuildconfig"></a>
### VerifyRcBuildConfig

Host-direct rebuild recipe configuration for one reproducibility profile.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcbuildconfig-command"></a>`command` | list[str] | yes | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="verifyrcbuildconfig-working-dir"></a>`working_dir` | str | no | Repository-root-relative working directory that Buildish should use when running the related build recipe. |
| <a id="verifyrcbuildconfig-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="verifyrcbuildconfig-output-globs"></a>`output_globs` | list[str] | yes | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |

<a id="verifyrcbuildoverrideconfig"></a>
### VerifyRcBuildOverrideConfig

Local non-canonical rebuild overrides for one reproducibility profile.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcbuildoverrideconfig-command"></a>`command` | list[str] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="verifyrcbuildoverrideconfig-working-dir"></a>`working_dir` | str | no | Repository-root-relative working directory that Buildish should use when running the related build recipe. |
| <a id="verifyrcbuildoverrideconfig-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="verifyrcbuildoverrideconfig-output-globs"></a>`output_globs` | list[str] | no | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |

<a id="verifyrcconfig"></a>
### VerifyRcConfig

Structured verify-rc configuration for rebuild recipes and profile selection.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcconfig-source"></a>`source` | [VerifyRcSourceConfig](#verifyrcsourceconfig) | no | Source-artifact-specific verify-rc policy block nested inside the component configuration. |
| <a id="verifyrcconfig-profiles"></a>`profiles` | dict[str, [VerifyRcProfileConfig](#verifyrcprofileconfig)] | no | Canonical reproducibility profiles keyed by profile identifier in the component configuration. |

<a id="verifyrcexactbytescomparisonconfig"></a>
### VerifyRcExactBytesComparisonConfig

Exact-byte comparison policy for source and file-like reproducibility profiles.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcexactbytescomparisonconfig-mode"></a>`mode` | Literal['exact-bytes'] | no | Comparison mode literal indicating that reproducibility succeeds only when the rebuilt artifact bytes match the staged bytes exactly. |

<a id="verifyrcmavenpathruleconfig"></a>
### VerifyRcMavenPathRuleConfig

One regex-based per-path comparison override inside a Maven repository profile.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcmavenpathruleconfig-pattern"></a>`pattern` | str | yes | Regular-expression pattern used to match one family of repository paths. |
| <a id="verifyrcmavenpathruleconfig-mode"></a>`mode` | Literal['exact-bytes', 'zip-normalized', 'content-only', 'remote-only'] | yes | Comparison mode that should apply to Maven repository paths matching this regex rule instead of the repository default. |

<a id="verifyrcmavenrepositorycomparisonconfig"></a>
### VerifyRcMavenRepositoryComparisonConfig

Repository-tree comparison policy for Maven repository reproducibility profiles.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcmavenrepositorycomparisonconfig-mode"></a>`mode` | Literal['repository-tree'] | no | Comparison mode literal indicating that this reproducibility profile compares a rebuilt Maven repository tree against the staged repository tree. |
| <a id="verifyrcmavenrepositorycomparisonconfig-repository-dir"></a>`repository_dir` | str | yes | Repository-root-relative rebuild output directory that should contain the local Maven repository tree. |
| <a id="verifyrcmavenrepositorycomparisonconfig-require-signatures"></a>`require_signatures` | bool | no | Whether Maven repository reproducibility should require detached signature files to exist and compare successfully. |
| <a id="verifyrcmavenrepositorycomparisonconfig-path-rules"></a>`path_rules` | list[[VerifyRcMavenPathRuleConfig](#verifyrcmavenpathruleconfig)] | no | Regex-based per-path comparison rules that specialize the default Maven repository comparison behavior. |

<a id="verifyrcociimagecomparisonconfig"></a>
### VerifyRcOciImageComparisonConfig

Digest-based OCI image comparison policy for image reproducibility profiles.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcociimagecomparisonconfig-mode"></a>`mode` | Literal['platform-digest', 'provenance-only'] | yes | Digest-comparison strategy used for OCI image reproducibility, either requiring matching platform digests or only provenance-level agreement. |
| <a id="verifyrcociimagecomparisonconfig-image-ref"></a>`image_ref` | str | yes | Fully qualified OCI image reference used for inspection or local rebuild comparison. |

<a id="verifyrcoverrideconfig"></a>
### VerifyRcOverrideConfig

Top-level local reproducibility override mapping keyed by profile_id.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcoverrideconfig-profile-overrides"></a>`profile_overrides` | dict[str, [VerifyRcProfileOverrideConfig](#verifyrcprofileoverrideconfig)] | no | Local non-canonical reproducibility overrides keyed by canonical profile identifier. |

<a id="verifyrcoverridefileconfig"></a>
### VerifyRcOverrideFileConfig

Validated local override file for non-canonical reproducibility runs.

- category: `authored`
- ownership: `consumer-owned`
- schema file: [`buildish-release-tooling-verify-rc-override-file-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-override-file-config.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcoverridefileconfig-verify-rc"></a>`verify_rc` | [VerifyRcOverrideConfig](#verifyrcoverrideconfig) | yes | Nested verify-rc configuration block for the component or local override file. |

<a id="verifyrcprofileconfig"></a>
### VerifyRcProfileConfig

One canonical reproducibility profile selected by signed manifest metadata.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcprofileconfig-kind"></a>`kind` | Literal['source-artifact', 'generic-file', 'generic-file-with-openpgp', 'maven-repository', 'npm-package', 'oci-image', 'python-distribution'] | yes | Artifact-kind discriminator that selects which canonical reproducibility profile shape applies. |
| <a id="verifyrcprofileconfig-build"></a>`build` | [VerifyRcBuildConfig](#verifyrcbuildconfig) | yes | Nested build recipe or effective build execution block for one reproducibility contract. |
| <a id="verifyrcprofileconfig-comparison"></a>`comparison` | [VerifyRcExactBytesComparisonConfig](#verifyrcexactbytescomparisonconfig) \| [VerifyRcMavenRepositoryComparisonConfig](#verifyrcmavenrepositorycomparisonconfig) \| [VerifyRcOciImageComparisonConfig](#verifyrcociimagecomparisonconfig) | yes | Artifact-kind-specific reproducibility comparison policy for the canonical profile. |

<a id="verifyrcprofileoverrideconfig"></a>
### VerifyRcProfileOverrideConfig

Local non-canonical override for one canonical reproducibility profile.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcprofileoverrideconfig-build"></a>`build` | [VerifyRcBuildOverrideConfig](#verifyrcbuildoverrideconfig) | yes | Nested build recipe or effective build execution block for one reproducibility contract. |

<a id="verifyrcselectionconfig"></a>
### VerifyRcSelectionConfig

One canonical reproducibility profile selection.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcselectionconfig-profile-id"></a>`profile_id` | str | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="verifyrcselectionconfig-mode"></a>`mode` | str | no | Optional future-facing mode hint recorded next to the selected reproducibility profile. When present, it narrows how the selected profile should be interpreted for this source-artifact policy block. |

<a id="verifyrcsourceconfig"></a>
### VerifyRcSourceConfig

Source-artifact verification policy for verify-rc.

- category: `authored`
- ownership: `component-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcsourceconfig-reproducibility"></a>`reproducibility` | [VerifyRcSelectionConfig](#verifyrcselectionconfig) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |

## Release manifests, inventories, and verification report types

Typed Buildish release manifests, emitted verification reports, inspection-bundle payloads, and related helper contracts.

<a id="artifactreproducibilitybuildoverridereport"></a>
### ArtifactReproducibilityBuildOverrideReport

Sparse local override delta applied to one canonical build recipe.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilitybuildoverridereport-command"></a>`command` | list[[NonEmptyString](#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilitybuildoverridereport-working-directory"></a>`working_directory` | [NonEmptyString](#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilitybuildoverridereport-output-globs"></a>`output_globs` | list[[NonEmptyString](#nonemptystring)] | no | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |
| <a id="artifactreproducibilitybuildoverridereport-env-keys"></a>`env_keys` | list[[NonEmptyString](#nonemptystring)] | no | Environment variable names referenced by the related recipe or override without exposing their values. |

<a id="artifactreproducibilitycanonicalbuildrecipereport"></a>
### ArtifactReproducibilityCanonicalBuildRecipeReport

Canonical build recipe declared by the verified source tree for one profile.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-command"></a>`command` | list[[NonEmptyString](#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-working-directory"></a>`working_directory` | [NonEmptyString](#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-output-globs"></a>`output_globs` | list[[NonEmptyString](#nonemptystring)] | no | Repository-root-relative glob patterns that identify expected outputs of the related build recipe. |
| <a id="artifactreproducibilitycanonicalbuildrecipereport-env-keys"></a>`env_keys` | list[[NonEmptyString](#nonemptystring)] | no | Environment variable names referenced by the related recipe or override without exposing their values. |

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
| <a id="artifactreproducibilityeffectivebuildexecutionreport-command"></a>`command` | list[[NonEmptyString](#nonemptystring)] | no | Literal argv list that Buildish executed or recommends for the related step. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-working-directory"></a>`working_directory` | [NonEmptyString](#nonemptystring) | no | Repository-root-relative working directory that Buildish recorded in the related canonical recipe, effective execution, or local override block. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-output-paths"></a>`output_paths` | list[[NonEmptyString](#nonemptystring)] | no | Concrete output paths that Buildish observed from the effective rebuild execution. |
| <a id="artifactreproducibilityeffectivebuildexecutionreport-injected-environment-keys"></a>`injected_environment_keys` | list[[NonEmptyString](#nonemptystring)] | no | Environment variable names that Buildish injected into the effective rebuild subprocess. |

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
| <a id="artifactreproducibilityreport-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="artifactreproducibilityreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="artifactreproducibilityreport-comparison-mode"></a>`comparison_mode` | [NonEmptyString](#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="artifactreproducibilityreport-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="artifactreproducibilityreport-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="artifactreproducibilityreport-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="artifactreproducibilityreport-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="artifactreproducibilityreport-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
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
| <a id="asfkeystrustroot-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="asfkeystrustroot-known-length-bytes"></a>`known_length_bytes` | int | yes | Expected byte length of the pinned ASF KEYS file when Buildish establishes the trust root. |
| <a id="asfkeystrustroot-known-prefix-sha512"></a>`known_prefix_sha512` | [Sha512Hex](#sha512hex) | yes | Pinned SHA-512 digest prefix that Buildish expects the ASF KEYS file to start with. |

<a id="asfkeystrustrootread"></a>
### AsfKeysTrustRootRead

Tolerant ASF KEYS trust-root subset accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-asf-keys-trust-root-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-asf-keys-trust-root-read.schema.json)
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
| <a id="authoritativemanifestreference-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="authoritativemanifestreference-checksum-uris"></a>`checksum_uris` | dict[Literal['sha512'], [NonEmptyString](#nonemptystring)] | yes | Manifest-relative or absolute URIs of checksum sidecars associated with the authoritative staged manifest. |
| <a id="authoritativemanifestreference-signatures"></a>`signatures` | list[[SignatureReference](#signaturereference)] | yes | Declared detached signature references associated with the related artifact or manifest. |

<a id="authoritativemanifestreferenceread"></a>
### AuthoritativeManifestReferenceRead

Tolerant authoritative-manifest reference accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-authoritative-manifest-reference-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-authoritative-manifest-reference-read.schema.json)
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
| <a id="draftgithubrelease-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="draftgithubrelease-tag"></a>`tag` | [NonEmptyString](#nonemptystring) | yes | Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload. |
| <a id="draftgithubrelease-url"></a>`url` | [NonEmptyString](#nonemptystring) | yes | Canonical browser or download URL associated with the related record. |

<a id="draftgithubreleaseread"></a>
### DraftGithubReleaseRead

Tolerant draft-release pointer accepted by verify-rc readers.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-draft-github-release-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-draft-github-release-read.schema.json)
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
- schema file: [`buildish-release-tooling-file-like-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-file-like-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="filelikereproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="filelikereproducibilitymetadata-kind"></a>`kind` | Literal['generic-file', 'generic-file-with-openpgp', 'python-distribution', 'npm-package'] | yes | Declared artifact or report kind discriminator. |
| <a id="filelikereproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="filelikereproducibilitymetadata-comparison-mode"></a>`comparison_mode` | [NonEmptyString](#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="filelikereproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="filelikereproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="filelikereproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="filelikereproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
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
| <a id="genericfilesecondaryartifact-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfilesecondaryartifact-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
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
| <a id="genericfileverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="genericfileverificationreport-kind"></a>`kind` | Literal['generic-file', 'generic-file-with-openpgp'] | yes | Declared artifact or report kind discriminator. |
| <a id="genericfileverificationreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="genericfileverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="genericfileverificationreport-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfileverificationreport-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
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
| <a id="genericfilewithopenpgpsecondaryartifact-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="genericfilewithopenpgpsecondaryartifact-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
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
| <a id="githubworkflowprovenance-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="githubworkflowprovenance-workflow"></a>`workflow` | str | yes | Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance. |
| <a id="githubworkflowprovenance-workflow-ref"></a>`workflow_ref` | str | yes | GitHub Actions workflow ref associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-id"></a>`run_id` | int | yes | GitHub Actions run id associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-attempt"></a>`run_attempt` | int | no | GitHub Actions run attempt number associated with the related provenance record. |
| <a id="githubworkflowprovenance-run-url"></a>`run_url` | [NonEmptyString](#nonemptystring) | no | Browser URL of the related GitHub Actions workflow run. |

<a id="inspectreprocountsummary"></a>
### InspectReproCountSummary

One count bucket emitted by inspect-repro machine-readable summaries.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreprocountsummary-key"></a>`key` | [NonEmptyString](#nonemptystring) | yes | Stable grouping or category key used in one Buildish summary object. |
| <a id="inspectreprocountsummary-count"></a>`count` | int | yes | Count value reported for one grouped summary bucket. |

<a id="inspectreproreportv1"></a>
### InspectReproReportV1

Machine-readable inspect-repro output for automation and post-processing.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-inspect-repro-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspect-repro-report-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectreproreportv1-schema-version"></a>`schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="inspectreproreportv1-report-type"></a>`report_type` | Literal['inspect-repro'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="inspectreproreportv1-verify-rc-report-schema-version"></a>`verify_rc_report_schema_version` | [SchemaVersionV1](#schemaversionv1) | yes | Schema version of the verify-rc JSON report that inspect-repro read before generating its own output. |
| <a id="inspectreproreportv1-bundle-schema-version"></a>`bundle_schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed. |
| <a id="inspectreproreportv1-component-id"></a>`component_id` | str | no | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="inspectreproreportv1-rc-tag"></a>`rc_tag` | str | no | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="inspectreproreportv1-verify-rc-verdict"></a>`verify_rc_verdict` | [VerificationVerdict](#verificationverdict) | yes | Final verify-rc verdict that inspect-repro observed in the input verification report. |
| <a id="inspectreproreportv1-build-checks-attempted"></a>`build_checks_attempted` | bool | yes | Whether the command attempted local reproducibility or rebuild checks during this run. |
| <a id="inspectreproreportv1-report-json-path"></a>`report_json_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the verify-rc JSON report consumed by inspect-repro. |
| <a id="inspectreproreportv1-inspection-bundle-path"></a>`inspection_bundle_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the retained inspection bundle directory. |
| <a id="inspectreproreportv1-selected-artifact-ids"></a>`selected_artifact_ids` | list[[NonEmptyString](#nonemptystring)] | no | Artifact ids that inspect-repro selected for detailed output. |
| <a id="inspectreproreportv1-selected-failure-classes"></a>`selected_failure_classes` | list[[NonEmptyString](#nonemptystring)] | no | Failure-class filters that inspect-repro applied when selecting targets. |
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
| <a id="inspectreprotargetv1-section-label"></a>`section_label` | [NonEmptyString](#nonemptystring) | yes | Human-facing section label that groups related inspect-repro targets. |
| <a id="inspectreprotargetv1-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="inspectreprotargetv1-kind"></a>`kind` | [NonEmptyString](#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="inspectreprotargetv1-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
| <a id="inspectreprotargetv1-failure-group"></a>`failure_group` | [NonEmptyString](#nonemptystring) | yes | Higher-level grouping bucket that inspect-repro assigned to the target, such as source-artifact or secondary artifact family. |
| <a id="inspectreprotargetv1-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="inspectreprotargetv1-comparison-mode"></a>`comparison_mode` | [NonEmptyString](#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="inspectreprotargetv1-recipe-source"></a>`recipe_source` | Literal['verifier-internal', 'canonical-profile', 'local-override'] | yes | Origin of the reproducibility recipe used for this target, such as verifier-internal logic, the canonical profile, or a local override. |
| <a id="inspectreprotargetv1-execution-backend"></a>`execution_backend` | [NonEmptyString](#nonemptystring) | no | Execution backend that verify-rc used for the recorded reproducibility run. |
| <a id="inspectreprotargetv1-build-command"></a>`build_command` | list[[NonEmptyString](#nonemptystring)] | no | Literal argv list that inspect-repro or verify-rc recorded as the effective build command for this target. |
| <a id="inspectreprotargetv1-build-working-directory"></a>`build_working_directory` | [NonEmptyString](#nonemptystring) | no | Repository-root-relative working directory that inspect-repro or verify-rc recorded for the effective build command. |
| <a id="inspectreprotargetv1-injected-environment-keys"></a>`injected_environment_keys` | list[[NonEmptyString](#nonemptystring)] | no | Environment variable names that Buildish injected into the effective rebuild subprocess. |
| <a id="inspectreprotargetv1-evidence-labels"></a>`evidence_labels` | list[[NonEmptyString](#nonemptystring)] | no | Short labels naming the retained evidence files that inspect-repro associated with this target. |
| <a id="inspectreprotargetv1-evidence"></a>`evidence` | list[[InspectionEvidenceReference](#inspectionevidencereference)] | no | Inspection-bundle evidence references retained for one reproducibility result. |
| <a id="inspectreprotargetv1-override-fields"></a>`override_fields` | list[[NonEmptyString](#nonemptystring)] | no | Sparse list of build-recipe fields that a local reproducibility override changed for this target. |

<a id="inspectionbundleartifactentry"></a>
### InspectionBundleArtifactEntry

One artifact-specific metadata document retained inside an inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionbundleartifactentry-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="inspectionbundleartifactentry-kind"></a>`kind` | [NonEmptyString](#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="inspectionbundleartifactentry-metadata-path"></a>`metadata_path` | [NonEmptyString](#nonemptystring) | yes | Bundle-relative path to the metadata file for one retained inspection target. |

<a id="inspectionbundlemanifestv1"></a>
### InspectionBundleManifestV1

Top-level contract manifest for one curated verify-rc inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-inspection-bundle-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspection-bundle-manifest-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: `inspection-bundle.json`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionbundlemanifestv1-schema-version"></a>`schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="inspectionbundlemanifestv1-bundle-type"></a>`bundle_type` | Literal['verify-rc-inspection'] | no | Stable inspection-bundle manifest discriminator. |
| <a id="inspectionbundlemanifestv1-report-type"></a>`report_type` | Literal['verify-rc'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="inspectionbundlemanifestv1-report-schema-version"></a>`report_schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Supported schema version of the related Buildish report payload. |
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
| <a id="inspectionbundlesection-relative-path-from-report"></a>`relative_path_from_report` | [NonEmptyString](#nonemptystring) | yes | Path from the verify-rc report directory to the retained inspection bundle directory. |
| <a id="inspectionbundlesection-bundle-schema-version"></a>`bundle_schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Supported schema version of the retained inspection-bundle manifest that inspect-repro consumed. |
| <a id="inspectionbundlesection-manifest-relative-path"></a>`manifest_relative_path` | [NonEmptyString](#nonemptystring) | no | Bundle-relative path to the top-level inspection bundle manifest file. |

<a id="inspectionevidencereference"></a>
### InspectionEvidenceReference

One retained evidence file inside the verify-rc inspection bundle.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="inspectionevidencereference-label"></a>`label` | [NonEmptyString](#nonemptystring) | yes | Human-readable label used to name one evidence file or report section. |
| <a id="inspectionevidencereference-path"></a>`path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |

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
| <a id="invalidsecondaryartifactverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
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
| <a id="inventoryverificationreport-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="inventoryverificationreport-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="inventoryverificationreport-sha512"></a>`sha512` | [Sha512Hex](#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
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
| <a id="liverepositorysignatureverification-path"></a>`path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="liverepositorysignatureverification-target-path"></a>`target_path` | [NonEmptyString](#nonemptystring) | yes | Target path that the related detached signature or copy operation refers to. |
| <a id="liverepositorysignatureverification-signature"></a>`signature` | [SignatureVerificationPayload](#signatureverificationpayload) | yes | Signature verification details for the related artifact or manifest. |

<a id="manifestprovenance"></a>
### ManifestProvenance

Top-level provenance block for the RC vote manifest.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifestprovenance-created-at"></a>`created_at` | [NonEmptyString](#nonemptystring) | yes | Timestamp when Buildish created the enclosing manifest or provenance record. |
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
| <a id="manifestverificationmetadatastrict-staging-svn-url"></a>`staging_svn_url` | [NonEmptyString](#nonemptystring) | yes | ASF SVN staging directory URL associated with the authoritative RC materials. |
| <a id="manifestverificationmetadatastrict-authoritative-manifest"></a>`authoritative_manifest` | [AuthoritativeManifestReference](#authoritativemanifestreference) | yes | Canonical authoritative RC vote-manifest reference or verification block associated with the enclosing payload. |

<a id="manifestverificationsection"></a>
### ManifestVerificationSection

Manifest-authenticity and tag-binding section of the verify-rc report.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="manifestverificationsection-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
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
| <a id="mavenrepositoryinventoryentry-path"></a>`path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="mavenrepositoryinventoryentry-size-bytes"></a>`size_bytes` | int | yes | Byte size recorded for the related artifact, retained snapshot, or inventory entry. |
| <a id="mavenrepositoryinventoryentry-sha512"></a>`sha512` | [Sha512Hex](#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |

<a id="mavenrepositoryinventoryv1"></a>
### MavenRepositoryInventoryV1

A signed Maven repository inventory attachment.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-maven-repository-inventory-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-inventory-v1.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryinventoryv1-schema-version"></a>`schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="mavenrepositoryinventoryv1-inventory-type"></a>`inventory_type` | Literal['maven-repository'] | no | Stable manifest discriminator for the signed Maven repository inventory file. |
| <a id="mavenrepositoryinventoryv1-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryinventoryv1-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositoryinventoryv1-base-url"></a>`base_url` | [NonEmptyString](#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |
| <a id="mavenrepositoryinventoryv1-entries"></a>`entries` | list[[MavenRepositoryInventoryEntry](#mavenrepositoryinventoryentry)] | yes | Typed entries recorded in the related manifest, inventory, or report payload. |

<a id="mavenrepositorypathresultreport"></a>
### MavenRepositoryPathResultReport

One comparable staged Maven repository path result retained for inspection.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-maven-repository-path-result-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-result-report.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositorypathresultreport-path"></a>`path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="mavenrepositorypathresultreport-mode"></a>`mode` | MavenRepositoryPathMode | yes | Comparison mode that Buildish applied when comparing this staged Maven repository path to the rebuilt local path. |
| <a id="mavenrepositorypathresultreport-verdict"></a>`verdict` | MavenRepositoryPathVerdict | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="mavenrepositorypathresultreport-detail"></a>`detail` | [NonEmptyString](#nonemptystring) | yes | Human-readable comparison detail for one verification or reproducibility result entry. |
| <a id="mavenrepositorypathresultreport-raw-bytes-equal"></a>`raw_bytes_equal` | bool | no | Whether raw staged and rebuilt bytes matched before any archive-aware normalization. |
| <a id="mavenrepositorypathresultreport-normalized-match"></a>`normalized_match` | bool | no | Whether the staged and rebuilt repository path matched after applying the selected normalization mode. |
| <a id="mavenrepositorypathresultreport-staged-sha512"></a>`staged_sha512` | [Sha512Hex](#sha512hex) | no | SHA-512 digest computed from the staged repository entry or retained artifact bytes. |
| <a id="mavenrepositorypathresultreport-rebuilt-sha512"></a>`rebuilt_sha512` | [Sha512Hex](#sha512hex) | no | SHA-512 digest computed from the rebuilt source or secondary artifact bytes. |

<a id="mavenrepositorypathrulereport"></a>
### MavenRepositoryPathRuleReport

One regex-based Maven repository path rule retained for inspection.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-maven-repository-path-rule-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-rule-report.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositorypathrulereport-pattern"></a>`pattern` | [NonEmptyString](#nonemptystring) | yes | Regular-expression pattern used to match one family of repository paths. |
| <a id="mavenrepositorypathrulereport-mode"></a>`mode` | MavenRepositoryPathMode | yes | Comparison mode that the associated regex path rule applies to matching staged Maven repository paths. |

<a id="mavenrepositoryreproducibilitymetadata"></a>
### MavenRepositoryReproducibilityMetadata

Retained comparison metadata for one Maven repository reproducibility run.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryreproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryreproducibilitymetadata-kind"></a>`kind` | Literal['maven-repository'] | no | Declared artifact or report kind discriminator. |
| <a id="mavenrepositoryreproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="mavenrepositoryreproducibilitymetadata-comparison-mode"></a>`comparison_mode` | Literal['repository-tree'] | no | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="mavenrepositoryreproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="mavenrepositoryreproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="mavenrepositoryreproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="mavenrepositoryreproducibilitymetadata-repository-dir"></a>`repository_dir` | [NonEmptyString](#nonemptystring) | no | Repository-root-relative rebuild output directory that should contain the local Maven repository tree. |
| <a id="mavenrepositoryreproducibilitymetadata-require-signatures"></a>`require_signatures` | bool | no | Whether Maven repository reproducibility should require detached signature files to exist and compare successfully. |
| <a id="mavenrepositoryreproducibilitymetadata-path-rules"></a>`path_rules` | list[[MavenRepositoryPathRuleReport](#mavenrepositorypathrulereport)] | no | Regex-based per-path comparison rules that specialize the default Maven repository comparison behavior. |
| <a id="mavenrepositoryreproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="mavenrepositoryreproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
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
| <a id="mavenrepositorysecondaryartifact-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositorysecondaryartifact-base-url"></a>`base_url` | [NonEmptyString](#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |

<a id="mavenrepositoryverificationreport"></a>
### MavenRepositoryVerificationReport

Verification report for one staged Maven repository.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="mavenrepositoryverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="mavenrepositoryverificationreport-kind"></a>`kind` | Literal['maven-repository'] | no | Declared artifact or report kind discriminator. |
| <a id="mavenrepositoryverificationreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="mavenrepositoryverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="mavenrepositoryverificationreport-staging-repository-id"></a>`staging_repository_id` | [NonEmptyString](#nonemptystring) | yes | Repository identifier of the staged Maven repository under verification. |
| <a id="mavenrepositoryverificationreport-base-url"></a>`base_url` | [NonEmptyString](#nonemptystring) | yes | Base URL used to discover or publish the related artifact or service resource. |
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
| <a id="npmpackagesecondaryartifact-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="npmpackagesecondaryartifact-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="npmpackagesecondaryartifact-registry-url"></a>`registry_url` | [NonEmptyString](#nonemptystring) | yes | Registry metadata URL used for npm package verification. |
| <a id="npmpackagesecondaryartifact-package-name"></a>`package_name` | [NonEmptyString](#nonemptystring) | yes | Normalized npm package name associated with the related package artifact or registry lookup. |
| <a id="npmpackagesecondaryartifact-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="npmpackagesecondaryartifact-integrity"></a>`integrity` | [NonEmptyString](#nonemptystring) | yes | Integrity verification details derived from registry metadata or sidecar checksums. |
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
| <a id="npmpackageverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="npmpackageverificationreport-kind"></a>`kind` | Literal['npm-package'] | no | Declared artifact or report kind discriminator. |
| <a id="npmpackageverificationreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="npmpackageverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="npmpackageverificationreport-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="npmpackageverificationreport-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="npmpackageverificationreport-registry-url"></a>`registry_url` | [NonEmptyString](#nonemptystring) | yes | Registry metadata URL used for npm package verification. |
| <a id="npmpackageverificationreport-package-name"></a>`package_name` | [NonEmptyString](#nonemptystring) | yes | Normalized npm package name associated with the related package artifact or registry lookup. |
| <a id="npmpackageverificationreport-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
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
| <a id="npmprovenanceauth-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |

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
- schema file: [`buildish-release-tooling-oci-image-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-oci-image-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociimagereproducibilitymetadata-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="ociimagereproducibilitymetadata-kind"></a>`kind` | Literal['oci-image'] | no | Declared artifact or report kind discriminator. |
| <a id="ociimagereproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="ociimagereproducibilitymetadata-comparison-mode"></a>`comparison_mode` | Literal['platform-digest', 'provenance-only'] | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="ociimagereproducibilitymetadata-canonical-recipe"></a>`canonical_recipe` | [ArtifactReproducibilityCanonicalRecipeReport](#artifactreproducibilitycanonicalrecipereport) | no | Canonical rebuild recipe resolved from the verified source tree or other authoritative Buildish configuration. |
| <a id="ociimagereproducibilitymetadata-effective-execution"></a>`effective_execution` | [ArtifactReproducibilityEffectiveExecutionReport](#artifactreproducibilityeffectiveexecutionreport) | no | Effective build execution details that Buildish actually ran after applying local overrides or runtime defaults. |
| <a id="ociimagereproducibilitymetadata-override"></a>`override` | [ArtifactReproducibilityOverrideReport](#artifactreproducibilityoverridereport) | no | Explicit local reproducibility override details applied on top of the canonical recipe. |
| <a id="ociimagereproducibilitymetadata-image-ref"></a>`image_ref` | [NonEmptyString](#nonemptystring) | no | Fully qualified OCI image reference used for inspection or local rebuild comparison. |
| <a id="ociimagereproducibilitymetadata-declared-digest"></a>`declared_digest` | [OciContentDigest](#ocicontentdigest) | yes | Signed or declared digest that the rebuilt value is compared against. |
| <a id="ociimagereproducibilitymetadata-expected-platform-digests"></a>`expected_platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Platform-specific OCI digests that the reproducibility check expected to reproduce for the rebuilt image. |
| <a id="ociimagereproducibilitymetadata-rebuilt-digest"></a>`rebuilt_digest` | [OciContentDigest](#ocicontentdigest) | no | Digest produced by rebuilding the related OCI image locally. |
| <a id="ociimagereproducibilitymetadata-rebuilt-platform-digests"></a>`rebuilt_platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Platform digests produced by rebuilding the related multi-platform OCI image. |
| <a id="ociimagereproducibilitymetadata-matches-remote-bytes"></a>`matches_remote_bytes` | bool | no | Whether the rebuilt artifact bytes matched the staged or signed remote bytes exactly. |
| <a id="ociimagereproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
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
| <a id="ociimagesecondaryartifact-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="ociimagesecondaryartifact-registry"></a>`registry` | [NonEmptyString](#nonemptystring) | yes | Container registry host or namespace that serves the related OCI image. |
| <a id="ociimagesecondaryartifact-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="ociimagesecondaryartifact-digest"></a>`digest` | [OciContentDigest](#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |
| <a id="ociimagesecondaryartifact-platform-digests"></a>`platform_digests` | list[[OciPlatformDigest](#ociplatformdigest)] | no | Per-platform OCI digests declared or observed for a multi-platform image. |

<a id="ociimageverificationreport"></a>
### OciImageVerificationReport

Verification report for one OCI image.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="ociimageverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="ociimageverificationreport-kind"></a>`kind` | Literal['oci-image'] | no | Declared artifact or report kind discriminator. |
| <a id="ociimageverificationreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="ociimageverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="ociimageverificationreport-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="ociimageverificationreport-registry"></a>`registry` | [NonEmptyString](#nonemptystring) | yes | Container registry host or namespace that serves the related OCI image. |
| <a id="ociimageverificationreport-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="ociimageverificationreport-digest"></a>`digest` | [OciContentDigest](#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |
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
| <a id="ociinspectionreport-image-ref"></a>`image_ref` | [NonEmptyString](#nonemptystring) | yes | Fully qualified OCI image reference used for inspection or local rebuild comparison. |
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
| <a id="ociplatformdigest-platform"></a>`platform` | [NonEmptyString](#nonemptystring) | yes | OCI platform identifier in `os/arch[/variant]` form. |
| <a id="ociplatformdigest-digest"></a>`digest` | [OciContentDigest](#ocicontentdigest) | yes | OCI content digest or similar immutable digest string for the related artifact. |

<a id="pypiattestationauth"></a>
### PyPiAttestationAuth

Explicit PyPI attestation metadata.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pypiattestationauth-scheme"></a>`scheme` | Literal['pypi-attestation'] | no | Stable scheme identifier that names the authenticity or provenance mechanism represented by the related payload. |
| <a id="pypiattestationauth-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |

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
| <a id="pythondistributionsecondaryartifact-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="pythondistributionsecondaryartifact-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="pythondistributionsecondaryartifact-index-url"></a>`index_url` | [NonEmptyString](#nonemptystring) | yes | Base Python simple-index URL that Buildish used for package verification. |
| <a id="pythondistributionsecondaryartifact-project-name"></a>`project_name` | [NonEmptyString](#nonemptystring) | yes | Python package project name associated with the related distribution artifact. |
| <a id="pythondistributionsecondaryartifact-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
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
| <a id="pythondistributionverificationreport-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="pythondistributionverificationreport-kind"></a>`kind` | Literal['python-distribution'] | no | Declared artifact or report kind discriminator. |
| <a id="pythondistributionverificationreport-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="pythondistributionverificationreport-issues"></a>`issues` | list[str] | no | Collected human-readable issues observed for the related verification, inspection, or reproducibility subject. |
| <a id="pythondistributionverificationreport-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="pythondistributionverificationreport-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="pythondistributionverificationreport-index-url"></a>`index_url` | [NonEmptyString](#nonemptystring) | yes | Base Python simple-index URL that Buildish used for package verification. |
| <a id="pythondistributionverificationreport-project-name"></a>`project_name` | [NonEmptyString](#nonemptystring) | yes | Python package project name associated with the related distribution artifact. |
| <a id="pythondistributionverificationreport-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
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
| <a id="pythonindexresolutionreport-project-index-url"></a>`project_index_url` | [NonEmptyString](#nonemptystring) | yes | Resolved Python simple-index page URL that Buildish used to discover the expected distribution artifact. |
| <a id="pythonindexresolutionreport-resolved-url"></a>`resolved_url` | str | no | Resolved direct distribution or tarball URL that Buildish selected from the related package index. |
| <a id="pythonindexresolutionreport-found-via"></a>`found_via` | str | no | Short note describing how the related package URL or artifact metadata was discovered during verification. |
| <a id="pythonindexresolutionreport-sha256-matches-index"></a>`sha256_matches_index` | bool | no | Whether the distribution hash from the Python simple index matched the digest declared in the signed manifest. |

<a id="rcvotemanifestv1"></a>
### RcVoteManifestV1

Strict authoritative RC vote manifest emitted by buildish-release-tooling.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-rc-vote-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rc-vote-manifest-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: `rc-vote-manifest.json`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="rcvotemanifestv1-schema-version"></a>`schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="rcvotemanifestv1-manifest-type"></a>`manifest_type` | Literal['rc-vote'] | no | Stable manifest contract discriminator for one Buildish file format. |
| <a id="rcvotemanifestv1-component-id"></a>`component_id` | [NonEmptyString](#nonemptystring) | yes | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="rcvotemanifestv1-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="rcvotemanifestv1-release-line"></a>`release_line` | [NonEmptyString](#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="rcvotemanifestv1-release-branch"></a>`release_branch` | [NonEmptyString](#nonemptystring) | yes | Git branch name that Buildish resolved as the authoritative release branch. |
| <a id="rcvotemanifestv1-source-repository-url"></a>`source_repository_url` | [NonEmptyString](#nonemptystring) | yes | Canonical source repository URL recorded in the RC vote manifest or verification report. |
| <a id="rcvotemanifestv1-source-commit-sha"></a>`source_commit_sha` | [GitCommitSha](#gitcommitsha) | yes | Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report. |
| <a id="rcvotemanifestv1-source-date-epoch"></a>`source_date_epoch` | int | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="rcvotemanifestv1-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="rcvotemanifestv1-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="rcvotemanifestv1-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |
| <a id="rcvotemanifestv1-provenance"></a>`provenance` | [ManifestProvenance](#manifestprovenance) | yes | Tooling, workflow, or publication provenance block embedded in or read from the related Buildish contract. |
| <a id="rcvotemanifestv1-trust-roots"></a>`trust_roots` | [ManifestTrustRoots](#manifesttrustroots) | yes | Pinned trust-root material that verify-rc uses to establish authenticity for the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-draft-github-release"></a>`draft_github_release` | [DraftGithubRelease](#draftgithubrelease) | yes | Draft GitHub release metadata embedded in or read from the RC vote manifest. |
| <a id="rcvotemanifestv1-vote-materials"></a>`vote_materials` | [VoteMaterialsStrict](#votematerialsstrict) | yes | Vote-materials reference block embedded in or read from the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-verification"></a>`verification` | [ManifestVerificationMetadataStrict](#manifestverificationmetadatastrict) | yes | Verification metadata block nested inside the authoritative RC vote manifest. |
| <a id="rcvotemanifestv1-materialized-commit-sha"></a>`materialized_commit_sha` | [GitCommitSha](#gitcommitsha) | no | Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow. |

<a id="rebuiltoutputsnapshot"></a>
### RebuiltOutputSnapshot

One rebuilt output file described inside an inspection-bundle metadata document.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-rebuilt-output-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rebuilt-output-snapshot.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="rebuiltoutputsnapshot-path"></a>`path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="rebuiltoutputsnapshot-sha512"></a>`sha512` | [Sha512Hex](#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
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
| <a id="reproducibilityselector-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |

<a id="retainedartifactsnapshot"></a>
### RetainedArtifactSnapshot

One retained file snapshot described inside an inspection-bundle metadata document.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-retained-artifact-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-retained-artifact-snapshot.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="retainedartifactsnapshot-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="retainedartifactsnapshot-sha512"></a>`sha512` | [Sha512Hex](#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="retainedartifactsnapshot-size-bytes"></a>`size_bytes` | int | yes | Byte size recorded for the related artifact, retained snapshot, or inventory entry. |

<a id="secondaryartifactbase"></a>
### SecondaryArtifactBase

Common fields shared across supported secondary artifact kinds.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-secondary-artifact-base.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-base.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="secondaryartifactbase-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="secondaryartifactbase-kind"></a>`kind` | str | yes | Declared artifact or report kind discriminator. |
| <a id="secondaryartifactbase-role"></a>`role` | [NonEmptyString](#nonemptystring) | no | Artifact role within the RC manifest, such as source artifact, vote-manifest supplement, or convenience artifact. |
| <a id="secondaryartifactbase-artifact-origin"></a>`artifact_origin` | [NonEmptyString](#nonemptystring) | no | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="secondaryartifactbase-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](#gitcommitsha) | no | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="secondaryartifactbase-reproducibility"></a>`reproducibility` | [ReproducibilitySelector](#reproducibilityselector) | no | Reproducibility policy or result block associated with the related source or secondary artifact. |
| <a id="secondaryartifactbase-inventory"></a>`inventory` | [SupplementalInventoryReference](#supplementalinventoryreference) | no | Signed inventory or supplemental staging metadata associated with the related artifact. |

<a id="secondaryartifactmanifestv1"></a>
### SecondaryArtifactManifestV1

A reusable secondary-artifact manifest fragment.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-secondary-artifact-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-manifest-v1.schema.json)
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
| <a id="sha256checksumpayload-value"></a>`value` | [Sha256Hex](#sha256hex) | yes | Declared checksum or digest value recorded in the related payload. |
| <a id="sha256checksumpayload-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

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
| <a id="sha512checksumpayload-value"></a>`value` | [Sha512Hex](#sha512hex) | yes | Declared checksum or digest value recorded in the related payload. |
| <a id="sha512checksumpayload-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

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
| <a id="shallowarchiveanalysisreport-classification"></a>`classification` | [NonEmptyString](#nonemptystring) | yes | High-level shallow-comparison classification that summarizes the most important archive drift pattern Buildish observed. |
| <a id="shallowarchiveanalysisreport-raw-bytes-equal"></a>`raw_bytes_equal` | bool | yes | Whether raw staged and rebuilt bytes matched before any archive-aware normalization. |
| <a id="shallowarchiveanalysisreport-archive-format"></a>`archive_format` | Literal['tar', 'zip'] | no | Detected top-level archive format of the compared artifact when shallow archive inspection succeeded. |
| <a id="shallowarchiveanalysisreport-staged-archive-format"></a>`staged_archive_format` | ArchiveAnalysisFormat | yes | Detected top-level archive format of the staged artifact retained for shallow archive inspection. |
| <a id="shallowarchiveanalysisreport-rebuilt-archive-format"></a>`rebuilt_archive_format` | ArchiveAnalysisFormat | yes | Detected top-level archive format of the rebuilt artifact retained for shallow archive inspection. |
| <a id="shallowarchiveanalysisreport-staged-entry-count"></a>`staged_entry_count` | int | no | Number of top-level archive entries found in the staged artifact during shallow inspection. |
| <a id="shallowarchiveanalysisreport-rebuilt-entry-count"></a>`rebuilt_entry_count` | int | no | Number of top-level archive entries found in the rebuilt artifact during shallow inspection. |
| <a id="shallowarchiveanalysisreport-missing-paths"></a>`missing_paths` | list[[NonEmptyString](#nonemptystring)] | no | Archive or repository paths that were present in the staged artifact but missing from the rebuilt artifact. |
| <a id="shallowarchiveanalysisreport-unexpected-paths"></a>`unexpected_paths` | list[[NonEmptyString](#nonemptystring)] | no | Archive or repository paths that were present only in the rebuilt artifact and not in the staged artifact. |
| <a id="shallowarchiveanalysisreport-entry-order-mismatches"></a>`entry_order_mismatches` | list[[NonEmptyString](#nonemptystring)] | no | Archive-entry ordering differences detected between the staged and rebuilt artifacts during shallow comparison. |
| <a id="shallowarchiveanalysisreport-metadata-mismatches"></a>`metadata_mismatches` | list[[NonEmptyString](#nonemptystring)] | no | Archive-entry metadata differences, such as timestamps, modes, owners, or file-type drift, found during shallow comparison. |
| <a id="shallowarchiveanalysisreport-content-mismatches"></a>`content_mismatches` | list[[NonEmptyString](#nonemptystring)] | no | Archive member paths whose direct top-level content bytes differed between the staged and rebuilt artifacts during shallow comparison. |

<a id="signaturereference"></a>
### SignatureReference

One detached OpenPGP signature reference.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="signaturereference-type"></a>`type` | Literal['openpgp-detached-ascii-armored'] | no | Stable subtype discriminator or signature-reference type for the related payload. |
| <a id="signaturereference-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |

<a id="signatureverificationpayload"></a>
### SignatureVerificationPayload

Serialized detached-signature verification details.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="signatureverificationpayload-signer-fingerprint"></a>`signer_fingerprint` | [NonEmptyString](#nonemptystring) | yes | OpenPGP fingerprint of the key that verified the related detached signature. |
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
| <a id="sourceartifactcontract-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="sourceartifactcontract-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | yes | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
| <a id="sourceartifactcontract-artifact-origin"></a>`artifact_origin` | [NonEmptyString](#nonemptystring) | yes | Origin classification describing whether the artifact came from a source build, registry, or repository staging area. |
| <a id="sourceartifactcontract-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](#gitcommitsha) | yes | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
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
- schema file: [`buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="sourceartifactreproducibilitymetadata-profile-id"></a>`profile_id` | [NonEmptyString](#nonemptystring) | yes | Reproducibility profile identifier selected for the related artifact or source verification. |
| <a id="sourceartifactreproducibilitymetadata-comparison-mode"></a>`comparison_mode` | [NonEmptyString](#nonemptystring) | yes | Declared reproducibility comparison mode used for the related artifact or profile. |
| <a id="sourceartifactreproducibilitymetadata-failure-class"></a>`failure_class` | [NonEmptyString](#nonemptystring) | no | Structured failure classification that summarizes the main reason why verification or reproducibility failed. |
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
| <a id="sourceartifactverificationsection-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
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
| <a id="supplementalinventoryreference-filename"></a>`filename` | [NonEmptyString](#nonemptystring) | yes | Artifact filename as seen in staging, manifests, or retained evidence. |
| <a id="supplementalinventoryreference-sha512"></a>`sha512` | [Sha512Hex](#sha512hex) | yes | SHA-512 checksum payload associated with the related artifact. |
| <a id="supplementalinventoryreference-uri"></a>`uri` | [NonEmptyString](#nonemptystring) | no | Canonical artifact or signature URI recorded in a Buildish manifest or verification report. |
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
| <a id="toolingprovenance-repository"></a>`repository` | [NonEmptyString](#nonemptystring) | yes | Repository identifier or repository name associated with the related provenance or external-auth record. |
| <a id="toolingprovenance-repository-url"></a>`repository_url` | [NonEmptyString](#nonemptystring) | yes | Canonical clone or browser URL for the related repository. |
| <a id="toolingprovenance-git-commit-sha"></a>`git_commit_sha` | [GitCommitSha](#gitcommitsha) | yes | Git commit SHA recorded for the related artifact, manifest, or provenance block. |
| <a id="toolingprovenance-git-ref"></a>`git_ref` | [NonEmptyString](#nonemptystring) | no | Git ref name recorded in tooling provenance for the related manifest or emitted file. |
| <a id="toolingprovenance-version"></a>`version` | [NonEmptyString](#nonemptystring) | no | Release version string without a leading `v` prefix. |

<a id="verificationfailurepayload"></a>
### VerificationFailurePayload

One collected verification failure.

- category: `emitted`
- ownership: `tooling-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verificationfailurepayload-scope"></a>`scope` | [NonEmptyString](#nonemptystring) | yes | Machine-readable scope label that identifies which verification surface produced the related failure record. |
| <a id="verificationfailurepayload-subject"></a>`subject` | [NonEmptyString](#nonemptystring) | yes | Human-facing verification failure subject that identifies what failed. |
| <a id="verificationfailurepayload-message"></a>`message` | [NonEmptyString](#nonemptystring) | yes | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |

<a id="verifyrcreportv1"></a>
### VerifyRcReportV1

Machine-readable Phase 1a RC verification report.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-verify-rc-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-report-v1.schema.json)
- audience: `supported`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="verifyrcreportv1-schema-version"></a>`schema_version` | [SchemaVersionV1](#schemaversionv1) | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="verifyrcreportv1-report-type"></a>`report_type` | Literal['verify-rc'] | no | Stable report discriminator for one Buildish JSON report contract. |
| <a id="verifyrcreportv1-component-id"></a>`component_id` | str | no | Stable component identifier used across Buildish manifests, reports, and release-state records. |
| <a id="verifyrcreportv1-version"></a>`version` | str | no | Release version string without a leading `v` prefix. |
| <a id="verifyrcreportv1-rc-tag"></a>`rc_tag` | str | no | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="verifyrcreportv1-source-commit-sha"></a>`source_commit_sha` | str | no | Resolved source Git commit SHA recorded in the authoritative RC manifest or verify-rc report. |
| <a id="verifyrcreportv1-source-date-epoch"></a>`source_date_epoch` | int | no | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="verifyrcreportv1-source-repository-url"></a>`source_repository_url` | str | no | Canonical source repository URL recorded in the RC vote manifest or verification report. |
| <a id="verifyrcreportv1-manifest-url"></a>`manifest_url` | [NonEmptyString](#nonemptystring) | yes | URL of the RC vote manifest that Buildish fetched or verified. |
| <a id="verifyrcreportv1-keys-url"></a>`keys_url` | [NonEmptyString](#nonemptystring) | yes | ASF KEYS URL that Buildish used or expected while establishing the RC trust roots. |
| <a id="verifyrcreportv1-verdict"></a>`verdict` | [VerificationVerdict](#verificationverdict) | yes | Structured verification or reproducibility verdict for the related subject. |
| <a id="verifyrcreportv1-work-dir"></a>`work_dir` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the verify-rc working directory where retained reports, logs, and downloaded artifacts were stored. |
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
- schema file: [`buildish-release-tooling-vote-materials-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-read.schema.json)
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
- schema file: [`buildish-release-tooling-vote-materials-strict.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-strict.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="votematerialsstrict-source-artifacts"></a>`source_artifacts` | list[[SourceArtifactContract](#sourceartifactcontract)] | yes | Manifest entries that describe the primary staged source artifact and any additional source-release materials. |
| <a id="votematerialsstrict-secondary-artifacts"></a>`secondary_artifacts` | list[AnySecondaryArtifact] | no | Declared secondary artifacts retained in the RC vote manifest or secondary-artifact manifest. |

## Internal unstable command action manifest types

Machine-readable command action manifests written for workflow coordination. These are Buildish-owned internal input/output contracts and are intentionally unstable.

<a id="attachgithubreleaseassetsmanifest"></a>
### AttachGithubReleaseAssetsManifest

Action manifest emitted after uploading primary and derived assets to a GitHub release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-attach-github-release-assets-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-attach-github-release-assets-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="attachgithubreleaseassetsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="attachgithubreleaseassetsmanifest-action"></a>`action` | Literal['attach-github-release-assets'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="attachgithubreleaseassetsmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="attachgithubreleaseassetsmanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="attachgithubreleaseassetsmanifest-release-id"></a>`release_id` | [NonEmptyString](#nonemptystring) | yes | GitHub release id associated with the related draft or final release record. |
| <a id="attachgithubreleaseassetsmanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="attachgithubreleaseassetsmanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="attachgithubreleaseassetsmanifest-release-url"></a>`release_url` | [NonEmptyString](#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="attachgithubreleaseassetsmanifest-primary-asset-names"></a>`primary_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | Primary release asset names that Buildish attached or expected to attach to the selected GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-uploaded-asset-names"></a>`uploaded_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | GitHub release asset names that Buildish uploaded during the related command. |
| <a id="attachgithubreleaseassetsmanifest-generated-checksum-asset-names"></a>`generated_checksum_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | Generated checksum asset names that Buildish attached or expected to attach to the GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-generated-signature-asset-names"></a>`generated_signature_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | Generated detached-signature asset names that Buildish attached or expected to attach to the GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-checksum-algorithms"></a>`checksum_algorithms` | list[[NonEmptyString](#nonemptystring)] | yes | Checksum algorithms that Buildish generated or expects for the related artifact set. |
| <a id="attachgithubreleaseassetsmanifest-gpg-fingerprint"></a>`gpg_fingerprint` | str | yes | OpenPGP fingerprint of the signing key Buildish used or verified. |

<a id="buildsourcercmanifest"></a>
### BuildSourceRcManifest

Action manifest emitted after building and staging the signed source RC bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-build-source-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-build-source-rc-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="buildsourcercmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="buildsourcercmanifest-action"></a>`action` | Literal['build-source-rc'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="buildsourcercmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="buildsourcercmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="buildsourcercmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="buildsourcercmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="buildsourcercmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-path"></a>`source_artifact_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the locally produced or staged source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-sha512"></a>`source_artifact_sha512` | [NonEmptyString](#nonemptystring) | yes | SHA-512 digest of the staged or locally produced source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-sha512-path"></a>`source_artifact_sha512_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the `.sha512` sidecar generated for the locally produced source artifact. |
| <a id="buildsourcercmanifest-source-artifact-asc-path"></a>`source_artifact_asc_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the detached OpenPGP signature file for the locally produced source artifact. |
| <a id="buildsourcercmanifest-staging-url"></a>`staging_url` | [NonEmptyString](#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |

<a id="cleanupdevsvnrcsmanifest"></a>
### CleanupDevSvnRcsManifest

Action manifest emitted after old or conflicting RC staging directories are removed.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="cleanupdevsvnrcsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="cleanupdevsvnrcsmanifest-action"></a>`action` | Literal['cleanup-dev-svn-rcs'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="cleanupdevsvnrcsmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="cleanupdevsvnrcsmanifest-dev-base-url"></a>`dev_base_url` | [NonEmptyString](#nonemptystring) | yes | Configured ASF `dist/dev` base URL that the cleanup or publication action targeted. |
| <a id="cleanupdevsvnrcsmanifest-deleted-rc-directories"></a>`deleted_rc_directories` | list[[NonEmptyString](#nonemptystring)] | yes | ASF dev/dist RC directories that Buildish deleted during cleanup. |

<a id="commandactionmanifest"></a>
### CommandActionManifest

Common top-level shape for command action manifests.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-command-action-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-action-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="commandactionmanifest-component"></a>`component` | [NonEmptyString](#nonemptystring) | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="commandactionmanifest-action"></a>`action` | [NonEmptyString](#nonemptystring) | yes | Stable command action identifier written by one Buildish command manifest. |

<a id="createfinaltagmanifest"></a>
### CreateFinalTagManifest

Action manifest emitted after creating or validating the final immutable release tag.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-create-final-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-final-tag-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createfinaltagmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createfinaltagmanifest-action"></a>`action` | Literal['create-final-tag'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createfinaltagmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="createfinaltagmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="createfinaltagmanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="createfinaltagmanifest-target-commit"></a>`target_commit` | [NonEmptyString](#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="createfinaltagmanifest-tag-creation-mode"></a>`tag_creation_mode` | [NonEmptyString](#nonemptystring) | yes | Mode that Buildish used when creating or reusing the related annotated Git tag. |
| <a id="createfinaltagmanifest-created-ref"></a>`created_ref` | str | yes | Git ref name that Buildish created or reused while performing the related tag or ref action. |

<a id="creatercmaterializationtagmanifest"></a>
### CreateRcMaterializationTagManifest

Action manifest emitted after tagging one detached RC materialization commit.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="creatercmaterializationtagmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="creatercmaterializationtagmanifest-action"></a>`action` | Literal['create-rc-materialization-tag'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="creatercmaterializationtagmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="creatercmaterializationtagmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="creatercmaterializationtagmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="creatercmaterializationtagmanifest-target-commit"></a>`target_commit` | [NonEmptyString](#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="creatercmaterializationtagmanifest-tag-target-origin"></a>`tag_target_origin` | Literal['materialized-commit', 'source-commit'] | yes | Origin that Buildish used for the target commit when tagging the RC materialization result. |
| <a id="creatercmaterializationtagmanifest-cleanup-materialized-ref-name"></a>`cleanup_materialized_ref_name` | str | yes | Temporary materialization ref that Buildish considered for cleanup after tagging the RC. |
| <a id="creatercmaterializationtagmanifest-cleanup-materialized-ref-mode"></a>`cleanup_materialized_ref_mode` | [NonEmptyString](#nonemptystring) | yes | Policy that Buildish used when deciding whether to delete the temporary materialization ref after tagging. |
| <a id="creatercmaterializationtagmanifest-tag-creation-mode"></a>`tag_creation_mode` | [NonEmptyString](#nonemptystring) | yes | Mode that Buildish used when creating or reusing the related annotated Git tag. |
| <a id="creatercmaterializationtagmanifest-created-ref"></a>`created_ref` | str | yes | Git ref name that Buildish created or reused while performing the related tag or ref action. |

<a id="createreleasebranchmanifest"></a>
### CreateReleaseBranchManifest

Action manifest emitted after resolving or creating a release branch.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-create-release-branch-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-release-branch-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createreleasebranchmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createreleasebranchmanifest-action"></a>`action` | Literal['create-release-branch'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createreleasebranchmanifest-release-line"></a>`release_line` | [NonEmptyString](#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="createreleasebranchmanifest-release-branch"></a>`release_branch` | [NonEmptyString](#nonemptystring) | yes | Git branch name that Buildish resolved as the authoritative release branch. |
| <a id="createreleasebranchmanifest-source-ref"></a>`source_ref` | [NonEmptyString](#nonemptystring) | yes | Source ref that Buildish used as the starting point for the related release-branch or materialization action. |

<a id="createsourceartifactmanifest"></a>
### CreateSourceArtifactManifest

Action manifest emitted after creating one local source release artifact.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-create-source-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-source-artifact-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createsourceartifactmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createsourceartifactmanifest-action"></a>`action` | Literal['create-source-artifact'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createsourceartifactmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="createsourceartifactmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="createsourceartifactmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="createsourceartifactmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="createsourceartifactmanifest-source-artifact-path"></a>`source_artifact_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path of the locally produced or staged source release artifact. |
| <a id="createsourceartifactmanifest-source-artifact-sha512"></a>`source_artifact_sha512` | [NonEmptyString](#nonemptystring) | yes | SHA-512 digest of the staged or locally produced source release artifact. |

<a id="finalizedraftgithubreleasemanifest"></a>
### FinalizeDraftGithubReleaseManifest

Action manifest emitted after finalizing a selected GitHub draft release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-finalize-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-draft-github-release-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="finalizedraftgithubreleasemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="finalizedraftgithubreleasemanifest-action"></a>`action` | Literal['finalize-draft-github-release'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="finalizedraftgithubreleasemanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="finalizedraftgithubreleasemanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="finalizedraftgithubreleasemanifest-release-id"></a>`release_id` | [NonEmptyString](#nonemptystring) | yes | GitHub release id associated with the related draft or final release record. |
| <a id="finalizedraftgithubreleasemanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="finalizedraftgithubreleasemanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="finalizedraftgithubreleasemanifest-release-url"></a>`release_url` | [NonEmptyString](#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="finalizedraftgithubreleasemanifest-deleted-asset-names"></a>`deleted_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | GitHub Release asset names that Buildish deleted during the related release-finalization step. |
| <a id="finalizedraftgithubreleasemanifest-finalize-mode"></a>`finalize_mode` | [NonEmptyString](#nonemptystring) | yes | Mode that Buildish used when finalizing the selected draft GitHub release. |

<a id="finalizercvotematerialsmanifest"></a>
### FinalizeRcVoteMaterialsManifest

Action manifest emitted after publishing and signing final RC vote materials.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="finalizercvotematerialsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="finalizercvotematerialsmanifest-action"></a>`action` | Literal['finalize-rc-vote-materials'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="finalizercvotematerialsmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="finalizercvotematerialsmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="finalizercvotematerialsmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="finalizercvotematerialsmanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="finalizercvotematerialsmanifest-rc-tag-target-commit"></a>`rc_tag_target_commit` | [NonEmptyString](#nonemptystring) | yes | Git commit SHA that the RC tag resolved to during verification or publication. |
| <a id="finalizercvotematerialsmanifest-source-artifact-url"></a>`source_artifact_url` | [NonEmptyString](#nonemptystring) | yes | Canonical staged download URL of the source release artifact referenced by the RC vote materials. |
| <a id="finalizercvotematerialsmanifest-authoritative-manifest-url"></a>`authoritative_manifest_url` | [NonEmptyString](#nonemptystring) | yes | Canonical staged URL of the signed RC vote manifest. |
| <a id="finalizercvotematerialsmanifest-authoritative-manifest-sha512"></a>`authoritative_manifest_sha512` | [NonEmptyString](#nonemptystring) | yes | SHA-512 digest of the authoritative staged RC vote manifest. |
| <a id="finalizercvotematerialsmanifest-bootstrap-script-url"></a>`bootstrap_script_url` | [NonEmptyString](#nonemptystring) | yes | Staged URL of the emitted verify-rc bootstrap helper script. |
| <a id="finalizercvotematerialsmanifest-bootstrap-script-sha512"></a>`bootstrap_script_sha512` | [NonEmptyString](#nonemptystring) | yes | SHA-512 digest of the emitted verify-rc bootstrap script. |
| <a id="finalizercvotematerialsmanifest-draft-release-url"></a>`draft_release_url` | [NonEmptyString](#nonemptystring) | yes | GitHub draft release URL associated with the current RC or final release workflow. |
| <a id="finalizercvotematerialsmanifest-secondary-artifact-count"></a>`secondary_artifact_count` | [NonEmptyString](#nonemptystring) | yes | Count of secondary artifacts associated with the related manifest or publication step. |
| <a id="finalizercvotematerialsmanifest-mirrored-asset-names"></a>`mirrored_asset_names` | list[[NonEmptyString](#nonemptystring)] | yes | GitHub release asset names that Buildish mirrored from the staged vote materials into the draft release bundle. |
| <a id="finalizercvotematerialsmanifest-gpg-fingerprint"></a>`gpg_fingerprint` | [NonEmptyString](#nonemptystring) | yes | OpenPGP fingerprint of the signing key Buildish used or verified. |

<a id="materializercgitcontentmanifest"></a>
### MaterializeRcGitContentManifest

Action manifest emitted after building detached RC materialization Git content.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-materialize-rc-git-content-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-materialize-rc-git-content-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="materializercgitcontentmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="materializercgitcontentmanifest-action"></a>`action` | Literal['materialize-rc-git-content'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="materializercgitcontentmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="materializercgitcontentmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="materializercgitcontentmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="materializercgitcontentmanifest-materialized-paths"></a>`materialized_paths` | list[[NonEmptyString](#nonemptystring)] | yes | Filesystem paths that the materialization step created or refreshed for the current RC. |
| <a id="materializercgitcontentmanifest-materialized-commit-sha"></a>`materialized_commit_sha` | [NonEmptyString](#nonemptystring) | yes | Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow. |
| <a id="materializercgitcontentmanifest-materialized-ref-name"></a>`materialized_ref_name` | [NonEmptyString](#nonemptystring) | yes | Temporary Git ref name that Buildish created or reused for RC materialization. |
| <a id="materializercgitcontentmanifest-materialized-ref-mode"></a>`materialized_ref_mode` | [NonEmptyString](#nonemptystring) | yes | Policy that Buildish used when creating or reusing the temporary materialization ref. |

<a id="preparercmanifest"></a>
### PrepareRcManifest

Action manifest emitted after prepare-rc resolves one RC workflow state bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-prepare-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="preparercmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="preparercmanifest-action"></a>`action` | Literal['prepare-rc'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="preparercmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="preparercmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="preparercmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="preparercmanifest-resolved-release-branch"></a>`resolved_release_branch` | [NonEmptyString](#nonemptystring) | yes | Release branch name that Buildish resolved for the selected version. |
| <a id="preparercmanifest-rc-number"></a>`rc_number` | [NonEmptyString](#nonemptystring) | yes | Numeric RC sequence selected for the related version. |
| <a id="preparercmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="preparercmanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="preparercmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="preparercmanifest-source-artifact-root-name"></a>`source_artifact_root_name` | [NonEmptyString](#nonemptystring) | yes | Root directory name that the source release archive should unpack to. |
| <a id="preparercmanifest-source-artifact-prefix-path"></a>`source_artifact_prefix_path` | [NonEmptyString](#nonemptystring) | yes | Top-level path prefix inside the source release archive. |
| <a id="preparercmanifest-staging-url"></a>`staging_url` | [NonEmptyString](#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |
| <a id="preparercmanifest-cleanup-existing-rc-staging"></a>`cleanup_existing_rc_staging` | Literal['true'] | no | Whether the prepare-rc flow cleaned up pre-existing same-version RC staging state before publishing new materials. |
| <a id="preparercmanifest-draft-release-action"></a>`draft_release_action` | Literal['recreate'] | no | Draft GitHub release convergence action that prepare-rc used when emitting new vote materials. |
| <a id="preparercmanifest-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |

<a id="pruneolderlinereleasesmanifest"></a>
### PruneOlderLineReleasesManifest

Action manifest emitted after pruning older same-line releases from dist/release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-prune-older-line-releases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prune-older-line-releases-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pruneolderlinereleasesmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="pruneolderlinereleasesmanifest-action"></a>`action` | Literal['prune-older-line-releases'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="pruneolderlinereleasesmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="pruneolderlinereleasesmanifest-release-line"></a>`release_line` | [NonEmptyString](#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="pruneolderlinereleasesmanifest-pruned-versions"></a>`pruned_versions` | list[[NonEmptyString](#nonemptystring)] | yes | Older release versions that Buildish removed from the active release line while pruning prior dist/release artifacts. |
| <a id="pruneolderlinereleasesmanifest-release-base-url"></a>`release_base_url` | [NonEmptyString](#nonemptystring) | yes | Base ASF dist/release URL associated with the related publication action. |

<a id="publishatrcandidatemanifest"></a>
### PublishAtrCandidateManifest

Action manifest emitted after publishing one release candidate to ATR.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-publish-atr-candidate-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-atr-candidate-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishatrcandidatemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishatrcandidatemanifest-action"></a>`action` | Literal['publish-atr-candidate'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishatrcandidatemanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishatrcandidatemanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="publishatrcandidatemanifest-atr-base-url"></a>`atr_base_url` | [NonEmptyString](#nonemptystring) | yes | Base ATR service URL that Buildish used for the related candidate upload or status query. |
| <a id="publishatrcandidatemanifest-atr-committee"></a>`atr_committee` | [NonEmptyString](#nonemptystring) | yes | ASF committee slug that Buildish reported to ATR for the related release candidate. |
| <a id="publishatrcandidatemanifest-atr-project"></a>`atr_project` | [NonEmptyString](#nonemptystring) | yes | ATR project or product-line identifier that Buildish reported for the related release candidate. |
| <a id="publishatrcandidatemanifest-atr-release-mode"></a>`atr_release_mode` | [NonEmptyString](#nonemptystring) | yes | ATR release mode that Buildish selected for the related publication run. |
| <a id="publishatrcandidatemanifest-atr-phase"></a>`atr_phase` | [NonEmptyString](#nonemptystring) | yes | ATR publication phase that Buildish targeted or reported for the related candidate. |
| <a id="publishatrcandidatemanifest-atr-latest-revision"></a>`atr_latest_revision` | str | yes | Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report. |
| <a id="publishatrcandidatemanifest-uploaded-file-names"></a>`uploaded_file_names` | list[[NonEmptyString](#nonemptystring)] | yes | File names that Buildish uploaded to ATR for the related candidate. |
| <a id="publishatrcandidatemanifest-waited-for-checks"></a>`waited_for_checks` | Literal['true', 'false'] | yes | Whether Buildish waited for ATR checks to complete before emitting the related command manifest. |
| <a id="publishatrcandidatemanifest-atr-total-checks"></a>`atr_total_checks` | [NonEmptyString](#nonemptystring) | yes | Total number of ATR checks observed for the related candidate revision. |
| <a id="publishatrcandidatemanifest-atr-failure-count"></a>`atr_failure_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that reported a failing outcome for the related candidate or report. |
| <a id="publishatrcandidatemanifest-atr-exception-count"></a>`atr_exception_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that ended in an exception state for the related candidate or report. |
| <a id="publishatrcandidatemanifest-atr-warning-count"></a>`atr_warning_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that reported warnings for the related candidate or report. |

<a id="publishdockerhubmovingtagsmanifest"></a>
### PublishDockerhubMovingTagsManifest

Action manifest emitted after publishing moving Docker Hub image aliases.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishdockerhubmovingtagsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishdockerhubmovingtagsmanifest-action"></a>`action` | Literal['publish-dockerhub-moving-tags'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishdockerhubmovingtagsmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishdockerhubmovingtagsmanifest-source-image"></a>`source_image` | [NonEmptyString](#nonemptystring) | yes | Exact source OCI image reference that should be copied to produce the published moving aliases. |
| <a id="publishdockerhubmovingtagsmanifest-image-repository"></a>`image_repository` | [NonEmptyString](#nonemptystring) | yes | Container image repository name without the moving tag or digest suffix. |
| <a id="publishdockerhubmovingtagsmanifest-published-alias-refs"></a>`published_alias_refs` | list[[NonEmptyString](#nonemptystring)] | yes | Fully qualified target image references that Buildish published as moving aliases. |

<a id="publishsourcereleasesvnmanifest"></a>
### PublishSourceReleaseSvnManifest

Action manifest emitted after promoting a verified source artifact into dist/release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-publish-source-release-svn-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-source-release-svn-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishsourcereleasesvnmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishsourcereleasesvnmanifest-action"></a>`action` | Literal['publish-source-release-svn'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishsourcereleasesvnmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishsourcereleasesvnmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="publishsourcereleasesvnmanifest-source-url"></a>`source_url` | [NonEmptyString](#nonemptystring) | yes | Source URL that Buildish copied or verified during a publication action. |
| <a id="publishsourcereleasesvnmanifest-target-url"></a>`target_url` | [NonEmptyString](#nonemptystring) | yes | Destination URL that Buildish published or copied content to. |
| <a id="publishsourcereleasesvnmanifest-verified-source-artifact-sha512"></a>`verified_source_artifact_sha512` | [NonEmptyString](#nonemptystring) | yes | Verified SHA-512 digest of the source release artifact promoted to ASF dist/release. |
| <a id="publishsourcereleasesvnmanifest-publish-mode"></a>`publish_mode` | [NonEmptyString](#nonemptystring) | yes | Mode that Buildish used when publishing the verified source artifact to ASF `dist/release`. |

<a id="recordartifactmanifest"></a>
### RecordArtifactManifest

Action manifest emitted after writing one typed secondary-artifact bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-record-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-record-artifact-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="recordartifactmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="recordartifactmanifest-action"></a>`action` | Literal['record-artifact'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="recordartifactmanifest-artifact-id"></a>`artifact_id` | [NonEmptyString](#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="recordartifactmanifest-kind"></a>`kind` | [NonEmptyString](#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="recordartifactmanifest-artifact-manifest-path"></a>`artifact_manifest_path` | [NonEmptyString](#nonemptystring) | yes | Filesystem path to the emitted secondary-artifact manifest fragment. |
| <a id="recordartifactmanifest-artifact-bundle-dir"></a>`artifact_bundle_dir` | [NonEmptyString](#nonemptystring) | yes | Directory that contains one emitted secondary-artifact registration bundle. |
| <a id="recordartifactmanifest-inventory-paths"></a>`inventory_paths` | list[[NonEmptyString](#nonemptystring)] | yes | Filesystem paths of supplemental inventory files emitted alongside one artifact bundle. |

<a id="releaseversionmanifest"></a>
### ReleaseVersionManifest

Action manifest emitted after a full release-version orchestration run completes.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-release-version-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="releaseversionmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="releaseversionmanifest-action"></a>`action` | Literal['release-version'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="releaseversionmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="releaseversionmanifest-release-line"></a>`release_line` | [NonEmptyString](#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="releaseversionmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="releaseversionmanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="releaseversionmanifest-archive-versions"></a>`archive_versions` | list[[NonEmptyString](#nonemptystring)] | yes | Older same-line release versions that Buildish resolved for archival pruning. |
| <a id="releaseversionmanifest-release-url"></a>`release_url` | [NonEmptyString](#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="releaseversionmanifest-moving-tags"></a>`moving_tags` | list[[NonEmptyString](#nonemptystring)] | yes | Derived moving tags or aliases that should point at the final released version. |
| <a id="releaseversionmanifest-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |

<a id="reportatrchecksmanifest"></a>
### ReportAtrChecksManifest

Action manifest emitted after summarizing ATR checks for one candidate revision.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-report-atr-checks-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-report-atr-checks-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="reportatrchecksmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="reportatrchecksmanifest-action"></a>`action` | Literal['report-atr-checks'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="reportatrchecksmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="reportatrchecksmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="reportatrchecksmanifest-atr-base-url"></a>`atr_base_url` | [NonEmptyString](#nonemptystring) | yes | Base ATR service URL that Buildish used for the related candidate upload or status query. |
| <a id="reportatrchecksmanifest-atr-committee"></a>`atr_committee` | [NonEmptyString](#nonemptystring) | yes | ASF committee slug that Buildish reported to ATR for the related release candidate. |
| <a id="reportatrchecksmanifest-atr-project"></a>`atr_project` | [NonEmptyString](#nonemptystring) | yes | ATR project or product-line identifier that Buildish reported for the related release candidate. |
| <a id="reportatrchecksmanifest-atr-phase"></a>`atr_phase` | [NonEmptyString](#nonemptystring) | yes | ATR publication phase that Buildish targeted or reported for the related candidate. |
| <a id="reportatrchecksmanifest-atr-latest-revision"></a>`atr_latest_revision` | str | yes | Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report. |
| <a id="reportatrchecksmanifest-atr-reported-revision"></a>`atr_reported_revision` | str | yes | ATR candidate revision that Buildish specifically reported in the related checks summary. |
| <a id="reportatrchecksmanifest-atr-total-checks"></a>`atr_total_checks` | [NonEmptyString](#nonemptystring) | yes | Total number of ATR checks observed for the related candidate revision. |
| <a id="reportatrchecksmanifest-atr-failure-count"></a>`atr_failure_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that reported a failing outcome for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-exception-count"></a>`atr_exception_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that ended in an exception state for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-warning-count"></a>`atr_warning_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that reported warnings for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-success-count"></a>`atr_success_count` | [NonEmptyString](#nonemptystring) | yes | Number of ATR checks that reported success for the related candidate or report. |
| <a id="reportatrchecksmanifest-strict-checking"></a>`strict_checking` | Literal['true', 'false'] | yes | Whether the related check or reporting step should fail the command when warnings or failures are present. |
| <a id="reportatrchecksmanifest-would-block-release"></a>`would_block_release` | Literal['true', 'false'] | yes | Whether the related check result would block release publication under the requested strictness policy. |

<a id="syncdraftgithubreleasemanifest"></a>
### SyncDraftGithubReleaseManifest

Action manifest emitted after synchronizing the draft GitHub release with staged RC artifacts.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-sync-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-sync-draft-github-release-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="syncdraftgithubreleasemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="syncdraftgithubreleasemanifest-action"></a>`action` | Literal['sync-draft-github-release'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="syncdraftgithubreleasemanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="syncdraftgithubreleasemanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="syncdraftgithubreleasemanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="syncdraftgithubreleasemanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="syncdraftgithubreleasemanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="syncdraftgithubreleasemanifest-staging-url"></a>`staging_url` | [NonEmptyString](#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |
| <a id="syncdraftgithubreleasemanifest-deleted-release-ids"></a>`deleted_release_ids` | list[[NonEmptyString](#nonemptystring)] | yes | GitHub draft release ids that Buildish deleted while converging on one selected release candidate. |
| <a id="syncdraftgithubreleasemanifest-release-id"></a>`release_id` | str | yes | GitHub release id associated with the related draft or final release record. |
| <a id="syncdraftgithubreleasemanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="syncdraftgithubreleasemanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="syncdraftgithubreleasemanifest-release-url"></a>`release_url` | [NonEmptyString](#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="syncdraftgithubreleasemanifest-sync-mode"></a>`sync_mode` | [NonEmptyString](#nonemptystring) | yes | Mode that Buildish used when reconciling the selected draft GitHub release with staged RC materials. |

<a id="updatemovingimagealiasesmanifest"></a>
### UpdateMovingImageAliasesManifest

Action manifest emitted after resolving moving OCI image aliases for publication.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-update-moving-image-aliases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-image-aliases-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="updatemovingimagealiasesmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="updatemovingimagealiasesmanifest-action"></a>`action` | Literal['update-moving-image-aliases'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="updatemovingimagealiasesmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="updatemovingimagealiasesmanifest-exact-image-tag"></a>`exact_image_tag` | [NonEmptyString](#nonemptystring) | yes | Exact released image tag that Buildish uses as the source for moving image aliases. |
| <a id="updatemovingimagealiasesmanifest-image-aliases"></a>`image_aliases` | list[[NonEmptyString](#nonemptystring)] | yes | Derived moving container tags that should point at the exact released image tag. |

<a id="updatemovingtagsmanifest"></a>
### UpdateMovingTagsManifest

Action manifest emitted after updating moving Git tags for a final release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`buildish-release-tooling-update-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-tags-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="updatemovingtagsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="updatemovingtagsmanifest-action"></a>`action` | Literal['update-moving-tags'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="updatemovingtagsmanifest-version"></a>`version` | [NonEmptyString](#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="updatemovingtagsmanifest-final-tag"></a>`final_tag` | [NonEmptyString](#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="updatemovingtagsmanifest-target-commit"></a>`target_commit` | [NonEmptyString](#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="updatemovingtagsmanifest-updated-tags"></a>`updated_tags` | list[[NonEmptyString](#nonemptystring)] | yes | Moving tags that Buildish updated during the related tag-publication action. |
| <a id="updatemovingtagsmanifest-skipped-tags"></a>`skipped_tags` | list[[NonEmptyString](#nonemptystring)] | yes | Moving tags that Buildish intentionally left unchanged during the related update operation. |
| <a id="updatemovingtagsmanifest-tag-update-modes"></a>`tag_update_modes` | list[[NonEmptyString](#nonemptystring)] | yes | Per-tag update outcomes describing how each moving tag was handled during the related publication run. |

## Harness configuration types

Committed and resolved release-harness configuration models.

<a id="releaseharnessconfig"></a>
### ReleaseHarnessConfig

Committed `release-harness.yaml` plus optional local overrides.

- category: `authored`
- ownership: `consumer-owned`
- schema file: [`buildish-release-tooling-release-harness-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-harness-config.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: `harness/release-harness.yaml`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="releaseharnessconfig-schema-version"></a>`schema_version` | Literal['1'] | no | Schema version of the enclosing Buildish JSON or YAML contract. |
| <a id="releaseharnessconfig-self-repository"></a>`self_repository` | [SelfRepositoryConfig](#selfrepositoryconfig) | yes | Resolved binding for the primary workflow repository under harness control. |
| <a id="releaseharnessconfig-repository-overrides"></a>`repository_overrides` | dict[str, [RepositoryOverrideConfig](#repositoryoverrideconfig)] | no | Per-repository local override bindings resolved from the harness configuration. |

<a id="repositoryoverrideconfig"></a>
### RepositoryOverrideConfig

Committed harness settings for one explicit repository override.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="repositoryoverrideconfig-local-checkout-mode"></a>`local_checkout_mode` | [RepositoryOverrideCheckoutMode](#repositoryoverridecheckoutmode) | no | Policy describing whether the related repository binding should resolve to a local checkout path. |
| <a id="repositoryoverrideconfig-local-path"></a>`local_path` | str | no | Resolved or configured local filesystem path associated with the related repository binding. |

<a id="resolvedreleaseharnessconfigjson"></a>
### ResolvedReleaseHarnessConfigJson

Machine-readable JSON payload for one resolved harness config file.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-resolved-release-harness-config-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-resolved-release-harness-config-json.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="resolvedreleaseharnessconfigjson-config-path"></a>`config_path` | str | yes | Filesystem path of the resolved configuration document. |
| <a id="resolvedreleaseharnessconfigjson-local-override-path"></a>`local_override_path` | str | yes | Filesystem path of the optional local harness override file that was considered during config loading. |
| <a id="resolvedreleaseharnessconfigjson-local-override-present"></a>`local_override_present` | bool | yes | Whether the optional local harness override file existed and was merged into the effective harness config. |
| <a id="resolvedreleaseharnessconfigjson-self-repository"></a>`self_repository` | [ResolvedRepositoryBindingJson](#resolvedrepositorybindingjson) | yes | Resolved binding for the primary workflow repository under harness control. |
| <a id="resolvedreleaseharnessconfigjson-repository-overrides"></a>`repository_overrides` | dict[str, [ResolvedRepositoryBindingJson](#resolvedrepositorybindingjson)] | no | Per-repository local override bindings resolved from the harness configuration. |

<a id="resolvedrepositorybindingjson"></a>
### ResolvedRepositoryBindingJson

Machine-readable JSON payload for one resolved harness repository binding.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="resolvedrepositorybindingjson-repository-id"></a>`repository_id` | str | yes | Logical repository identifier used by the harness configuration layer. |
| <a id="resolvedrepositorybindingjson-local-checkout-mode"></a>`local_checkout_mode` | str | yes | Policy describing whether the related repository binding should resolve to a local checkout path. |
| <a id="resolvedrepositorybindingjson-local-path"></a>`local_path` | str | yes | Resolved or configured local filesystem path associated with the related repository binding. |

<a id="selfrepositoryconfig"></a>
### SelfRepositoryConfig

Committed harness settings for the workflow repository under test.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="selfrepositoryconfig-repository-id"></a>`repository_id` | str | yes | Logical repository identifier used by the harness configuration layer. |
| <a id="selfrepositoryconfig-local-checkout-mode"></a>`local_checkout_mode` | [SelfRepositoryCheckoutMode](#selfrepositorycheckoutmode) | no | Policy describing whether the related repository binding should resolve to a local checkout path. |
| <a id="selfrepositoryconfig-local-path"></a>`local_path` | str | no | Resolved or configured local filesystem path associated with the related repository binding. |

## Harness scenario and runtime result types

Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results.

<a id="filewriteaction"></a>
### FileWriteAction

A file write that a mocked tool invocation should perform.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="filewriteaction-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="filewriteaction-content"></a>`content` | str | yes | Literal file content that the harness should write or that the mocked tool should emit. |
| <a id="filewriteaction-executable"></a>`executable` | bool | no | Whether the written file should have the executable bit set in the harness workspace. |

<a id="gitrepositoryfixture"></a>
### GitRepositoryFixture

A disposable Git repository that should be initialized inside the workspace.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="gitrepositoryfixture-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="gitrepositoryfixture-default-branch"></a>`default_branch` | str | no | Branch name that the harness should create as the default branch in the disposable Git repository fixture. |
| <a id="gitrepositoryfixture-commit-message"></a>`commit_message` | str | no | Commit message that the harness should use when creating the initial commit in the disposable Git repository fixture. |
| <a id="gitrepositoryfixture-files"></a>`files` | list[[WorkspaceFile](#workspacefile)] | no | Workspace files that the harness should create inside the related fixture repository before execution begins. |

<a id="harnessbuiltinghtagobject"></a>
### HarnessBuiltinGhTagObject

Synthetic GitHub tag-object payload retained by the harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghtagobject-tag"></a>`tag` | str | no | Tag name associated with the related release, workflow fixture, or synthetic GitHub tag-object payload. |
| <a id="harnessbuiltinghtagobject-message"></a>`message` | str | no | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |
| <a id="harnessbuiltinghtagobject-object"></a>`object` | str | no | Git object SHA that the synthetic annotated-tag payload ultimately points at. |

<a id="harnesscommandtraceentry"></a>
### HarnessCommandTraceEntry

One persisted command-trace entry recorded by harness tool shims.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-harness-command-trace-entry.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-command-trace-entry.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesscommandtraceentry-tool"></a>`tool` | str | yes | Tool name associated with the recorded harness command trace entry. |
| <a id="harnesscommandtraceentry-argv"></a>`argv` | list[str] | no | Exact argv list that the harness should match or that it recorded for the related command invocation. |
| <a id="harnesscommandtraceentry-cwd"></a>`cwd` | str | yes | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="harnesscommandtraceentry-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="harnesscommandtraceentry-exit-code"></a>`exit_code` | int | yes | Process exit code that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-stdout"></a>`stdout` | str | no | Captured stdout that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-stderr"></a>`stderr` | str | no | Captured stderr that the harness recorded or should synthesize for the related tool invocation. |
| <a id="harnesscommandtraceentry-delegated"></a>`delegated` | bool | no | Whether the recorded harness command invocation delegated to the real tool implementation. |

<a id="harnessinspectablepaths"></a>
### HarnessInspectablePaths

Stable inspectable workspace paths exposed by the harness CLI.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessinspectablepaths-workspace-root"></a>`workspace_root` | str | yes | Filesystem path of the harness workspace root used by the persisted shim state. |
| <a id="harnessinspectablepaths-primary-git-checkout"></a>`primary_git_checkout` | str | yes | Harness workspace path of the primary repository checkout used for the workflow-under-test. |
| <a id="harnessinspectablepaths-rewritten-workflows"></a>`rewritten_workflows` | str | yes | Harness workspace path that contains workflow YAML files rewritten for local execution. |
| <a id="harnessinspectablepaths-harness-root"></a>`harness_root` | str | yes | Harness workspace path that contains persisted harness state, rewritten workflows, and generated helper files. |
| <a id="harnessinspectablepaths-generated-actions"></a>`generated_actions` | str | yes | Harness workspace path that contains generated helper scripts or wrapper actions. |
| <a id="harnessinspectablepaths-repo-sources"></a>`repo_sources` | str | yes | Harness workspace path that contains repository source templates or seed inputs used to build fixture checkouts. |
| <a id="harnessinspectablepaths-git-origins"></a>`git_origins` | str | yes | Harness workspace path that contains the origin repositories used to seed local Git checkouts. |
| <a id="harnessinspectablepaths-self-git-origin"></a>`self_git_origin` | str | yes | Harness workspace path of the local Git origin repository used to simulate GitHub-side mutations for the primary repository. |
| <a id="harnessinspectablepaths-git-checkouts"></a>`git_checkouts` | str | yes | Harness workspace path that contains generated Git working-copy checkouts. |
| <a id="harnessinspectablepaths-svn-root"></a>`svn_root` | str | yes | Harness workspace path that contains all simulated SVN repository and working-copy state. |
| <a id="harnessinspectablepaths-svn-repository"></a>`svn_repository` | str | yes | Harness workspace path that contains the simulated backing SVN repository state. |
| <a id="harnessinspectablepaths-svn-working-copy"></a>`svn_working_copy` | str | yes | Harness workspace path of the simulated SVN working copy used during the run. |
| <a id="harnessinspectablepaths-step-summaries"></a>`step_summaries` | str | yes | Harness workspace path that contains per-step summary files emitted during the run. |
| <a id="harnessinspectablepaths-job-summaries"></a>`job_summaries` | str | yes | Harness workspace path that contains one rendered markdown or text summary per job. |
| <a id="harnessinspectablepaths-job-statuses"></a>`job_statuses` | str | yes | Final per-job status map emitted by the harness for the reported workflow or sequence run. |
| <a id="harnessinspectablepaths-command-trace"></a>`command_trace` | str | yes | Harness workspace path of the structured command-trace log emitted during the run. |

<a id="harnessrunresultjson"></a>
### HarnessRunResultJson

Machine-readable JSON payload for one harness run or rerun.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-harness-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-run-result-json.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessrunresultjson-workspace"></a>`workspace` | str | yes | Filesystem path of the harness workspace directory for the related run. |
| <a id="harnessrunresultjson-inspectable-paths"></a>`inspectable_paths` | [HarnessInspectablePaths](#harnessinspectablepaths) | yes | Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state. |
| <a id="harnessrunresultjson-selected-job-ids"></a>`selected_job_ids` | list[str] | no | Harness job ids selected for execution in the reported run. |
| <a id="harnessrunresultjson-failed-job-ids"></a>`failed_job_ids` | list[str] | no | Harness job ids that finished with a failure outcome in the reported run. |
| <a id="harnessrunresultjson-blocked-job-ids"></a>`blocked_job_ids` | list[str] | no | Harness job ids that were not run because an upstream dependency failed or was blocked. |
| <a id="harnessrunresultjson-job-statuses"></a>`job_statuses` | dict[str, [HarnessJobStatus](#harnessjobstatus)] | no | Final per-job status map emitted by the harness for the reported workflow or sequence run. |

<a id="harnessscenario"></a>
### HarnessScenario

A runner-agnostic integration-test scenario.

- category: `authored`
- ownership: `consumer-owned`
- schema file: [`buildish-release-tooling-harness-scenario.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-scenario.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: `harness/scenarios/*.yaml`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessscenario-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="harnessscenario-backend"></a>`backend` | [HarnessBackendName](#harnessbackendname) | no | Execution backend name that performed the related Buildish action or reproducibility run. |
| <a id="harnessscenario-env-capture"></a>`env_capture` | list[str] | no | Environment variable names that the harness shim should retain in trace output. |
| <a id="harnessscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="harnessscenario-secrets"></a>`secrets` | dict[str, str] | no | Secret environment variables that the harness should expose to the scenario while keeping them logically separate from ordinary environment variables. |
| <a id="harnessscenario-workspace-files"></a>`workspace_files` | list[[WorkspaceFile](#workspacefile)] | no | Files that the harness should create directly in the scenario workspace before execution begins. |
| <a id="harnessscenario-git-repositories"></a>`git_repositories` | list[[GitRepositoryFixture](#gitrepositoryfixture)] | no | Disposable Git repositories that the harness should create in the scenario workspace before execution begins. |
| <a id="harnessscenario-tool-behaviors"></a>`tool_behaviors` | dict[str, list[[ToolBehavior](#toolbehavior)]] | no | Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state. |
| <a id="harnessscenario-jobs"></a>`jobs` | list[[JobScenario](#jobscenario)] | no | Jobs that the harness should execute for the related custom scenario. |
| <a id="harnessscenario-workflow"></a>`workflow` | [WorkflowScenario](#workflowscenario) | no | Nested workflow block for an `act` harness scenario, or the workflow name recorded in provenance. |

<a id="harnesssequenceentryjson"></a>
### HarnessSequenceEntryJson

One sequence-run entry returned by the harness CLI.

- category: `runtime`
- ownership: `runtime-derived`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesssequenceentryjson-scenario"></a>`scenario` | str | yes | Scenario name associated with the related harness sequence result entry. |
| <a id="harnesssequenceentryjson-workspace"></a>`workspace` | str | yes | Filesystem path of the harness workspace directory for the related run. |
| <a id="harnesssequenceentryjson-inspectable-paths"></a>`inspectable_paths` | [HarnessInspectablePaths](#harnessinspectablepaths) | yes | Paths that a harness caller can inspect after the run to understand rewritten workflows, summaries, and persisted state. |
| <a id="harnesssequenceentryjson-selected-job-ids"></a>`selected_job_ids` | list[str] | no | Harness job ids selected for execution in the reported run. |
| <a id="harnesssequenceentryjson-failed-job-ids"></a>`failed_job_ids` | list[str] | no | Harness job ids that finished with a failure outcome in the reported run. |
| <a id="harnesssequenceentryjson-blocked-job-ids"></a>`blocked_job_ids` | list[str] | no | Harness job ids that were not run because an upstream dependency failed or was blocked. |
| <a id="harnesssequenceentryjson-job-statuses"></a>`job_statuses` | dict[str, [HarnessJobStatus](#harnessjobstatus)] | no | Final per-job status map emitted by the harness for the reported workflow or sequence run. |

<a id="harnesssequencerunresultjson"></a>
### HarnessSequenceRunResultJson

Machine-readable JSON payload for one harness sequence run.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-harness-sequence-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-sequence-run-result-json.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnesssequencerunresultjson-sequence"></a>`sequence` | list[[HarnessSequenceEntryJson](#harnesssequenceentryjson)] | no | Ordered per-scenario results retained for one multi-scenario harness sequence run. |
| <a id="harnesssequencerunresultjson-final-workspace"></a>`final_workspace` | str | yes | Filesystem path of the final harness workspace retained after a multi-scenario sequence run. |

<a id="harnessshimstate"></a>
### HarnessShimState

Persisted subprocess-facing harness shim state.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-harness-shim-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-shim-state.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessshimstate-workspace-root"></a>`workspace_root` | str | yes | Filesystem path of the harness workspace root used by the persisted shim state. |
| <a id="harnessshimstate-trace-file"></a>`trace_file` | str | yes | Filesystem path where the harness shim appends structured command trace entries. |
| <a id="harnessshimstate-env-capture"></a>`env_capture` | list[str] | no | Environment variable names that the harness shim should retain in trace output. |
| <a id="harnessshimstate-tool-behaviors"></a>`tool_behaviors` | dict[str, list[[ToolBehavior](#toolbehavior)]] | no | Scripted intercepted-tool behaviors keyed by tool name in the related harness scenario or runtime state. |
| <a id="harnessshimstate-counts"></a>`counts` | dict[str, int] | no | Per-tool or per-key invocation counts retained in harness runtime state. |
| <a id="harnessshimstate-gh-tag-objects"></a>`gh_tag_objects` | dict[str, [HarnessBuiltinGhTagObject](#harnessbuiltinghtagobject)] | no | Synthetic GitHub annotated-tag payloads persisted in harness shim state for later ref mutation handling. |

<a id="invocationmatch"></a>
### InvocationMatch

A matcher for a single intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="invocationmatch-argv"></a>`argv` | list[str] | no | Exact argv list that the harness should match or that it recorded for the related command invocation. |
| <a id="invocationmatch-argv-prefix"></a>`argv_prefix` | list[str] | no | Command-line prefix that the intercepted argv list must start with before the harness behavior matches. |
| <a id="invocationmatch-argv-contains"></a>`argv_contains` | list[str] | no | Command-line fragments that must appear somewhere in the intercepted argv list before the harness behavior matches. |
| <a id="invocationmatch-cwd"></a>`cwd` | str | no | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="invocationmatch-env-contains"></a>`env_contains` | dict[str, str] | no | Subset of required environment entries that a harness tool matcher must observe. |

<a id="jobscenario"></a>
### JobScenario

A job in the harness scenario.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="jobscenario-id"></a>`id` | str | yes | Stable identifier for the related harness job, step, or scenario element. |
| <a id="jobscenario-needs"></a>`needs` | list[str] | no | Job ids that must complete successfully before the related harness job is allowed to run. |
| <a id="jobscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="jobscenario-steps"></a>`steps` | list[[StepScenario](#stepscenario)] | yes | Ordered shell steps that the harness should run for the related custom job. |

<a id="stepscenario"></a>
### StepScenario

A single shell step in a harness job.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="stepscenario-id"></a>`id` | str | yes | Stable identifier for the related harness job, step, or scenario element. |
| <a id="stepscenario-run"></a>`run` | str | yes | Shell command body that the harness should execute for the related step. |
| <a id="stepscenario-cwd"></a>`cwd` | str | no | Working directory that the harness should use or that it observed for the related command invocation. |
| <a id="stepscenario-env"></a>`env` | dict[str, str] | no | Environment-variable mapping supplied to the related build, scenario, or command step. |
| <a id="stepscenario-shell"></a>`shell` | str | no | Shell executable name or mode that the harness should use for the related step. |

<a id="svnrepositoryfixture"></a>
### SvnRepositoryFixture

Initial ASF SVN state to create inside one harness `act` workspace.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="svnrepositoryfixture-initial-state"></a>`initial_state` | [SvnInitialState](#svninitialstate) | no | Named SVN fixture preset that describes what ASF dist state the harness should create before the run begins. |
| <a id="svnrepositoryfixture-version"></a>`version` | str | no | Release version string without a leading `v` prefix. |
| <a id="svnrepositoryfixture-rc-number"></a>`rc_number` | int | no | Numeric RC sequence selected for the related version. |
| <a id="svnrepositoryfixture-other-version"></a>`other_version` | str | no | Additional release version that the SVN harness fixture should materialize for preset scenarios that require another version line. |
| <a id="svnrepositoryfixture-dev-dist-entries"></a>`dev_dist_entries` | list[str] | no | Initial SVN entries that the harness should create under the simulated ASF `dist/dev` tree. |
| <a id="svnrepositoryfixture-release-dist-entries"></a>`release_dist_entries` | list[str] | no | Initial SVN entries that the harness should create under the simulated ASF `dist/release` tree. |
| <a id="svnrepositoryfixture-repository-files"></a>`repository_files` | list[[WorkspaceFile](#workspacefile)] | no | Files that the harness should create inside the simulated SVN repository fixture before execution begins. |

<a id="toolbehavior"></a>
### ToolBehavior

A scripted behavior for an intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="toolbehavior-match"></a>`match` | [InvocationMatch](#invocationmatch) | no | Tool-invocation matcher that decides when the related scripted harness behavior should be applied. |
| <a id="toolbehavior-result"></a>`result` | [ToolBehaviorResult](#toolbehaviorresult) | no | Scripted harness tool result that should be returned when the matching invocation is observed. |
| <a id="toolbehavior-times"></a>`times` | int | no | Maximum number of times that the harness should apply the scripted tool behavior before it stops matching. |

<a id="toolbehaviorresult"></a>
### ToolBehaviorResult

The mocked result of an intercepted tool invocation.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="toolbehaviorresult-exit-code"></a>`exit_code` | int | no | Process exit code that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-stdout"></a>`stdout` | str | no | Captured stdout that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-stderr"></a>`stderr` | str | no | Captured stderr that the harness recorded or should synthesize for the related tool invocation. |
| <a id="toolbehaviorresult-summary"></a>`summary` | str | no | Human-readable short summary for the related result or mocked tool behavior. |
| <a id="toolbehaviorresult-append-stdout-to-summary"></a>`append_stdout_to_summary` | bool | no | Whether the harness should append mocked stdout to the rendered step or job summary output. |
| <a id="toolbehaviorresult-delegate-to-real-tool"></a>`delegate_to_real_tool` | bool | no | Whether the harness should fall through to the real external tool instead of returning the mocked result directly. |
| <a id="toolbehaviorresult-writes"></a>`writes` | list[[FileWriteAction](#filewriteaction)] | no | Files that the mocked tool behavior should write when the invocation matches. |

<a id="workflowrepositorybranchfixture"></a>
### WorkflowRepositoryBranchFixture

A branch that should exist in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositorybranchfixture-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="workflowrepositorybranchfixture-start-point"></a>`start_point` | str | no | Commit, ref, or symbolic start point that the harness should use when creating the related branch or tag. |

<a id="workflowrepositoryfixture"></a>
### WorkflowRepositoryFixture

Git refs that should be created in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositoryfixture-branches"></a>`branches` | list[[WorkflowRepositoryBranchFixture](#workflowrepositorybranchfixture)] | no | Git branches that the harness should create in the workflow repository fixture before execution begins. |
| <a id="workflowrepositoryfixture-tags"></a>`tags` | list[[WorkflowRepositoryTagFixture](#workflowrepositorytagfixture)] | no | Git tags that the harness should create in the workflow repository fixture before execution begins. |

<a id="workflowrepositorytagfixture"></a>
### WorkflowRepositoryTagFixture

A tag that should exist in the workflow repository checkout before execution.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowrepositorytagfixture-name"></a>`name` | str | yes | Stable name for the related object, branch, tag, release, or harness step. |
| <a id="workflowrepositorytagfixture-target"></a>`target` | str | no | Target commit, ref, or identifier that the related fixture or release record should point at. |
| <a id="workflowrepositorytagfixture-annotated"></a>`annotated` | bool | no | Whether the related Git tag fixture should be created as an annotated tag instead of a lightweight tag. |
| <a id="workflowrepositorytagfixture-message"></a>`message` | str | no | Human-readable message body associated with the related verification failure, harness tag object, or fixture definition. |

<a id="workflowscenario"></a>
### WorkflowScenario

A real workflow-YAML invocation executed by the `act` backend.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workflowscenario-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="workflowscenario-event"></a>`event` | Literal['workflow_dispatch'] | no | Workflow event name that the harness should simulate for the related workflow scenario. |
| <a id="workflowscenario-inputs"></a>`inputs` | dict[str, str] | no | Workflow-dispatch inputs that the harness should pass to the selected workflow invocation. |
| <a id="workflowscenario-harness-config"></a>`harness_config` | str | yes | Path to the harness configuration file that the `act` workflow scenario should load. |
| <a id="workflowscenario-real-cli-commands"></a>`real_cli_commands` | list[str] | no | External CLI command names that the `act` harness workflow may run directly instead of through shim wrappers. |
| <a id="workflowscenario-repository-fixture"></a>`repository_fixture` | [WorkflowRepositoryFixture](#workflowrepositoryfixture) | no | Workflow-repository ref fixture that the harness should materialize before running the selected workflow. |
| <a id="workflowscenario-gpg-fixture"></a>`gpg_fixture` | [GpgFixtureMode](#gpgfixturemode) | no | GPG fixture mode that the harness should prepare for the related workflow scenario. |
| <a id="workflowscenario-svn-fixture"></a>`svn_fixture` | [SvnRepositoryFixture](#svnrepositoryfixture) | no | SVN fixture preset that the `act` workflow scenario should create before execution begins. |

<a id="workspacefile"></a>
### WorkspaceFile

A file that should exist in the scenario workspace before job execution starts.

- category: `authored`
- ownership: `consumer-owned`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="workspacefile-path"></a>`path` | str | yes | Filesystem path, relative artifact path, or retained evidence path associated with the related record. |
| <a id="workspacefile-content"></a>`content` | str | yes | Literal file content that the harness should write or that the mocked tool should emit. |
| <a id="workspacefile-executable"></a>`executable` | bool | no | Whether the written file should have the executable bit set in the harness workspace. |

## Harness shim builtin payload types

Small runtime payloads used by the harness shim to emulate GitHub and other tools.

<a id="harnessbuiltinghrefmutationpayload"></a>
### HarnessBuiltinGhRefMutationPayload

Synthetic GitHub tag-ref mutation payload consumed by the harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghrefmutationpayload-ref"></a>`ref` | str | no | Git ref name observed or created during the related operation. |
| <a id="harnessbuiltinghrefmutationpayload-sha"></a>`sha` | str | no | Git object SHA associated with one synthetic harness GitHub ref mutation payload. |

