---
title: "Release configuration and authored override types"
description: "Consumer-owned and component-owned authored configuration models, including `release-config.yaml` and local verify-rc override payloads."
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

Consumer-owned and component-owned authored configuration models, including `release-config.yaml` and local verify-rc override payloads.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

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
- schema file: [`command-context.schema.json`](../../../schemas/command-context.schema.json)
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
- schema file: [`component-config.schema.json`](../../../schemas/component-config.schema.json)
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
| <a id="componentconfig-release-program"></a>`release_program` | ReleaseProgram | no | Release-governance program whose policy model Buildish should apply to this component. |
| <a id="componentconfig-project-status"></a>`project_status` | ProjectStatus | no | Project lifecycle status within the configured release program. |
| <a id="componentconfig-incubator-disclaimer-file"></a>`incubator_disclaimer_file` | str | no | Project-root-relative file path that supplies the approved incubating disclaimer text. |
| <a id="componentconfig-candidate-start-number"></a>`candidate_start_number` | int | no | First numeric candidate suffix to use when no matching candidate tag exists for a version and label. |
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
- schema file: [`prepare-rc-state.schema.json`](../../../schemas/prepare-rc-state.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="preparercstate-resolved-release-branch"></a>`resolved_release_branch` | str | yes | Release branch name that Buildish resolved for the selected version. |
| <a id="preparercstate-resolved-source-ref"></a>`resolved_source_ref` | str | yes | Resolved source Git commit SHA that Buildish selected for release production or verification. |
| <a id="preparercstate-source-date-epoch"></a>`source_date_epoch` | int | yes | Canonical `SOURCE_DATE_EPOCH` integer carried through RC production and verification. |
| <a id="preparercstate-candidate-label"></a>`candidate_label` | str | no | Candidate-series label used in the selected candidate tag. |
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
- schema file: [`release-version-state.schema.json`](../../../schemas/release-version-state.schema.json)
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
- schema file: [`verify-rc-override-file-config.schema.json`](../../../schemas/verify-rc-override-file-config.schema.json)
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

