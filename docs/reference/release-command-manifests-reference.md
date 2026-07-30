---
title: "Internal unstable command action manifest types"
description: "Machine-readable command action manifests written for workflow coordination. These are Buildish-owned internal input/output contracts and are intentionally unstable."
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

Machine-readable command action manifests written for workflow coordination. These are Buildish-owned internal input/output contracts and are intentionally unstable.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

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

<a id="attachgithubreleaseassetsmanifest"></a>
### AttachGithubReleaseAssetsManifest

Action manifest emitted after uploading primary and derived assets to a GitHub release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`attach-github-release-assets-manifest.schema.json`](/components/release-tooling/schemas/attach-github-release-assets-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="attachgithubreleaseassetsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="attachgithubreleaseassetsmanifest-action"></a>`action` | Literal['attach-github-release-assets'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="attachgithubreleaseassetsmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="attachgithubreleaseassetsmanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="attachgithubreleaseassetsmanifest-release-id"></a>`release_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub release id associated with the related draft or final release record. |
| <a id="attachgithubreleaseassetsmanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="attachgithubreleaseassetsmanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="attachgithubreleaseassetsmanifest-release-url"></a>`release_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="attachgithubreleaseassetsmanifest-primary-asset-names"></a>`primary_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Primary release asset names that Buildish attached or expected to attach to the selected GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-uploaded-asset-names"></a>`uploaded_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | GitHub release asset names that Buildish uploaded during the related command. |
| <a id="attachgithubreleaseassetsmanifest-generated-checksum-asset-names"></a>`generated_checksum_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Generated checksum asset names that Buildish attached or expected to attach to the GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-generated-signature-asset-names"></a>`generated_signature_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Generated detached-signature asset names that Buildish attached or expected to attach to the GitHub release. |
| <a id="attachgithubreleaseassetsmanifest-checksum-algorithms"></a>`checksum_algorithms` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Checksum algorithms that Buildish generated or expects for the related artifact set. |
| <a id="attachgithubreleaseassetsmanifest-gpg-fingerprint"></a>`gpg_fingerprint` | str | yes | OpenPGP fingerprint of the signing key Buildish used or verified. |

<a id="buildsourcercmanifest"></a>
### BuildSourceRcManifest

Action manifest emitted after building and staging the signed source RC bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`build-source-rc-manifest.schema.json`](/components/release-tooling/schemas/build-source-rc-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="buildsourcercmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="buildsourcercmanifest-action"></a>`action` | Literal['build-source-rc'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="buildsourcercmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="buildsourcercmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="buildsourcercmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="buildsourcercmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="buildsourcercmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-path"></a>`source_artifact_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the locally produced or staged source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-sha512"></a>`source_artifact_sha512` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | SHA-512 digest of the staged or locally produced source release artifact. |
| <a id="buildsourcercmanifest-source-artifact-sha512-path"></a>`source_artifact_sha512_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the `.sha512` sidecar generated for the locally produced source artifact. |
| <a id="buildsourcercmanifest-source-artifact-asc-path"></a>`source_artifact_asc_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the detached OpenPGP signature file for the locally produced source artifact. |
| <a id="buildsourcercmanifest-staging-url"></a>`staging_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |

<a id="cleanupdevsvnrcsmanifest"></a>
### CleanupDevSvnRcsManifest

Action manifest emitted after old or conflicting RC staging directories are removed.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`cleanup-dev-svn-rcs-manifest.schema.json`](/components/release-tooling/schemas/cleanup-dev-svn-rcs-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="cleanupdevsvnrcsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="cleanupdevsvnrcsmanifest-action"></a>`action` | Literal['cleanup-dev-svn-rcs'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="cleanupdevsvnrcsmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="cleanupdevsvnrcsmanifest-dev-base-url"></a>`dev_base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Configured ASF `dist/dev` base URL that the cleanup or publication action targeted. |
| <a id="cleanupdevsvnrcsmanifest-deleted-rc-directories"></a>`deleted_rc_directories` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | ASF dev/dist RC directories that Buildish deleted during cleanup. |

<a id="commandactionmanifest"></a>
### CommandActionManifest

Common top-level shape for command action manifests.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`command-action-manifest.schema.json`](/components/release-tooling/schemas/command-action-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="commandactionmanifest-component"></a>`component` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="commandactionmanifest-action"></a>`action` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable command action identifier written by one Buildish command manifest. |

<a id="createfinaltagmanifest"></a>
### CreateFinalTagManifest

Action manifest emitted after creating or validating the final immutable release tag.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`create-final-tag-manifest.schema.json`](/components/release-tooling/schemas/create-final-tag-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createfinaltagmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createfinaltagmanifest-action"></a>`action` | Literal['create-final-tag'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createfinaltagmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="createfinaltagmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="createfinaltagmanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="createfinaltagmanifest-target-commit"></a>`target_commit` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="createfinaltagmanifest-tag-creation-mode"></a>`tag_creation_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Mode that Buildish used when creating or reusing the related annotated Git tag. |
| <a id="createfinaltagmanifest-created-ref"></a>`created_ref` | str | yes | Git ref name that Buildish created or reused while performing the related tag or ref action. |

<a id="creatercmaterializationtagmanifest"></a>
### CreateRcMaterializationTagManifest

Action manifest emitted after tagging one detached RC materialization commit.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`create-rc-materialization-tag-manifest.schema.json`](/components/release-tooling/schemas/create-rc-materialization-tag-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="creatercmaterializationtagmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="creatercmaterializationtagmanifest-action"></a>`action` | Literal['create-rc-materialization-tag'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="creatercmaterializationtagmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="creatercmaterializationtagmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="creatercmaterializationtagmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="creatercmaterializationtagmanifest-target-commit"></a>`target_commit` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="creatercmaterializationtagmanifest-tag-target-origin"></a>`tag_target_origin` | Literal['materialized-commit', 'source-commit'] | yes | Origin that Buildish used for the target commit when tagging the RC materialization result. |
| <a id="creatercmaterializationtagmanifest-cleanup-materialized-ref-name"></a>`cleanup_materialized_ref_name` | str | yes | Temporary materialization ref that Buildish considered for cleanup after tagging the RC. |
| <a id="creatercmaterializationtagmanifest-cleanup-materialized-ref-mode"></a>`cleanup_materialized_ref_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Policy that Buildish used when deciding whether to delete the temporary materialization ref after tagging. |
| <a id="creatercmaterializationtagmanifest-tag-creation-mode"></a>`tag_creation_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Mode that Buildish used when creating or reusing the related annotated Git tag. |
| <a id="creatercmaterializationtagmanifest-created-ref"></a>`created_ref` | str | yes | Git ref name that Buildish created or reused while performing the related tag or ref action. |

<a id="createreleasebranchmanifest"></a>
### CreateReleaseBranchManifest

Action manifest emitted after resolving or creating a release branch.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`create-release-branch-manifest.schema.json`](/components/release-tooling/schemas/create-release-branch-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createreleasebranchmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createreleasebranchmanifest-action"></a>`action` | Literal['create-release-branch'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createreleasebranchmanifest-release-line"></a>`release_line` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="createreleasebranchmanifest-release-branch"></a>`release_branch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git branch name that Buildish resolved as the authoritative release branch. |
| <a id="createreleasebranchmanifest-source-ref"></a>`source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Source ref that Buildish used as the starting point for the related release-branch or materialization action. |

<a id="createsourceartifactmanifest"></a>
### CreateSourceArtifactManifest

Action manifest emitted after creating one local source release artifact.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`create-source-artifact-manifest.schema.json`](/components/release-tooling/schemas/create-source-artifact-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="createsourceartifactmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="createsourceartifactmanifest-action"></a>`action` | Literal['create-source-artifact'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="createsourceartifactmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="createsourceartifactmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="createsourceartifactmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="createsourceartifactmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="createsourceartifactmanifest-source-artifact-path"></a>`source_artifact_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path of the locally produced or staged source release artifact. |
| <a id="createsourceartifactmanifest-source-artifact-sha512"></a>`source_artifact_sha512` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | SHA-512 digest of the staged or locally produced source release artifact. |

<a id="finalizedraftgithubreleasemanifest"></a>
### FinalizeDraftGithubReleaseManifest

Action manifest emitted after finalizing a selected GitHub draft release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`finalize-draft-github-release-manifest.schema.json`](/components/release-tooling/schemas/finalize-draft-github-release-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="finalizedraftgithubreleasemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="finalizedraftgithubreleasemanifest-action"></a>`action` | Literal['finalize-draft-github-release'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="finalizedraftgithubreleasemanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="finalizedraftgithubreleasemanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="finalizedraftgithubreleasemanifest-release-id"></a>`release_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub release id associated with the related draft or final release record. |
| <a id="finalizedraftgithubreleasemanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="finalizedraftgithubreleasemanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="finalizedraftgithubreleasemanifest-release-url"></a>`release_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="finalizedraftgithubreleasemanifest-deleted-asset-names"></a>`deleted_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | GitHub Release asset names that Buildish deleted during the related release-finalization step. |
| <a id="finalizedraftgithubreleasemanifest-finalize-mode"></a>`finalize_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Mode that Buildish used when finalizing the selected draft GitHub release. |

<a id="finalizercvotematerialsmanifest"></a>
### FinalizeRcVoteMaterialsManifest

Action manifest emitted after publishing and signing final RC vote materials.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`finalize-rc-vote-materials-manifest.schema.json`](/components/release-tooling/schemas/finalize-rc-vote-materials-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="finalizercvotematerialsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="finalizercvotematerialsmanifest-action"></a>`action` | Literal['finalize-rc-vote-materials'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="finalizercvotematerialsmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="finalizercvotematerialsmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="finalizercvotematerialsmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="finalizercvotematerialsmanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="finalizercvotematerialsmanifest-rc-tag-target-commit"></a>`rc_tag_target_commit` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git commit SHA that the RC tag resolved to during verification or publication. |
| <a id="finalizercvotematerialsmanifest-source-artifact-url"></a>`source_artifact_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical staged download URL of the source release artifact referenced by the RC vote materials. |
| <a id="finalizercvotematerialsmanifest-authoritative-manifest-url"></a>`authoritative_manifest_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical staged URL of the signed RC vote manifest. |
| <a id="finalizercvotematerialsmanifest-authoritative-manifest-sha512"></a>`authoritative_manifest_sha512` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | SHA-512 digest of the authoritative staged RC vote manifest. |
| <a id="finalizercvotematerialsmanifest-bootstrap-script-url"></a>`bootstrap_script_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Staged URL of the emitted verify-rc bootstrap helper script. |
| <a id="finalizercvotematerialsmanifest-bootstrap-script-sha512"></a>`bootstrap_script_sha512` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | SHA-512 digest of the emitted verify-rc bootstrap script. |
| <a id="finalizercvotematerialsmanifest-draft-release-url"></a>`draft_release_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub draft release URL associated with the current RC or final release workflow. |
| <a id="finalizercvotematerialsmanifest-secondary-artifact-count"></a>`secondary_artifact_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Count of secondary artifacts associated with the related manifest or publication step. |
| <a id="finalizercvotematerialsmanifest-mirrored-asset-names"></a>`mirrored_asset_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | GitHub release asset names that Buildish mirrored from the staged vote materials into the draft release bundle. |
| <a id="finalizercvotematerialsmanifest-gpg-fingerprint"></a>`gpg_fingerprint` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | OpenPGP fingerprint of the signing key Buildish used or verified. |

<a id="materializercgitcontentmanifest"></a>
### MaterializeRcGitContentManifest

Action manifest emitted after building detached RC materialization Git content.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`materialize-rc-git-content-manifest.schema.json`](/components/release-tooling/schemas/materialize-rc-git-content-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="materializercgitcontentmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="materializercgitcontentmanifest-action"></a>`action` | Literal['materialize-rc-git-content'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="materializercgitcontentmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="materializercgitcontentmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="materializercgitcontentmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="materializercgitcontentmanifest-materialized-paths"></a>`materialized_paths` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Filesystem paths that the materialization step created or refreshed for the current RC. |
| <a id="materializercgitcontentmanifest-materialized-commit-sha"></a>`materialized_commit_sha` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git commit SHA of the materialized tree that Buildish created for the RC tagging workflow. |
| <a id="materializercgitcontentmanifest-materialized-ref-name"></a>`materialized_ref_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Temporary Git ref name that Buildish created or reused for RC materialization. |
| <a id="materializercgitcontentmanifest-materialized-ref-mode"></a>`materialized_ref_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Policy that Buildish used when creating or reusing the temporary materialization ref. |

<a id="preparercmanifest"></a>
### PrepareRcManifest

Action manifest emitted after prepare-rc resolves one RC workflow state bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`prepare-rc-manifest.schema.json`](/components/release-tooling/schemas/prepare-rc-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="preparercmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="preparercmanifest-action"></a>`action` | Literal['prepare-rc'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="preparercmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="preparercmanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="preparercmanifest-source-date-epoch"></a>`source_date_epoch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="preparercmanifest-resolved-release-branch"></a>`resolved_release_branch` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release branch name that Buildish resolved for the selected version. |
| <a id="preparercmanifest-rc-number"></a>`rc_number` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Numeric RC sequence selected for the related version. |
| <a id="preparercmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="preparercmanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="preparercmanifest-source-artifact-name"></a>`source_artifact_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filename of the staged source release artifact. |
| <a id="preparercmanifest-source-artifact-root-name"></a>`source_artifact_root_name` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Root directory name that the source release archive should unpack to. |
| <a id="preparercmanifest-source-artifact-prefix-path"></a>`source_artifact_prefix_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Top-level path prefix inside the source release archive. |
| <a id="preparercmanifest-staging-url"></a>`staging_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |
| <a id="preparercmanifest-cleanup-existing-rc-staging"></a>`cleanup_existing_rc_staging` | Literal['true'] | no | Whether the prepare-rc flow cleaned up pre-existing same-version RC staging state before publishing new materials. |
| <a id="preparercmanifest-draft-release-action"></a>`draft_release_action` | Literal['recreate'] | no | Draft GitHub release convergence action that prepare-rc used when emitting new vote materials. |
| <a id="preparercmanifest-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |

<a id="pruneolderlinereleasesmanifest"></a>
### PruneOlderLineReleasesManifest

Action manifest emitted after pruning older same-line releases from dist/release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`prune-older-line-releases-manifest.schema.json`](/components/release-tooling/schemas/prune-older-line-releases-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="pruneolderlinereleasesmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="pruneolderlinereleasesmanifest-action"></a>`action` | Literal['prune-older-line-releases'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="pruneolderlinereleasesmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="pruneolderlinereleasesmanifest-release-line"></a>`release_line` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="pruneolderlinereleasesmanifest-pruned-versions"></a>`pruned_versions` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Older release versions that Buildish removed from the active release line while pruning prior dist/release artifacts. |
| <a id="pruneolderlinereleasesmanifest-release-base-url"></a>`release_base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base ASF dist/release URL associated with the related publication action. |

<a id="publishatrcandidatemanifest"></a>
### PublishAtrCandidateManifest

Action manifest emitted after publishing one release candidate to ATR.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`publish-atr-candidate-manifest.schema.json`](/components/release-tooling/schemas/publish-atr-candidate-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishatrcandidatemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishatrcandidatemanifest-action"></a>`action` | Literal['publish-atr-candidate'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishatrcandidatemanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishatrcandidatemanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="publishatrcandidatemanifest-atr-base-url"></a>`atr_base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base ATR service URL that Buildish used for the related candidate upload or status query. |
| <a id="publishatrcandidatemanifest-atr-committee"></a>`atr_committee` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF committee slug that Buildish reported to ATR for the related release candidate. |
| <a id="publishatrcandidatemanifest-atr-project"></a>`atr_project` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ATR project or product-line identifier that Buildish reported for the related release candidate. |
| <a id="publishatrcandidatemanifest-atr-release-mode"></a>`atr_release_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ATR release mode that Buildish selected for the related publication run. |
| <a id="publishatrcandidatemanifest-atr-phase"></a>`atr_phase` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ATR publication phase that Buildish targeted or reported for the related candidate. |
| <a id="publishatrcandidatemanifest-atr-latest-revision"></a>`atr_latest_revision` | str | yes | Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report. |
| <a id="publishatrcandidatemanifest-uploaded-file-names"></a>`uploaded_file_names` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | File names that Buildish uploaded to ATR for the related candidate. |
| <a id="publishatrcandidatemanifest-waited-for-checks"></a>`waited_for_checks` | Literal['true', 'false'] | yes | Whether Buildish waited for ATR checks to complete before emitting the related command manifest. |
| <a id="publishatrcandidatemanifest-atr-total-checks"></a>`atr_total_checks` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Total number of ATR checks observed for the related candidate revision. |
| <a id="publishatrcandidatemanifest-atr-failure-count"></a>`atr_failure_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that reported a failing outcome for the related candidate or report. |
| <a id="publishatrcandidatemanifest-atr-exception-count"></a>`atr_exception_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that ended in an exception state for the related candidate or report. |
| <a id="publishatrcandidatemanifest-atr-warning-count"></a>`atr_warning_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that reported warnings for the related candidate or report. |

<a id="publishdockerhubmovingtagsmanifest"></a>
### PublishDockerhubMovingTagsManifest

Action manifest emitted after publishing moving Docker Hub image aliases.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`publish-dockerhub-moving-tags-manifest.schema.json`](/components/release-tooling/schemas/publish-dockerhub-moving-tags-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishdockerhubmovingtagsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishdockerhubmovingtagsmanifest-action"></a>`action` | Literal['publish-dockerhub-moving-tags'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishdockerhubmovingtagsmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishdockerhubmovingtagsmanifest-source-image"></a>`source_image` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact source OCI image reference that should be copied to produce the published moving aliases. |
| <a id="publishdockerhubmovingtagsmanifest-image-repository"></a>`image_repository` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Container image repository name without the moving tag or digest suffix. |
| <a id="publishdockerhubmovingtagsmanifest-published-alias-refs"></a>`published_alias_refs` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Fully qualified target image references that Buildish published as moving aliases. |

<a id="publishsourcereleasesvnmanifest"></a>
### PublishSourceReleaseSvnManifest

Action manifest emitted after promoting a verified source artifact into dist/release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`publish-source-release-svn-manifest.schema.json`](/components/release-tooling/schemas/publish-source-release-svn-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="publishsourcereleasesvnmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="publishsourcereleasesvnmanifest-action"></a>`action` | Literal['publish-source-release-svn'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="publishsourcereleasesvnmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="publishsourcereleasesvnmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="publishsourcereleasesvnmanifest-source-url"></a>`source_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Source URL that Buildish copied or verified during a publication action. |
| <a id="publishsourcereleasesvnmanifest-target-url"></a>`target_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Destination URL that Buildish published or copied content to. |
| <a id="publishsourcereleasesvnmanifest-verified-source-artifact-sha512"></a>`verified_source_artifact_sha512` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Verified SHA-512 digest of the source release artifact promoted to ASF dist/release. |
| <a id="publishsourcereleasesvnmanifest-publish-mode"></a>`publish_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Mode that Buildish used when publishing the verified source artifact to ASF `dist/release`. |

<a id="recordartifactmanifest"></a>
### RecordArtifactManifest

Action manifest emitted after writing one typed secondary-artifact bundle.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`record-artifact-manifest.schema.json`](/components/release-tooling/schemas/record-artifact-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="recordartifactmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="recordartifactmanifest-action"></a>`action` | Literal['record-artifact'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="recordartifactmanifest-artifact-id"></a>`artifact_id` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Stable identifier for one source, secondary, or emitted artifact within Buildish release tooling. |
| <a id="recordartifactmanifest-kind"></a>`kind` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Declared artifact or report kind discriminator. |
| <a id="recordartifactmanifest-artifact-manifest-path"></a>`artifact_manifest_path` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Filesystem path to the emitted secondary-artifact manifest fragment. |
| <a id="recordartifactmanifest-artifact-bundle-dir"></a>`artifact_bundle_dir` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Directory that contains one emitted secondary-artifact registration bundle. |
| <a id="recordartifactmanifest-inventory-paths"></a>`inventory_paths` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Filesystem paths of supplemental inventory files emitted alongside one artifact bundle. |

<a id="releaseversionmanifest"></a>
### ReleaseVersionManifest

Action manifest emitted after a full release-version orchestration run completes.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`release-version-manifest.schema.json`](/components/release-tooling/schemas/release-version-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="releaseversionmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="releaseversionmanifest-action"></a>`action` | Literal['release-version'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="releaseversionmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="releaseversionmanifest-release-line"></a>`release_line` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Maintenance-line identifier used to group related versions, branches, and moving tags. |
| <a id="releaseversionmanifest-selected-rc-tag"></a>`selected_rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | RC tag that Buildish selected as the winning release candidate for a final release action. |
| <a id="releaseversionmanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="releaseversionmanifest-archive-versions"></a>`archive_versions` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Older same-line release versions that Buildish resolved for archival pruning. |
| <a id="releaseversionmanifest-release-url"></a>`release_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="releaseversionmanifest-moving-tags"></a>`moving_tags` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Derived moving tags or aliases that should point at the final released version. |
| <a id="releaseversionmanifest-final-tag-mode"></a>`final_tag_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Configured or recorded policy describing how the final immutable release tag should be created for this component or release run. |

<a id="reportatrchecksmanifest"></a>
### ReportAtrChecksManifest

Action manifest emitted after summarizing ATR checks for one candidate revision.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`report-atr-checks-manifest.schema.json`](/components/release-tooling/schemas/report-atr-checks-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="reportatrchecksmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="reportatrchecksmanifest-action"></a>`action` | Literal['report-atr-checks'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="reportatrchecksmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="reportatrchecksmanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="reportatrchecksmanifest-atr-base-url"></a>`atr_base_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Base ATR service URL that Buildish used for the related candidate upload or status query. |
| <a id="reportatrchecksmanifest-atr-committee"></a>`atr_committee` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF committee slug that Buildish reported to ATR for the related release candidate. |
| <a id="reportatrchecksmanifest-atr-project"></a>`atr_project` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ATR project or product-line identifier that Buildish reported for the related release candidate. |
| <a id="reportatrchecksmanifest-atr-phase"></a>`atr_phase` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ATR publication phase that Buildish targeted or reported for the related candidate. |
| <a id="reportatrchecksmanifest-atr-latest-revision"></a>`atr_latest_revision` | str | yes | Most recent ATR candidate revision known to Buildish when it emitted the related manifest or report. |
| <a id="reportatrchecksmanifest-atr-reported-revision"></a>`atr_reported_revision` | str | yes | ATR candidate revision that Buildish specifically reported in the related checks summary. |
| <a id="reportatrchecksmanifest-atr-total-checks"></a>`atr_total_checks` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Total number of ATR checks observed for the related candidate revision. |
| <a id="reportatrchecksmanifest-atr-failure-count"></a>`atr_failure_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that reported a failing outcome for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-exception-count"></a>`atr_exception_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that ended in an exception state for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-warning-count"></a>`atr_warning_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that reported warnings for the related candidate or report. |
| <a id="reportatrchecksmanifest-atr-success-count"></a>`atr_success_count` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Number of ATR checks that reported success for the related candidate or report. |
| <a id="reportatrchecksmanifest-strict-checking"></a>`strict_checking` | Literal['true', 'false'] | yes | Whether the related check or reporting step should fail the command when warnings or failures are present. |
| <a id="reportatrchecksmanifest-would-block-release"></a>`would_block_release` | Literal['true', 'false'] | yes | Whether the related check result would block release publication under the requested strictness policy. |

<a id="syncdraftgithubreleasemanifest"></a>
### SyncDraftGithubReleaseManifest

Action manifest emitted after synchronizing the draft GitHub release with staged RC artifacts.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`sync-draft-github-release-manifest.schema.json`](/components/release-tooling/schemas/sync-draft-github-release-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="syncdraftgithubreleasemanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="syncdraftgithubreleasemanifest-action"></a>`action` | Literal['sync-draft-github-release'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="syncdraftgithubreleasemanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="syncdraftgithubreleasemanifest-repository-slug"></a>`repository_slug` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | GitHub `owner/name` repository slug used for API calls and emitted release metadata. |
| <a id="syncdraftgithubreleasemanifest-resolved-source-ref"></a>`resolved_source_ref` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="syncdraftgithubreleasemanifest-rc-tag"></a>`rc_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact RC Git tag, including the leading `v` prefix and `-rcN` suffix. |
| <a id="syncdraftgithubreleasemanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="syncdraftgithubreleasemanifest-staging-url"></a>`staging_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | ASF dev/dist staging directory URL selected for the current RC. |
| <a id="syncdraftgithubreleasemanifest-deleted-release-ids"></a>`deleted_release_ids` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | GitHub draft release ids that Buildish deleted while converging on one selected release candidate. |
| <a id="syncdraftgithubreleasemanifest-release-id"></a>`release_id` | str | yes | GitHub release id associated with the related draft or final release record. |
| <a id="syncdraftgithubreleasemanifest-release-tag"></a>`release_tag` | str | yes | GitHub release tag name as stored on the related release record. |
| <a id="syncdraftgithubreleasemanifest-release-name"></a>`release_name` | str | yes | Human-facing GitHub release title used for the related draft or final release. |
| <a id="syncdraftgithubreleasemanifest-release-url"></a>`release_url` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Primary user-facing URL of the related GitHub release or published release artifact. |
| <a id="syncdraftgithubreleasemanifest-sync-mode"></a>`sync_mode` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Mode that Buildish used when reconciling the selected draft GitHub release with staged RC materials. |

<a id="updatemovingimagealiasesmanifest"></a>
### UpdateMovingImageAliasesManifest

Action manifest emitted after resolving moving OCI image aliases for publication.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`update-moving-image-aliases-manifest.schema.json`](/components/release-tooling/schemas/update-moving-image-aliases-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="updatemovingimagealiasesmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="updatemovingimagealiasesmanifest-action"></a>`action` | Literal['update-moving-image-aliases'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="updatemovingimagealiasesmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="updatemovingimagealiasesmanifest-exact-image-tag"></a>`exact_image_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Exact released image tag that Buildish uses as the source for moving image aliases. |
| <a id="updatemovingimagealiasesmanifest-image-aliases"></a>`image_aliases` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Derived moving container tags that should point at the exact released image tag. |

<a id="updatemovingtagsmanifest"></a>
### UpdateMovingTagsManifest

Action manifest emitted after updating moving Git tags for a final release.

- category: `emitted`
- ownership: `tooling-derived`
- schema file: [`update-moving-tags-manifest.schema.json`](/components/release-tooling/schemas/update-moving-tags-manifest.schema.json)
- audience: `internal`
- stability: `unstable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="updatemovingtagsmanifest-component"></a>`component` | object | yes | Component identifier for the Buildish command manifest or emitted action record. |
| <a id="updatemovingtagsmanifest-action"></a>`action` | Literal['update-moving-tags'] | no | Stable command action identifier written by one Buildish command manifest. |
| <a id="updatemovingtagsmanifest-version"></a>`version` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Release version string without a leading `v` prefix. |
| <a id="updatemovingtagsmanifest-final-tag"></a>`final_tag` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Final immutable Git tag that Buildish intends to publish for the released version. |
| <a id="updatemovingtagsmanifest-target-commit"></a>`target_commit` | [NonEmptyString](../release-shared-types-reference/#nonemptystring) | yes | Git commit SHA that the related tag or alias operation targeted. |
| <a id="updatemovingtagsmanifest-updated-tags"></a>`updated_tags` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Moving tags that Buildish updated during the related tag-publication action. |
| <a id="updatemovingtagsmanifest-skipped-tags"></a>`skipped_tags` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Moving tags that Buildish intentionally left unchanged during the related update operation. |
| <a id="updatemovingtagsmanifest-tag-update-modes"></a>`tag_update_modes` | list[[NonEmptyString](../release-shared-types-reference/#nonemptystring)] | yes | Per-tag update outcomes describing how each moving tag was handled during the related publication run. |

