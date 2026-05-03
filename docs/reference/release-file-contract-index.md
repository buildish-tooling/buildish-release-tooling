---
title: "Release file contract index"
description: "Generated contract-file tables for supported and internal Buildish Release Tooling schemas."
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

This page groups the published JSON Schemas by file contract and contract posture.

Back to the [reference overview](../release-model-schema-reference/).

## File contract groups

### Supported authored file contracts

Consumer-authored or component-authored file contracts that are part of the supported external release-tooling surface.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `release-config.yaml` | [ComponentConfig](../release-config-reference/#componentconfig) | [`buildish-release-tooling-component-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-component-config.schema.json) | `supported` | `stable` | Component-authored `release-config.yaml` contract for release policy and target integration settings. |

### Supported emitted file contracts

Stable emitted Buildish file contracts that workflows or humans may intentionally consume.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `inspection-bundle.json` | [InspectionBundleManifestV1](../release-manifests-and-verification-reference/#inspectionbundlemanifestv1) | [`buildish-release-tooling-inspection-bundle-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspection-bundle-manifest-v1.schema.json) | `supported` | `stable` | Top-level manifest for a retained verify-rc inspection bundle. |
| `rc-vote-manifest.json` | [RcVoteManifestV1](../release-manifests-and-verification-reference/#rcvotemanifestv1) | [`buildish-release-tooling-rc-vote-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rc-vote-manifest-v1.schema.json) | `supported` | `stable` | Signed RC vote manifest that declares the source artifact, trust roots, and secondary artifacts that verifiers must inspect. |

### Supported emitted non-file root contracts

Supported emitted JSON contract roots that do not correspond to one fixed checked-in path.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [InspectReproReportV1](../release-manifests-and-verification-reference/#inspectreproreportv1) | [`buildish-release-tooling-inspect-repro-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-inspect-repro-report-v1.schema.json) | `supported` | `stable` | Machine-readable `inspect-repro --json` output contract. |
| [VerifyRcReportV1](../release-manifests-and-verification-reference/#verifyrcreportv1) | [`buildish-release-tooling-verify-rc-report-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-report-v1.schema.json) | `supported` | `stable` | Machine-readable `verify-rc` report contract, typically written through `--report-json`. |

### Internal stable file contracts

Buildish-owned internal file contracts that are documented here for maintainability but are not part of the supported external API.

| Contract file | Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- | --- |
| `harness/scenarios/*.yaml` | [HarnessScenario](../release-harness-runtime-reference/#harnessscenario) | [`buildish-release-tooling-harness-scenario.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-scenario.schema.json) | `internal` | `stable` | Harness scenario contract for synthetic or `act`-backed release-workflow integration tests. |
| `harness/release-harness.yaml` | [ReleaseHarnessConfig](../release-harness-config-reference/#releaseharnessconfig) | [`buildish-release-tooling-release-harness-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-harness-config.schema.json) | `internal` | `stable` | Committed harness configuration contract for local repository bindings and optional overrides. |
| `artifact-manifest.json` | [SecondaryArtifactManifestV1](../release-manifests-and-verification-reference/#secondaryartifactmanifestv1) | [`buildish-release-tooling-secondary-artifact-manifest-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-manifest-v1.schema.json) | `internal` | `stable` | Typed secondary-artifact registration manifest fragment written by `record-artifact`. |

### Internal stable non-file root contracts

Buildish-owned internal root contracts and runtime payloads with stable current semantics but no external support promise.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AsfKeysTrustRootRead](../release-manifests-and-verification-reference/#asfkeystrustrootread) | [`buildish-release-tooling-asf-keys-trust-root-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-asf-keys-trust-root-read.schema.json) | `internal` | `stable` | Tolerant read model for ASF KEYS trust-root references carried through vote-materials loading. |
| [AuthoritativeManifestReferenceRead](../release-manifests-and-verification-reference/#authoritativemanifestreferenceread) | [`buildish-release-tooling-authoritative-manifest-reference-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-authoritative-manifest-reference-read.schema.json) | `internal` | `stable` | Tolerant read model for the authoritative signed manifest reference used by vote-materials loading. |
| [CommandContext](../release-config-reference/#commandcontext) | [`buildish-release-tooling-command-context.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-context.schema.json) | `internal` | `stable` | Runtime command context built from CLI arguments and validated component configuration. |
| [DraftGithubReleaseRead](../release-manifests-and-verification-reference/#draftgithubreleaseread) | [`buildish-release-tooling-draft-github-release-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-draft-github-release-read.schema.json) | `internal` | `stable` | Tolerant read model for draft GitHub release coordinates recorded in vote materials. |
| [FileLikeReproducibilityMetadata](../release-manifests-and-verification-reference/#filelikereproducibilitymetadata) | [`buildish-release-tooling-file-like-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-file-like-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for file-like reproducibility comparisons. |
| [HarnessBuiltinGhRefMutationPayload](../release-harness-shim-reference/#harnessbuiltinghrefmutationpayload) | [`buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-builtin-gh-ref-mutation-payload.schema.json) | `internal` | `stable` | Harness shim builtin payload describing a synthetic GitHub ref mutation request. |
| [HarnessCommandTraceEntry](../release-harness-runtime-reference/#harnesscommandtraceentry) | [`buildish-release-tooling-harness-command-trace-entry.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-command-trace-entry.schema.json) | `internal` | `stable` | Structured command-trace record emitted by the harness shim for one intercepted invocation. |
| [HarnessRunResultJson](../release-harness-runtime-reference/#harnessrunresultjson) | [`buildish-release-tooling-harness-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for one harness scenario run. |
| [HarnessSequenceRunResultJson](../release-harness-runtime-reference/#harnesssequencerunresultjson) | [`buildish-release-tooling-harness-sequence-run-result-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-sequence-run-result-json.schema.json) | `internal` | `stable` | Machine-readable JSON result for a multi-scenario harness sequence run. |
| [HarnessShimState](../release-harness-runtime-reference/#harnessshimstate) | [`buildish-release-tooling-harness-shim-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-harness-shim-state.schema.json) | `internal` | `stable` | Persisted subprocess-facing harness shim state used by intercepted tool wrappers. |
| [MavenRepositoryInventoryV1](../release-manifests-and-verification-reference/#mavenrepositoryinventoryv1) | [`buildish-release-tooling-maven-repository-inventory-v1.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-inventory-v1.schema.json) | `internal` | `stable` | Signed Maven repository inventory contract emitted for staged Maven repository verification. |
| [MavenRepositoryPathResultReport](../release-manifests-and-verification-reference/#mavenrepositorypathresultreport) | [`buildish-release-tooling-maven-repository-path-result-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-result-report.schema.json) | `internal` | `stable` | Per-path Maven repository reproducibility comparison result retained in bundle metadata. |
| [MavenRepositoryPathRuleReport](../release-manifests-and-verification-reference/#mavenrepositorypathrulereport) | [`buildish-release-tooling-maven-repository-path-rule-report.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-path-rule-report.schema.json) | `internal` | `stable` | Rendered Maven repository per-path comparison rule retained in reproducibility metadata. |
| [MavenRepositoryReproducibilityMetadata](../release-manifests-and-verification-reference/#mavenrepositoryreproducibilitymetadata) | [`buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-maven-repository-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for Maven repository reproducibility evidence. |
| [OciImageReproducibilityMetadata](../release-manifests-and-verification-reference/#ociimagereproducibilitymetadata) | [`buildish-release-tooling-oci-image-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-oci-image-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for OCI image reproducibility evidence. |
| [PrepareRcState](../release-config-reference/#preparercstate) | [`buildish-release-tooling-prepare-rc-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-state.schema.json) | `internal` | `stable` | Resolved prepare-rc state persisted between release workflow steps. |
| [RebuiltOutputSnapshot](../release-manifests-and-verification-reference/#rebuiltoutputsnapshot) | [`buildish-release-tooling-rebuilt-output-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-rebuilt-output-snapshot.schema.json) | `internal` | `stable` | Snapshot of one rebuilt output retained in reproducibility metadata. |
| [ReleaseVersionState](../release-config-reference/#releaseversionstate) | [`buildish-release-tooling-release-version-state.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-state.schema.json) | `internal` | `stable` | Resolved release-version state persisted across final release workflow steps. |
| [ResolvedReleaseHarnessConfigJson](../release-harness-config-reference/#resolvedreleaseharnessconfigjson) | [`buildish-release-tooling-resolved-release-harness-config-json.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-resolved-release-harness-config-json.schema.json) | `internal` | `stable` | Machine-readable JSON payload for one resolved harness configuration. |
| [RetainedArtifactSnapshot](../release-manifests-and-verification-reference/#retainedartifactsnapshot) | [`buildish-release-tooling-retained-artifact-snapshot.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-retained-artifact-snapshot.schema.json) | `internal` | `stable` | Snapshot of one retained staged or rebuilt artifact captured in reproducibility metadata. |
| [SecondaryArtifactBase](../release-manifests-and-verification-reference/#secondaryartifactbase) | [`buildish-release-tooling-secondary-artifact-base.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-secondary-artifact-base.schema.json) | `internal` | `stable` | Common base shape shared across supported secondary-artifact manifest entries. |
| [SourceArtifactReproducibilityMetadata](../release-manifests-and-verification-reference/#sourceartifactreproducibilitymetadata) | [`buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-source-artifact-reproducibility-metadata.schema.json) | `internal` | `stable` | Inspection-bundle metadata payload for source-artifact reproducibility evidence. |
| [VerifyRcOverrideFileConfig](../release-config-reference/#verifyrcoverridefileconfig) | [`buildish-release-tooling-verify-rc-override-file-config.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-verify-rc-override-file-config.schema.json) | `internal` | `stable` | Local non-canonical verify-rc reproducibility override file passed through `--repro-override-file`. |
| [VoteMaterialsRead](../release-manifests-and-verification-reference/#votematerialsread) | [`buildish-release-tooling-vote-materials-read.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-read.schema.json) | `internal` | `stable` | Tolerant read model for vote materials consumed during verification and bootstrap workflows. |
| [VoteMaterialsStrict](../release-manifests-and-verification-reference/#votematerialsstrict) | [`buildish-release-tooling-vote-materials-strict.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-vote-materials-strict.schema.json) | `internal` | `stable` | Strict typed vote-materials bundle assembled by release-tooling before RC publication. |

### Internal unstable command action manifests

Internal workflow-coordination manifests written by commands. These are documented to aid maintenance and debugging, but they are intentionally unstable.

| Root type(s) | Schema file | Audience | Stability | Summary |
| --- | --- | --- | --- | --- |
| [AttachGithubReleaseAssetsManifest](../release-command-manifests-reference/#attachgithubreleaseassetsmanifest) | [`buildish-release-tooling-attach-github-release-assets-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-attach-github-release-assets-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `attach-github-release-assets`. |
| [BuildSourceRcManifest](../release-command-manifests-reference/#buildsourcercmanifest) | [`buildish-release-tooling-build-source-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-build-source-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `build-source-rc`. |
| [CleanupDevSvnRcsManifest](../release-command-manifests-reference/#cleanupdevsvnrcsmanifest) | [`buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-cleanup-dev-svn-rcs-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `cleanup-dev-svn-rcs`. |
| [CommandActionManifest](../release-command-manifests-reference/#commandactionmanifest) | [`buildish-release-tooling-command-action-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-command-action-manifest.schema.json) | `internal` | `unstable` | Common top-level shape for internal unstable command action manifests written through `MANIFEST_PATH`. |
| [CreateFinalTagManifest](../release-command-manifests-reference/#createfinaltagmanifest) | [`buildish-release-tooling-create-final-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-final-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-final-tag`. |
| [CreateRcMaterializationTagManifest](../release-command-manifests-reference/#creatercmaterializationtagmanifest) | [`buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-rc-materialization-tag-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-rc-materialization-tag`. |
| [CreateReleaseBranchManifest](../release-command-manifests-reference/#createreleasebranchmanifest) | [`buildish-release-tooling-create-release-branch-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-release-branch-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-release-branch`. |
| [CreateSourceArtifactManifest](../release-command-manifests-reference/#createsourceartifactmanifest) | [`buildish-release-tooling-create-source-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-create-source-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `create-source-artifact`. |
| [FinalizeDraftGithubReleaseManifest](../release-command-manifests-reference/#finalizedraftgithubreleasemanifest) | [`buildish-release-tooling-finalize-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-draft-github-release`. |
| [FinalizeRcVoteMaterialsManifest](../release-command-manifests-reference/#finalizercvotematerialsmanifest) | [`buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-finalize-rc-vote-materials-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `finalize-rc-vote-materials`. |
| [MaterializeRcGitContentManifest](../release-command-manifests-reference/#materializercgitcontentmanifest) | [`buildish-release-tooling-materialize-rc-git-content-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-materialize-rc-git-content-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `materialize-rc-git-content`. |
| [PrepareRcManifest](../release-command-manifests-reference/#preparercmanifest) | [`buildish-release-tooling-prepare-rc-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prepare-rc-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prepare-rc`. |
| [PruneOlderLineReleasesManifest](../release-command-manifests-reference/#pruneolderlinereleasesmanifest) | [`buildish-release-tooling-prune-older-line-releases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-prune-older-line-releases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `prune-older-line-releases`. |
| [PublishAtrCandidateManifest](../release-command-manifests-reference/#publishatrcandidatemanifest) | [`buildish-release-tooling-publish-atr-candidate-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-atr-candidate-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-atr-candidate`. |
| [PublishDockerhubMovingTagsManifest](../release-command-manifests-reference/#publishdockerhubmovingtagsmanifest) | [`buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-dockerhub-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-dockerhub-moving-tags`. |
| [PublishSourceReleaseSvnManifest](../release-command-manifests-reference/#publishsourcereleasesvnmanifest) | [`buildish-release-tooling-publish-source-release-svn-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-publish-source-release-svn-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `publish-source-release-svn`. |
| [RecordArtifactManifest](../release-command-manifests-reference/#recordartifactmanifest) | [`buildish-release-tooling-record-artifact-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-record-artifact-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `record-artifact`. |
| [ReleaseVersionManifest](../release-command-manifests-reference/#releaseversionmanifest) | [`buildish-release-tooling-release-version-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-release-version-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `release-version`. |
| [ReportAtrChecksManifest](../release-command-manifests-reference/#reportatrchecksmanifest) | [`buildish-release-tooling-report-atr-checks-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-report-atr-checks-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `report-atr-checks`. |
| [SyncDraftGithubReleaseManifest](../release-command-manifests-reference/#syncdraftgithubreleasemanifest) | [`buildish-release-tooling-sync-draft-github-release-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-sync-draft-github-release-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `sync-draft-github-release`. |
| [UpdateMovingImageAliasesManifest](../release-command-manifests-reference/#updatemovingimagealiasesmanifest) | [`buildish-release-tooling-update-moving-image-aliases-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-image-aliases-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-image-aliases`. |
| [UpdateMovingTagsManifest](../release-command-manifests-reference/#updatemovingtagsmanifest) | [`buildish-release-tooling-update-moving-tags-manifest.schema.json`](/components/buildish-release-tooling/schemas/buildish-release-tooling-update-moving-tags-manifest.schema.json) | `internal` | `unstable` | Internal unstable JSON action manifest emitted by `update-moving-tags`. |

