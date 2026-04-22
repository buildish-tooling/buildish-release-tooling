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

# Scenario 06: Multiple Secondary Artifact Targets

## Component

- `buildish-site-pipeline`
- Secondary target families: `pypi`, `dockerhub`

## Workflow Path

### Releasey Prepare RC

1. shared RC jobs through `build-source-rc`
2. `build-staged-python-artifacts`
   - `TODO` only
3. `build-staged-container-artifacts`
   - `TODO` only
4. `create-rc-tag`
5. `sync-draft-github-release`
6. `finalize-rc-vote-materials`

### Releasey Release Version

1. shared source-release jobs
2. `create-final-tag`
3. `publish-pypi`
   - `TODO` only
4. `publish-dockerhub`
   - `TODO` only
5. `update-moving-image-aliases`
   - derives aliases only
6. `finalize-draft-github-release`

## Logical Outcome

- The workflow can complete the source release path.
- It cannot yet produce a complete RC inventory or a complete final publication inventory for the
  Python and container convenience artifacts.

## Findings

- Both RC-only staging jobs are still placeholders, so the workflow never generates reviewer-visible
  secondary artifacts or secondary artifact manifest files before creating the RC tag.
  - References:
    - [releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-20-prepare-rc.yml)

- Both final publication jobs are still placeholders, so the final release can be published without
  actually shipping either PyPI packages or Docker Hub images.
  - References:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-30-release-version.yml)

- The moving-image step is advisory only.
  - The checked-in workflow still uses only the advisory alias-planning step.
  - Shared tooling support for actual Docker Hub moving-tag publication now exists, but the draft
    workflow does not call it yet because the exact-image publish job is still a placeholder.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-30-release-version.yml)
