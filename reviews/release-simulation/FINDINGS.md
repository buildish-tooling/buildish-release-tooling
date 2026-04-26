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

# Consolidated Findings After Rerun

This file summarizes the logical release simulation after the latest `buildish-release-tooling`
fixes were applied and the scenario set was re-reviewed.

## Closed By Fixes

- Follow-up RCs for the same exact version now allocate the next RC number, rather than reusing the
  highest existing RC number.
- Later `prepare-rc` jobs now carry the resolved `rc_tag` explicitly, so they no longer drift to a
  newer RC number within the same workflow run.
- `release-version` now selects the RC from the exact-version draft GitHub Release rather than
  mechanically picking the highest matching Git tag.
- `release-version` workflows can now carry the resolved `selected_rc_tag` into later RC-sensitive
  jobs, and those commands can fail if the draft release drifted to a newer RC.
- `publish-source-release-svn` now treats an already-copied identical final release directory as a
  successful rerun.
- `sync-draft-github-release` now reuses the same RC draft release, deletes lower-RC drafts, and
  fails on a higher-RC draft.
- The RC vote manifest can now include secondary artifact entries when component workflows supply
  secondary artifact manifests.
- `buildish-release-tooling` now uses podling vote semantics in its checked-in release config.
- RC tag creation now fails if the exact RC tag already exists, which makes same-version concurrent
  `Prepare RC` runs fail fast instead of silently sharing one RC tag.
- Docker Hub moving-alias publication now exists in the shared tooling for already-pushed exact
  image refs.

## Remaining Findings

### Medium

- `buildish-mammoth-cache` is still blocked by draft-workflow `TODO` jobs.
  - The draft `Prepare RC` workflow now materializes and tags the detached `dist/` commit through
    shared tooling, but the final GitHub Action publication job is still a placeholder.
  - References:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-mammoth-cache/.github/workflows/releasey-30-release-version.yml)

- The component workflows with secondary artifacts remain structurally incomplete.
  - The shared tooling can now carry secondary artifact manifests into the signed RC vote manifest,
    but the checked-in draft workflows still do not build, publish, and hand off those manifests for
    the non-source targets.
  - References:
    - [buildish-no-gradle-wrapper-jar releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-no-gradle-wrapper-jar/.github/workflows/releasey-20-prepare-rc.yml)
    - [buildish-no-gradle-wrapper-jar releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-no-gradle-wrapper-jar/.github/workflows/releasey-30-release-version.yml)
    - [buildish-site-pipeline releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-20-prepare-rc.yml)
    - [buildish-site-pipeline releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-site-pipeline/.github/workflows/releasey-30-release-version.yml)

### Low

- The tooling repo's own draft `release-version` workflow still contains a placeholder PyPI job
  even though the component has no configured secondary targets.
  - This is workflow noise rather than a release-correctness bug.
  - Reference:
    - [releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-release-tooling/.github/workflows/releasey-30-release-version.yml)
