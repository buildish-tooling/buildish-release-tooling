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

# Scenario 01: Initial Tooling Release With No Secondary Artifacts

## Assumptions

- Component: `buildish-release-tooling`
- Exact version: `1.2.3`
- No pre-existing `v1.2.3-rcN` tags
- No pre-existing `dist/dev/.../1.2.3-rc0/`
- No pre-existing `dist/release/.../1.2.3/`
- `secondary_targets: []`

## Workflows Traversed

- `.github/workflows/releasey-20-prepare-rc.yml`
- `.github/workflows/releasey-30-release-version.yml`

## Job And CLI Trace

### Releasey Prepare RC

1. `verify-source-ref-checks`
   - `bash buildish-release-tooling/release-tooling.sh verify-source-ref-checks 1.2.3`
2. `resolve-state`
   - `bash buildish-release-tooling/release-tooling.sh prepare-rc 1.2.3`
   - resolves `rc_tag=v1.2.3-rc0`
3. `cleanup-dev-svn-rcs`
   - `bash buildish-release-tooling/release-tooling.sh cleanup-dev-svn-rcs 1.2.3`
4. `build-source-rc`
   - `bash buildish-release-tooling/release-tooling.sh build-source-rc --rc-tag v1.2.3-rc0 1.2.3`
5. `create-rc-tag`
   - `bash buildish-release-tooling/release-tooling.sh create-rc-materialization-tag --rc-tag v1.2.3-rc0 1.2.3`
6. `sync-draft-github-release`
   - `bash buildish-release-tooling/release-tooling.sh sync-draft-github-release --rc-tag v1.2.3-rc0 1.2.3`
7. `finalize-rc-vote-materials`
   - `bash buildish-release-tooling/release-tooling.sh finalize-rc-vote-materials --rc-tag v1.2.3-rc0 1.2.3`

### Releasey Release Version

1. `resolve-latest-rc`
   - `bash buildish-release-tooling/release-tooling.sh release-version 1.2.3`
   - selects `v1.2.3-rc0` from the exact-version draft GitHub Release
2. `publish-source-release-svn`
   - `bash buildish-release-tooling/release-tooling.sh publish-source-release-svn --selected-rc-tag v1.2.3-rc0 1.2.3`
3. `prune-older-line-releases`
   - `bash buildish-release-tooling/release-tooling.sh prune-older-line-releases 1.2.3`
4. `create-final-tag`
   - `bash buildish-release-tooling/release-tooling.sh create-final-tag --selected-rc-tag v1.2.3-rc0 1.2.3`
5. `publish-pypi-convenience-artifacts`
   - no tooling command; `TODO` echo only
6. `finalize-draft-github-release`
   - `bash buildish-release-tooling/release-tooling.sh finalize-draft-github-release --selected-rc-tag v1.2.3-rc0 1.2.3`

## Logical Outcome

- The source-only RC path is mostly coherent.
- The final release path is coherent for the ASF source release and exact final tag.
- No secondary-artifact inventory is required for this component because `secondary_targets: []`.
- The checked-in config now matches the podling vote semantics implied by the ASF incubator paths.

## Findings

- The draft release workflow still contains a placeholder PyPI publication job even though the
  component has no configured secondary targets.
  - This is not a correctness bug by itself, but it makes the draft workflow shape diverge from the
    actual component policy.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-release-tooling/.github/workflows/releasey-30-release-version.yml)
