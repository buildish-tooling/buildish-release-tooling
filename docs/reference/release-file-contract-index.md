---
title: "Release file contract index"
description: "Generated contract-file tables for supported and internal Buildish Release Tooling schemas."
---

<!--
Copyright 2026 The Buildish Authors

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

This page groups the published JSON Schemas by file contract and contract posture.

Back to the [reference overview](../release-model-schema-reference/).

## File contract groups

### Supported authored file contracts

Consumer-authored or component-authored file contracts that are part of the supported external release-tooling surface.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `release-config.yaml` | [ReleaseConfig](../release-config-reference/#releaseconfig) | [`component-config.schema.json`](/components/release-tooling/schemas/component-config.schema.json) | `supported` | `stable` | Component-authored `release-config.yaml` contract for release policy and target integration settings. |

### Supported emitted file contracts

Stable emitted Buildish file contracts that workflows or humans may intentionally consume.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `inspection-bundle.json` | [InspectionBundleManifestV1](../release-manifests-and-verification-reference/#inspectionbundlemanifestv1) | [`inspection-bundle-manifest-v1.schema.json`](/components/release-tooling/schemas/inspection-bundle-manifest-v1.schema.json) | `supported` | `stable` | Top-level manifest for a retained verify-rc inspection bundle. |

### Supported emitted non-file root contracts

Supported emitted JSON contract roots that do not correspond to one fixed checked-in path.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [CandidateManifestV1](../release-config-reference/#candidatemanifestv1) | [`candidate-manifest-v1.schema.json`](/components/release-tooling/schemas/candidate-manifest-v1.schema.json) | `supported` | `stable` | Stable Buildish manifest for one exact release candidate. |
| [InspectReproReportV1](../release-manifests-and-verification-reference/#inspectreproreportv1) | [`inspect-repro-report-v1.schema.json`](/components/release-tooling/schemas/inspect-repro-report-v1.schema.json) | `supported` | `stable` | Machine-readable `inspect-repro --json` output contract. |
| [PublishGitHubFinalReleaseResult](../release-config-reference/#publishgithubfinalreleaseresult) | [`publish-github-final-release-result.schema.json`](/components/release-tooling/schemas/publish-github-final-release-result.schema.json) | `supported` | `stable` | Stable publication result for a direct GitHub final release. |
| [ReadGitHubFinalReleaseResult](../release-config-reference/#readgithubfinalreleaseresult) | [`read-github-final-release-result.schema.json`](/components/release-tooling/schemas/read-github-final-release-result.schema.json) | `supported` | `stable` | Stable exact observation of a direct GitHub final release. |
| [ReleaseManifestV1](../release-config-reference/#releasemanifestv1) | [`release-manifest-v1.schema.json`](/components/release-tooling/schemas/release-manifest-v1.schema.json) | `supported` | `stable` | Stable Buildish manifest for one final direct or promoted release. |
| [StageGitHubFinalReleaseResult](../release-config-reference/#stagegithubfinalreleaseresult) | [`stage-github-final-release-result.schema.json`](/components/release-tooling/schemas/stage-github-final-release-result.schema.json) | `supported` | `stable` | Stable result of staging a direct GitHub final release. |
| [VerifyGitHubFinalReleaseResult](../release-config-reference/#verifygithubfinalreleaseresult) | [`verify-github-final-release-result.schema.json`](/components/release-tooling/schemas/verify-github-final-release-result.schema.json) | `supported` | `stable` | Stable verification result for a direct GitHub final release. |
| [VerifyRcReportV1](../release-manifests-and-verification-reference/#verifyrcreportv1) | [`verify-rc-report-v1.schema.json`](/components/release-tooling/schemas/verify-rc-report-v1.schema.json) | `supported` | `stable` | Machine-readable `verify-rc` report contract, typically written through `--report-json`. |
| [VotePackageV1](../release-config-reference/#votepackagev1) | [`vote-package-v1.schema.json`](/components/release-tooling/schemas/vote-package-v1.schema.json) | `supported` | `stable` | Stable optional vote package bound to one candidate manifest digest. |

### Internal stable file contracts

Buildish-owned internal file contracts that are documented here for maintainability but are not part of the supported external API.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `harness/scenarios/*.yaml` | [HarnessScenario](../release-harness-runtime-reference/#harnessscenario) | [`harness-scenario.schema.json`](/components/release-tooling/schemas/harness-scenario.schema.json) | `internal` | `stable` | Harness scenario contract for synthetic or `act`-backed release-workflow integration tests. |
| `harness/release-harness.yaml` | [ReleaseHarnessConfig](../release-harness-config-reference/#releaseharnessconfig) | [`release-harness-config.schema.json`](/components/release-tooling/schemas/release-harness-config.schema.json) | `internal` | `stable` | Committed harness configuration contract for local repository bindings and optional overrides. |
| `artifact-manifest.json` | [SecondaryArtifactManifestV1](../release-manifests-and-verification-reference/#secondaryartifactmanifestv1) | [`secondary-artifact-manifest-v1.schema.json`](/components/release-tooling/schemas/secondary-artifact-manifest-v1.schema.json) | `internal` | `stable` | Typed secondary-artifact registration manifest fragment written by `record-artifact`. |

### Internal stable non-file root contracts

Buildish-owned internal root contracts and runtime payloads with stable current semantics but no external support promise.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AsfKeysTrustRootRead](../release-manifests-and-verification-reference/#asfkeystrustrootread) | [`asf-keys-trust-root-read.schema.json`](/components/release-tooling/schemas/asf-keys-trust-root-read.schema.json) | `internal` | `stable` | Tolerant read model for ASF KEYS trust-root references carried through vote-materials loading. |
| [AuthoritativeManifestReferenceRead](../release-manifests-and-verification-reference/#authoritativemanifestreferenceread) | [`authoritative-manifest-reference-read.schema.json`](/components/release-tooling/schemas/authoritative-manifest-reference-read.schema.json) | `internal` | `stable` | Tolerant read model for the authoritative signed manifest reference used by vote-materials loading. |
| [CandidateReleaseState](../release-config-reference/#candidatereleasestate) | [`candidate-release-state.schema.json`](/components/release-tooling/schemas/candidate-release-state.schema.json) | `internal` | `stable` | Resolved provider-neutral state for one exact release candidate. |
| [CommandContext](../release-config-reference/#commandcontext) | [`command-context.schema.json`](/components/release-tooling/schemas/command-context.schema.json) | `internal` | `stable` | Runtime command context built from validated release configuration. |
| [DirectReleaseState](../release-config-reference/#directreleasestate) | [`direct-release-state.schema.json`](/components/release-tooling/schemas/direct-release-state.schema.json) | `internal` | `stable` | Resolved provider-neutral state for one direct release. |
| [DraftGitHubReleaseRead](../release-manifests-and-verification-reference/#draftgithubreleaseread) | [`draft-github-release-read.schema.json`](/components/release-tooling/schemas/draft-github-release-read.schema.json) | `internal` | `stable` | Tolerant read model for draft GitHub release coordinates recorded in vote materials. |
| [FileLikeReproducibilityMetadata](../release-manifests-and-verification-reference/#filelikereproducibilitymetadata) | [`file-like-reproducibility-metadata.schema.json`](/components/release-tooling/schemas/file-like-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for file-like reproducibility comparisons. |
| [HarnessBuiltinGhRefMutationPayload](../release-harness-shim-reference/#harnessbuiltinghrefmutationpayload) | [`harness-builtin-gh-ref-mutation-payload.schema.json`](/components/release-tooling/schemas/harness-builtin-gh-ref-mutation-payload.schema.json) | `internal` | `stable` | Harness shim builtin payload describing a synthetic GitHub ref mutation request. |
| [HarnessCommandTraceEntry](../release-harness-runtime-reference/#harnesscommandtraceentry) | [`harness-command-trace-entry.schema.json`](/components/release-tooling/schemas/harness-command-trace-entry.schema.json) | `internal` | `stable` | Structured command-trace record emitted by the harness shim for one intercepted invocation. |
| [HarnessRunResultJson](../release-harness-runtime-reference/#harnessrunresultjson) | [`harness-run-result-json.schema.json`](/components/release-tooling/schemas/harness-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for one harness scenario run. |
| [HarnessSequenceRunResultJson](../release-harness-runtime-reference/#harnesssequencerunresultjson) | [`harness-sequence-run-result-json.schema.json`](/components/release-tooling/schemas/harness-sequence-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for a multi-scenario harness sequence run. |
| [HarnessShimState](../release-harness-runtime-reference/#harnessshimstate) | [`harness-shim-state.schema.json`](/components/release-tooling/schemas/harness-shim-state.schema.json) | `internal` | `stable` | Persisted subprocess-facing harness shim state used by intercepted tool wrappers. |
| [MavenRepositoryInventoryV1](../release-manifests-and-verification-reference/#mavenrepositoryinventoryv1) | [`maven-repository-inventory-v1.schema.json`](/components/release-tooling/schemas/maven-repository-inventory-v1.schema.json) | `internal` | `stable` | Signed Maven repository inventory contract emitted for staged Maven repository verification. |
| [MavenRepositoryPathResultReport](../release-manifests-and-verification-reference/#mavenrepositorypathresultreport) | [`maven-repository-path-result-report.schema.json`](/components/release-tooling/schemas/maven-repository-path-result-report.schema.json) | `internal` | `stable` | Per-path Maven repository reproducibility comparison result retained in bundle metadata. |
| [MavenRepositoryPathRuleReport](../release-manifests-and-verification-reference/#mavenrepositorypathrulereport) | [`maven-repository-path-rule-report.schema.json`](/components/release-tooling/schemas/maven-repository-path-rule-report.schema.json) | `internal` | `stable` | Rendered Maven repository per-path comparison rule retained in reproducibility metadata. |
| [MavenRepositoryReproducibilityMetadata](../release-manifests-and-verification-reference/#mavenrepositoryreproducibilitymetadata) | [`maven-repository-reproducibility-metadata.schema.json`](/components/release-tooling/schemas/maven-repository-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for Maven repository reproducibility evidence. |
| [OciImageReproducibilityMetadata](../release-manifests-and-verification-reference/#ociimagereproducibilitymetadata) | [`oci-image-reproducibility-metadata.schema.json`](/components/release-tooling/schemas/oci-image-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for OCI image reproducibility evidence. |
| [PromotionState](../release-config-reference/#promotionstate) | [`promotion-state.schema.json`](/components/release-tooling/schemas/promotion-state.schema.json) | `internal` | `stable` | Resolved provider-neutral state for exact candidate promotion. |
| [RebuiltOutputSnapshot](../release-manifests-and-verification-reference/#rebuiltoutputsnapshot) | [`rebuilt-output-snapshot.schema.json`](/components/release-tooling/schemas/rebuilt-output-snapshot.schema.json) | `internal` | `stable` | Snapshot of one rebuilt output retained in reproducibility metadata. |
| [ResolvedReleaseHarnessConfigJson](../release-harness-config-reference/#resolvedreleaseharnessconfigjson) | [`resolved-release-harness-config-json.schema.json`](/components/release-tooling/schemas/resolved-release-harness-config-json.schema.json) | `internal` | `stable` | Machine-readable JSON payload for one resolved harness configuration. |
| [RetainedArtifactSnapshot](../release-manifests-and-verification-reference/#retainedartifactsnapshot) | [`retained-artifact-snapshot.schema.json`](/components/release-tooling/schemas/retained-artifact-snapshot.schema.json) | `internal` | `stable` | Snapshot of one retained staged or rebuilt artifact captured in reproducibility metadata. |
| [SecondaryArtifactBase](../release-manifests-and-verification-reference/#secondaryartifactbase) | [`secondary-artifact-base.schema.json`](/components/release-tooling/schemas/secondary-artifact-base.schema.json) | `internal` | `stable` | Common base shape shared across supported secondary-artifact manifest entries. |
| [SourceArtifactReproducibilityMetadata](../release-manifests-and-verification-reference/#sourceartifactreproducibilitymetadata) | [`source-artifact-reproducibility-metadata.schema.json`](/components/release-tooling/schemas/source-artifact-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for source-artifact reproducibility evidence. |
| [VerifyRcOverrideFileConfig](../release-config-reference/#verifyrcoverridefileconfig) | [`verify-rc-override-file-config.schema.json`](/components/release-tooling/schemas/verify-rc-override-file-config.schema.json) | `internal` | `stable` | Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`. |

### Internal unstable command action manifests

Internal workflow-coordination manifests written by commands. These are documented to aid maintenance and debugging, but they are intentionally unstable.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AttachGitHubReleaseAssetsManifest](../release-command-manifests-reference/#attachgithubreleaseassetsmanifest) | [`attach-github-release-assets-manifest.schema.json`](/components/release-tooling/schemas/attach-github-release-assets-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `attach-github-release-assets`. |
| [BuildSourceRcManifest](../release-command-manifests-reference/#buildsourcercmanifest) | [`build-source-rc-manifest.schema.json`](/components/release-tooling/schemas/build-source-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `build-source-rc`. |
| [CleanupDevSvnRcsManifest](../release-command-manifests-reference/#cleanupdevsvnrcsmanifest) | [`cleanup-dev-svn-rcs-manifest.schema.json`](/components/release-tooling/schemas/cleanup-dev-svn-rcs-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `cleanup-dev-svn-rcs`. |
| [CommandActionManifest](../release-command-manifests-reference/#commandactionmanifest) | [`command-action-manifest.schema.json`](/components/release-tooling/schemas/command-action-manifest.schema.json) | `internal` | `unstable` | Common top-level shape for internal unstable command action manifests written through `MANIFEST_PATH`. |
| [CreateFinalTagManifest](../release-command-manifests-reference/#createfinaltagmanifest) | [`create-final-tag-manifest.schema.json`](/components/release-tooling/schemas/create-final-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-final-tag`. |
| [CreateRcMaterializationTagManifest](../release-command-manifests-reference/#creatercmaterializationtagmanifest) | [`create-rc-materialization-tag-manifest.schema.json`](/components/release-tooling/schemas/create-rc-materialization-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-rc-materialization-tag`. |
| [CreateReleaseBranchManifest](../release-command-manifests-reference/#createreleasebranchmanifest) | [`create-release-branch-manifest.schema.json`](/components/release-tooling/schemas/create-release-branch-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-release-branch`. |
| [CreateSourceArtifactManifest](../release-command-manifests-reference/#createsourceartifactmanifest) | [`create-source-artifact-manifest.schema.json`](/components/release-tooling/schemas/create-source-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-source-artifact`. |
| [FinalizeDraftGitHubReleaseManifest](../release-command-manifests-reference/#finalizedraftgithubreleasemanifest) | [`finalize-draft-github-release-manifest.schema.json`](/components/release-tooling/schemas/finalize-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-draft-github-release`. |
| [FinalizeRcVoteMaterialsManifest](../release-command-manifests-reference/#finalizercvotematerialsmanifest) | [`finalize-rc-vote-materials-manifest.schema.json`](/components/release-tooling/schemas/finalize-rc-vote-materials-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-rc-vote-materials`. |
| [MaterializeRcGitContentManifest](../release-command-manifests-reference/#materializercgitcontentmanifest) | [`materialize-rc-git-content-manifest.schema.json`](/components/release-tooling/schemas/materialize-rc-git-content-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `materialize-rc-git-content`. |
| [PrepareRcManifest](../release-command-manifests-reference/#preparercmanifest) | [`prepare-rc-manifest.schema.json`](/components/release-tooling/schemas/prepare-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prepare-rc`. |
| [PruneOlderLineReleasesManifest](../release-command-manifests-reference/#pruneolderlinereleasesmanifest) | [`prune-older-line-releases-manifest.schema.json`](/components/release-tooling/schemas/prune-older-line-releases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prune-older-line-releases`. |
| [PublishAtrCandidateManifest](../release-command-manifests-reference/#publishatrcandidatemanifest) | [`publish-atr-candidate-manifest.schema.json`](/components/release-tooling/schemas/publish-atr-candidate-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-atr-candidate`. |
| [PublishDockerhubMovingTagsManifest](../release-command-manifests-reference/#publishdockerhubmovingtagsmanifest) | [`publish-dockerhub-moving-tags-manifest.schema.json`](/components/release-tooling/schemas/publish-dockerhub-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-dockerhub-moving-tags`. |
| [PublishSourceReleaseSvnManifest](../release-command-manifests-reference/#publishsourcereleasesvnmanifest) | [`publish-source-release-svn-manifest.schema.json`](/components/release-tooling/schemas/publish-source-release-svn-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-source-release-svn`. |
| [RecordArtifactManifest](../release-command-manifests-reference/#recordartifactmanifest) | [`record-artifact-manifest.schema.json`](/components/release-tooling/schemas/record-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `record-artifact`. |
| [ReleaseVersionManifest](../release-command-manifests-reference/#releaseversionmanifest) | [`release-version-manifest.schema.json`](/components/release-tooling/schemas/release-version-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `release-version`. |
| [ReportAtrChecksManifest](../release-command-manifests-reference/#reportatrchecksmanifest) | [`report-atr-checks-manifest.schema.json`](/components/release-tooling/schemas/report-atr-checks-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `report-atr-checks`. |
| [SyncDraftGitHubReleaseManifest](../release-command-manifests-reference/#syncdraftgithubreleasemanifest) | [`sync-draft-github-release-manifest.schema.json`](/components/release-tooling/schemas/sync-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `sync-draft-github-release`. |
| [UpdateMovingImageAliasesManifest](../release-command-manifests-reference/#updatemovingimagealiasesmanifest) | [`update-moving-image-aliases-manifest.schema.json`](/components/release-tooling/schemas/update-moving-image-aliases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-image-aliases`. |
| [UpdateMovingTagsManifest](../release-command-manifests-reference/#updatemovingtagsmanifest) | [`update-moving-tags-manifest.schema.json`](/components/release-tooling/schemas/update-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-tags`. |

