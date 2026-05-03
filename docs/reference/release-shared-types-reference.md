---
title: "Release shared types reference"
description: "Generated scalar alias, literal-set, and enum reference for Buildish Release Tooling contracts."
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

This page defines the shared scalar aliases, literal sets, and enums that appear across the generated contract pages.

Back to the [reference overview](../release-model-schema-reference/).

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


