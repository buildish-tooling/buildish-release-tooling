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
   - `materialize-rc-git-content --rc-tag v1.2.3-rc0 --materialized-path dist --materialized-ref-name <temp-ref> --run-command '<component build>' 1.2.3`
3. `create-rc-materialization-tag`
   - `create-rc-materialization-tag --rc-tag v1.2.3-rc0 --target-commit <materialized-commit> --cleanup-materialized-ref-name <temp-ref> 1.2.3`
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

- The shared tooling can now create one detached materialization commit in isolated Git state,
  optionally anchor it on a temporary remote ref for later jobs, and then create the RC tag on that
  exact commit.
- The RC tag and final exact tag path is now logically coherent end to end: the RC tag points at
  the detached commit, and the final exact tag can later reuse that same commit.
- The remaining release-path gap is the later GitHub Action publication placeholder in
  `releasey-30-release-version.yml`.

## Findings

- The final GitHub Action publication step is also still a placeholder.
  - The workflow can create the final exact tag, but it cannot yet publish the action payload from
    that detached commit.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-mammoth-cache/.github/workflows/releasey-30-release-version.yml)
