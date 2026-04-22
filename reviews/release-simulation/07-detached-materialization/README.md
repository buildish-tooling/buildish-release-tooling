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

# Scenario 07: Detached Materialization Commit

## Component

- `buildish-mammoth-cache`
- `final_tag_mode: detached-materialization-commit`

## Workflow Path

### Releasey Prepare RC

1. shared RC jobs through `build-source-rc`
2. `materialize-rc-dist-payload`
   - `TODO` only
   - logical simulation uses a dummy detached commit that adds generated `dist/` content without
     entering the release-branch history
3. `create-rc-materialization-tag`
   - `create-rc-materialization-tag --rc-tag v1.2.3-rc0 --target-commit <dummy-detached-commit> 1.2.3`
4. `sync-draft-github-release`
   - `sync-draft-github-release --rc-tag v1.2.3-rc0 1.2.3`
5. `finalize-rc-vote-materials`
   - `finalize-rc-vote-materials --rc-tag v1.2.3-rc0 1.2.3`

### Releasey Release Version

1. shared source-release jobs
2. `create-final-tag`
3. `publish-github-action-release`
   - `TODO` only
4. `update-moving-tags`
5. `finalize-draft-github-release`

## Logical Outcome

- The shared tooling is capable of tagging a detached materialization commit once it is given an
  explicit `--target-commit`.
- With a dummy detached commit supplied, the RC tag and final exact tag path is logically coherent:
  the RC tag points at the detached commit, and the final exact tag can later reuse that same
  commit.
- The component workflow cannot currently produce that target commit, so the full detached release
  path is still blocked.

## Findings

- The prepare-RC workflow is not actually executable today.
  - `materialize-rc-dist-payload` is a placeholder and produces no commit SHA.
  - `create-rc-materialization-tag` consumes a hard-coded placeholder environment value instead of a
    real job output.
  - References:
    - [releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-mammoth-cache/.github/workflows/releasey-20-prepare-rc.yml)

- The final GitHub Action publication step is also still a placeholder.
  - The workflow can create the final exact tag, but it cannot yet publish the action payload from
    that detached commit.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-mammoth-cache/.github/workflows/releasey-30-release-version.yml)
