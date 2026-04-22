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

# Scenario 04: Release `1.2.3` After `1.3.4`

## Assumptions

- `1.3.4` has already reached final release
- `v1` already points at `v1.3.4`
- A later release run publishes `1.2.3`

## Workflow Path

- `buildish-mammoth-cache` `release-version` workflow is the most complete moving-tag case
  because it actually invokes `update-moving-tags`.

## Job And CLI Trace

1. `resolve-latest-rc`
   - `release-version 1.2.3`
   - selects the approved RC from the exact-version draft GitHub Release body
2. `publish-source-release-svn`
   - `publish-source-release-svn 1.2.3`
3. `prune-older-line-releases`
   - `prune-older-line-releases 1.2.3`
4. `create-final-tag`
   - `create-final-tag 1.2.3`
5. `publish-github-action-release`
   - `TODO`
6. `update-moving-tags`
   - `update-moving-tags 1.2.3`
7. `finalize-draft-github-release`

## Logical Outcome

- Same-line pruning uses the specific release line `1.2.x`, so it only prunes older `1.2.x`
  releases.
- Moving Git tags use no-backward-move logic:
  - `v1.2` may move to `1.2.3`
  - `v1` must stay on `1.3.4`

## Findings

- The Git tag-moving logic matches the intended anti-rollback behavior for Git tag-backed aliases.
  - References:
    - [commands.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/commands.py)

- The container-image path is not equivalently complete.
  - The shared tooling can now publish Docker Hub moving aliases from an already-pushed exact image
    ref, but the checked-in component workflow still does not invoke that path because the exact
    Docker Hub publication job is still a placeholder.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-30-release-version.yml)
