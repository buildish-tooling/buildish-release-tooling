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

# Release Tooling Release Process

This draft applies the Buildish release architecture to `buildish-release-tooling`.

## Special rule for this component

This component is the shared release implementation layer used by other Buildish components.

Because of that:

- its own release workflows must execute the checked-out source tree directly
- it must not require an already-installed copy of itself to release itself
- optional PyPI publication should stay a convenience channel only
- the official ASF release remains the signed source archive published through ASF distribution
  infrastructure

## Draft workflow set

### `Create release branch`

Inputs:

- `release_line`
- `source_ref`

Behavior:

- resolve and optionally create `release/<line>` from the checked-out repository using
  `bash buildish-release-tooling/release-tooling.sh create-release-branch`

### `Prepare RC`

Inputs:

- exact `version`
- optional `source_sha`

Behavior:

- hard-gate the source commit on successful or skipped GitHub checks
- resolve release state from the checked-out repository using the local tooling checkout
- build the reproducible source artifact
- write `.sha512`
- sign with the ASF-managed CI key
- stage the source RC into ASF SVN
- emit vote mail and verification blocks through the GitHub Summary

### `Verify RC`

This is authored as a local Linux/macOS verification flow and may also be run from a manual
workflow. The authoritative verification still happens on trusted owned hardware.

### `Release version`

Inputs:

- exact `version`

Behavior:

- resolve the latest RC
- promote the exact source release from `dist/dev` to `dist/release`
- prune older same-line source releases from `dist/release`
- create the exact final tag on the same source commit as the released RC
- optionally publish convenience Python artifacts in a separate retryable job
- finalize the draft GitHub Release

## Consumption model

This component is intended to be consumed by other Buildish repositories via:

- an exact pinned Git ref
- a checked-out source tree in the workflow workspace
- `bash buildish-release-tooling/release-tooling.sh ...`

`uvx` can be supported for ad hoc local invocation, but the pinned source checkout is the
release-critical path.
