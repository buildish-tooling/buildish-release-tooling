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

# Scenario 03: Parallel RCs On `1.2.x` And `1.3.x`

## Assumptions

- RC A: `1.2.3`
- RC B: `1.3.4`
- Both exist or are being prepared concurrently
- Major line is shared (`1.x`), but exact versions differ

## Workflow Path

- `Releasey Prepare RC` for `1.2.3`
- `Releasey Prepare RC` for `1.3.4`

## Logical Trace

- Source branch resolution is exact-version aware and prefers:
  - `release/1.2.x` then `release/1.x` for `1.2.3`
  - `release/1.3.x` then `release/1.x` for `1.3.4`
- RC numbering is exact-version scoped:
  - only tags matching `v1.2.3-rcN` affect `1.2.3`
  - only tags matching `v1.3.4-rcN` affect `1.3.4`
- ASF SVN dev cleanup is exact-version scoped:
  - `cleanup-dev-svn-rcs 1.2.3` deletes only `1.2.3-rcN/`
  - `cleanup-dev-svn-rcs 1.3.4` deletes only `1.3.4-rcN/`
- Draft GitHub Releases are keyed by exact final tag:
  - `v1.2.3`
  - `v1.3.4`

## Outcome

- No direct collision was found between parallel RCs for different minor lines on the same major
  line.
- The current code correctly isolates exact-version Git tags, exact-version ASF SVN staging
  directories, and exact-version draft GitHub Releases.

## Findings

- No exact-version collision bug was found for this scenario.
- Same-version concurrency is now fail-fast at RC tag creation rather than silently sharing one RC
  tag, so no additional cross-minor finding remains here.
