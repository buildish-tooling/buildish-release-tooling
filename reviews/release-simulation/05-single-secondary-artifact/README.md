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

# Scenario 05: One Secondary Artifact Target

## Component

- `buildish-no-gradle-wrapper-jar`
- Secondary target family: `github-release-assets`

## Workflow Path

### Releasey Prepare RC

1. shared RC jobs through `build-source-rc`
2. `stage-bootstrap-assets`
   - `TODO` only
3. `create-rc-tag`
4. `sync-draft-github-release`
5. `finalize-rc-vote-materials`

### Releasey Release Version

1. shared source-release jobs
2. `create-final-tag`
3. `publish-immutable-github-release-assets`
   - `TODO` only
4. `finalize-draft-github-release`

## Logical Outcome

- The source release path works.
- The shared tooling can now carry the secondary artifact inventory into the signed RC vote
  manifest, but only if the workflow supplies a secondary artifact manifest file.
- The checked-in component workflow still does not build or publish the convenience artifact, so the
  end-to-end secondary artifact path remains incomplete.

## Findings

  - The component draft workflow still never produces the secondary artifact manifest that
    `finalize-rc-vote-materials` expects for voted convenience artifacts.
  - `stage-bootstrap-assets` is still a placeholder, so no machine-readable artifact inventory is
    handed to the shared tooling.
  - Reference:
    - [releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-no-gradle-wrapper-jar/.github/workflows/releasey-20-prepare-rc.yml)

- The component draft workflow still never calls `attach-github-release-assets` for the final
  immutable convenience asset publication path.
  - `publish-immutable-github-release-assets` is still a `TODO` echo-only job.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-no-gradle-wrapper-jar/.github/workflows/releasey-30-release-version.yml)

- `finalize-draft-github-release` can therefore publish the GitHub Release without the expected
  immutable convenience assets.
