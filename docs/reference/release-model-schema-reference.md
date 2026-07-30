---
title: "Release model schema reference"
description: "This reference is generated from the Buildish Release Tooling Pydantic models and checked-in reference metadata. Do not edit it by hand; regenerate it with `make schemas`."
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

This reference describes the typed Buildish Release Tooling contracts that are checked into this repository.
It covers supported external configuration and verification/report contracts, plus internal runtime contracts and internal unstable command action manifests.

## How to read this reference

- file-contract pages identify stable checked-in file contracts where one exists
- `audience` distinguishes supported external contracts from Buildish-owned internal contracts
- `stability` distinguishes stable supported/internal contracts from intentionally unstable internal machine I/O
- field names are shown in their wire-format aliases
- schema files link to the published JSON Schema contract for the matching root type

## Reference pages

- [File contract index](../release-file-contract-index/) — supported and internal file/root contract tables.
- [Shared types reference](../release-shared-types-reference/) — shared scalar aliases, literal sets, and enums.
- [Release configuration and authored override types](../release-config-reference/) — Consumer-owned and component-owned authored configuration models, including `release-config.yaml` and local verify-rc override payloads.
- [Release manifests, inventories, and verification report types](../release-manifests-and-verification-reference/) — Typed Buildish release manifests, emitted verification reports, inspection-bundle payloads, and related helper contracts.
- [Internal unstable command action manifest types](../release-command-manifests-reference/) — Machine-readable command action manifests written for workflow coordination. These are Buildish-owned internal input/output contracts and are intentionally unstable.
- [Harness configuration types](../release-harness-config-reference/) — Committed and resolved release-harness configuration models.
- [Harness scenario and runtime result types](../release-harness-runtime-reference/) — Harness scenario inputs, mocked tool behavior contracts, and machine-readable run results.
- [Harness shim builtin payload types](../release-harness-shim-reference/) — Small runtime payloads used by the harness shim to emulate GitHub and other tools.

## Coverage notes

- generated schema files: `55`
- command action manifests are documented here for maintenance and debugging, but they are intentionally unstable and not a supported external API.

