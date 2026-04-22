---
title: "Harness configuration types"
description: "Committed and resolved release-harness configuration models."
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

Committed and resolved release-harness configuration models.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

- [ReleaseHarnessConfig](#releaseharnessconfig) — Committed `release-harness.yaml` plus optional local overrides.
- [RepositoryOverrideConfig](#repositoryoverrideconfig) — Committed harness settings for one explicit repository override.
- [ResolvedReleaseHarnessConfigJson](#resolvedreleaseharnessconfigjson) — Machine-readable JSON payload for one resolved harness config file.
- [ResolvedRepositoryBindingJson](#resolvedrepositorybindingjson) — Machine-readable JSON payload for one resolved harness repository binding.
- [SelfRepositoryConfig](#selfrepositoryconfig) — Committed harness settings for the workflow repository under test.

<a id="releaseharnessconfig"></a>
### ReleaseHarnessConfig

Committed `release-harness.yaml` plus optional local overrides.

- category: `authored`
- ownership: `consumer-owned`
- schema file: [`release-harness-config.schema.json`](/components/release-tooling/schemas/release-harness-config.schema.json)
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
| <a id="repositoryoverrideconfig-local-checkout-mode"></a>`local_checkout_mode` | [RepositoryOverrideCheckoutMode](../release-shared-types-reference/#repositoryoverridecheckoutmode) | no | Policy describing whether the related repository binding should resolve to a local checkout path. |
| <a id="repositoryoverrideconfig-local-path"></a>`local_path` | str | no | Resolved or configured local filesystem path associated with the related repository binding. |

<a id="resolvedreleaseharnessconfigjson"></a>
### ResolvedReleaseHarnessConfigJson

Machine-readable JSON payload for one resolved harness config file.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`resolved-release-harness-config-json.schema.json`](/components/release-tooling/schemas/resolved-release-harness-config-json.schema.json)
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
| <a id="selfrepositoryconfig-local-checkout-mode"></a>`local_checkout_mode` | [SelfRepositoryCheckoutMode](../release-shared-types-reference/#selfrepositorycheckoutmode) | no | Policy describing whether the related repository binding should resolve to a local checkout path. |
| <a id="selfrepositoryconfig-local-path"></a>`local_path` | str | no | Resolved or configured local filesystem path associated with the related repository binding. |

