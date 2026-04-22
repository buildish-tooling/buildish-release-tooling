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

# Scenario 08: Transient Failure And Job Rerun Safety

## Goal

Assess whether individual jobs are safe to rerun after a transient error, following the current
code paths.

## Assessment By Job / Command Family

### Safely Repeatable In The Common Case

- `verify-source-ref-checks`
- `prepare-rc`
- `cleanup-dev-svn-rcs`
- `build-source-rc`
- `prune-older-line-releases`
- `create-final-tag`
- `update-moving-tags`
- `finalize-draft-github-release`

These are read-only or are explicitly tolerant of already-applied state.

### Conditionally Repeatable

- `create-rc-materialization-tag`
  - now fails if the RC tag already exists, even on the same target commit
  - that makes same-version concurrent `Prepare RC` runs fail fast
  - it also means the RC-tag job is no longer intended as a transparent rerun-on-success no-op

- `finalize-rc-vote-materials`
  - safe if the RC tag, source RC, and draft release still describe the same RC
  - safe for secondary artifacts only if the same secondary artifact manifest files are available on
    rerun

### Conditionally Repeatable But Now Idempotent In Same-State Reruns

- `publish-source-release-svn`
  - if the target ASF release directory already exists and matches the source RC directory, the
    rerun is now treated as success
  - if the target exists but differs, the rerun still fails hard
  - this is the right behavior for an ambiguous post-copy failure

- `sync-draft-github-release`
  - rerunning for the same RC is now safe and updates the existing same-RC draft release in place
  - lower-RC draft releases are removed
  - a higher-RC draft release still causes a hard failure, which is the intended safety stop

## Findings

- The common source-only path is fairly rerun-friendly.
- The release-publication boundary in ASF SVN is now idempotent for same-state reruns, which closes
  the previous ambiguity gap.
- Draft GitHub Release synchronization is now rerun-safe for the same RC and explicitly protects
  against higher-RC regression.
- The remaining rerun gaps are mostly component-specific `TODO` jobs, because the incomplete
  convenience publication paths cannot yet demonstrate resumability end to end.
