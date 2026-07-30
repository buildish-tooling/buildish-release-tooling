<!--
  Copyright 2026 The Buildish Authors

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

# Real-CLI `act` Backend Plan

This document describes the planned next step for `buildish-release-harness`: running the real
`buildish-release-tooling` CLI inside the `act` backend against harness-owned Git and ASF SVN test
state, instead of relying primarily on mocked CLI responses.

## Why this is worth doing

The current `act` backend already gives useful workflow-level confidence:

- it executes the real checked-in workflow YAML
- it exercises rewritten `actions/checkout` and `setup-uv` behavior
- it shows live step progress
- it captures step summaries and aggregates them into per-job summaries

However, the current `releasey-*` scenarios for `buildish-release-tooling` still mock the
`buildish-release-tooling` CLI for most workflow steps. That leaves a gap:

- workflow structure is validated
- but many release side effects are not yet validated in the `act` path

Moving the `act` backend toward real CLI execution is therefore valuable because it would validate
much more of what a real production release workflow run actually does.

## Overall evaluation

This work is feasible and worthwhile.

It is not tiny, but it is also not a rabbit hole if scoped carefully.

Estimated size:

- small to medium for `releasey-10-create-release-branch`
- small to medium for `releasey-40-verify-rc`
- medium for `releasey-20-prepare-rc`
- medium for `releasey-30-release-version`

The main reason the work stays tractable is that the current `act` backend already handles:

- workflow rewriting
- local checkout overrides
- command shims
- progress streaming
- step summaries
- rerun support

The missing part is not “build a GitHub Actions runner”. The missing part is “let selected
workflows call the real CLI against harness-managed local services and repositories”.

## Non-goals

This plan does not aim to:

- replace the current custom harness backend
- emulate all marketplace actions
- emulate GitHub permissions, environments, or concurrency perfectly
- replace lower-level direct integration tests

The `act` backend should remain a workflow-focused integration layer around the real release CLI.

## Mutable state and inspectability

### Current mutable state

For the `act` backend today, the main mutable Git checkout is already the workspace root:

- `<workspace>/`

That checkout is authoritative for the workflow-under-test and should remain the main place to
inspect mutated Git state.

Companion repositories currently staged under:

- `<workspace>/.buildish-release-harness/repo-sources/`

are support material for local checkouts and imports. They are not currently intended to be the
primary mutable repositories under test.

### Recommended inspectable layout

The harness should standardize the following locations for real-CLI `act` scenarios:

- authoritative local Git origin for the workflow repository under test:
  - `<workspace>/.buildish-release-harness/git-origins/self/`
- workflow repository under test:
  - `<workspace>/`
- generated harness state:
  - `<workspace>/.buildish-release-harness/`
- staged companion repository sources:
  - `<workspace>/.buildish-release-harness/repo-sources/`
- mutable companion Git checkouts, when needed:
  - `<workspace>/.buildish-release-harness/git-checkouts/<repo-slug>/`
- local ASF SVN repository:
  - `<workspace>/.buildish-release-harness/svn/repository/`
- local ASF SVN working copy:
  - `<workspace>/.buildish-release-harness/svn/working-copy/`

This gives users stable paths for inspection after a run.

### Recommendation on Git checkout duplication

The main workflow repository should remain the authoritative mutable working clone at the workspace
root, but it should be backed by a separate local origin repository under
`.buildish-release-harness/`.

Reason:

- the workspace root should remain the single obvious place to inspect the mutable working tree
- a separate local origin is still useful for realistic fetch, branch, and tag behavior
- some release flows need a distinction between:
  - the mutable checked-out repository under test
  - the repository that acts as `origin`
- users inspecting the result should look at the workspace root for the main repository

Extra mutable Git repositories should only be created when a scenario truly needs them.

### Recommendation on the workflow repository under test

Yes, the harness should model the workflow repository under test as:

1. a local origin repository
2. a separate mutable working clone at the workspace root

That is the cleanest shape for release workflows because the workflow may:

- create local branches
- create local tags
- fetch from `origin`
- compare local and remote refs

The current `act` backend already approximates this by materializing a separate clone for the
workspace root and pointing `origin` at staged local repository data. The plan should formalize
that model and make it inspectable instead of treating it as an implementation detail.

## Runner environment requirements

To execute the real CLI in the `act` backend, the runner environment needs more than the current
mocked path:

- `git`
- `svn` and `svnadmin`
- `gpg`
- `python3`
- `uv` support or an equivalent harness shim path

`gh` and `docker` should remain shimmed for deterministic harness behavior.

The most likely implementation shape is:

- keep the current `act` runner image mapping
- add a custom harness runner image later if the default image is insufficient

The custom runner image should only be introduced when the default `act` images are no longer
enough for real CLI execution.

## Summary of desired end state

In the desired end state, an `act` harness run for `buildish-release-tooling` would:

1. run the real workflow YAML
2. invoke the real `buildish-release-tooling` CLI for release steps
3. operate on a real mutable Git checkout
4. operate on a real local ASF SVN repository and working copy
5. keep `gh` and `docker` mocked
6. produce inspectable state for:
   - Git refs and commits
   - local SVN `dist/dev` and `dist/release`
   - manifests
   - summaries
   - email proposals

## Phases

### Phase 1: Observability and stable mutable-state locations

Goal:

- make the `act` workspace structure explicit and stable for inspection

Tasks:

- document the authoritative mutable Git checkout location as the workspace root
- add stable subdirectories for harness-owned mutable SVN state
- add stable subdirectories for optional extra mutable Git checkouts
- surface those locations clearly in harness stderr and JSON output

Done when:

- users can inspect the workspace and know where Git and SVN state lives
- the layout no longer depends on reading harness implementation details

### Phase 2: Real CLI support for `releasey-10` and `releasey-40`

Goal:

- run the real CLI for the low-risk workflows first

Status:

- implemented for the tooling repo's committed `releasey-10-create-release-branch` and
  `releasey-40-verify-rc` scenarios

Targets:

- `releasey-10-create-release-branch`
- `releasey-40-verify-rc`

Tasks:

- let selected scenarios opt into real CLI execution for `uv run ... buildish-release-tooling ...`
- keep `gh`, `docker`, and other external-service boundaries mocked
- ensure summaries reflect real command output rather than mocked placeholders

Done when:

- the `act` scenarios for `releasey-10` and `releasey-40` no longer rely on mocked
  `buildish-release-tooling` command responses

### Phase 3: Real local ASF SVN support

Goal:

- provide a harness-owned local ASF SVN repository and working copy inside the `act` workspace

Status:

- implemented for the `act` backend workspace bootstrap path
- committed `releasey-20-prepare-rc` and `releasey-30-release-version` scenarios now declare
  local SVN fixture state through `workflow.svn_fixture`

Tasks:

- create a local SVN repository under `.buildish-release-harness/svn/repository/`
- create a working copy under `.buildish-release-harness/svn/working-copy/`
- overlay `release-config.yaml` in the workspace so CLI commands use `file://...` URLs
- expose those paths in harness output and docs

Done when:

- `act` scenarios can stage and inspect local `dist/dev` and `dist/release`
- users can inspect the resulting SVN tree after a run

### Phase 4: Real CLI support for `releasey-20-prepare-rc`

Goal:

- execute the real prepare-RC path against harness-managed Git and SVN state

Tasks:

- run the real CLI for:
  - `verify-source-ref-checks`
  - `prepare-rc`
  - `cleanup-dev-svn-rcs`
  - `build-source-rc`
  - `create-rc-materialization-tag` where applicable
  - `sync-draft-github-release`
  - `finalize-rc-vote-materials`
- keep GitHub and registry actions mocked via `gh` and `docker` shims
- ensure `finalize-rc-vote-materials` uses the real rendered email templates and real manifest
- verify that the resulting local SVN working copy contains the staged RC vote materials

Done when:

- the prepare-RC `act` scenario no longer depends on mocked CLI results
- the resulting RC vote-manifest, source RC files, and email content are inspectable from the
  workspace

### Phase 5: Real CLI support for `releasey-30-release-version`

Goal:

- execute the real finalization path against harness-managed Git and SVN state

Tasks:

- run the real CLI for:
  - `release-version`
  - `publish-source-release-svn`
  - `prune-older-line-releases`
  - `create-final-tag`
  - `update-moving-tags`
  - `finalize-draft-github-release`
- keep `gh` and `docker` mocked
- verify non-rollback behavior for moving tags
- inspect the resulting local SVN release tree

Done when:

- the release-version `act` scenario validates real Git and SVN side effects

### Phase 6: Component rollout

Goal:

- apply the same pattern to component repositories after the tooling repo path is stable

Tasks:

- add real-CLI `act` scenarios for components incrementally
- keep component-specific TODO steps mocked until each component implements them
- use the same inspectable workspace conventions

Done when:

- each component can opt into the same `act` + real-CLI harness path for the release steps it has
  actually implemented

## Scenario model changes likely needed

The current scenario model is good enough for mocked CLI flow, but real-CLI execution will likely
need a few explicit additions:

- a way to declare that `uv run ... buildish-release-tooling ...` should execute the real CLI
- Git fixture declarations for:
  - branches
  - tags
  - optional extra commits
- local SVN fixture declarations for:
  - preset initial state via `workflow.svn_fixture.initial_state`
  - optional explicit `dev_dist_entries`
  - optional explicit `release_dist_entries`
  - configurable `rc_number`, `version`, and `other_version` for preset expansion
- optional GPG fixture material

The simplest first step is to add preset-style initial-state values before introducing fully custom
fixture graphs.

For SVN, likely presets include:

- `absent`
- `empty`
- `preexisting-previous-rc`
- `preexisting-current-rc`
- `preexisting-future-rc`
- `preexisting-other-version`

For Git, likely presets include:

- `empty`
- `release-branch-only`
- `current-version-rc-present`
- `previous-version-rc-present`
- `future-version-rc-present`
- `other-line-release-present`

Those preset enums should be designed as shortcuts for common cases, not as the only possible
representation. Later, scenarios should still be able to override them with explicit branch, tag,
and directory declarations when needed.

These should remain scenario-level concerns and not leak into production `release-config.yaml`.

## Expected summary improvements

As real CLI execution becomes the default for `act` scenarios, the harness summaries should become
more trustworthy and more detailed.

The following data should be surfaced consistently in command summaries:

- component repository URL
- source commit SHA
- RC tag and final tag
- RC tag target commit SHA
- release branch
- worktree dirty state for local harness runs
- authoritative ASF SVN staging URL
- source artifact URLs and checksums
- secondary artifact URLs and checksums when present

## RC vote-manifest follow-up

The current RC vote-manifest already carries:

- source commit SHA
- optional materialized commit SHA
- source and secondary artifacts
- per-artifact Git commit SHA
- tooling provenance including tooling repository URL

One likely follow-up improvement is to add explicit source repository identity for the released
component:

- repository slug or name
- repository URL

That information is useful both for human summaries and for machine-auditable provenance.

## Risks

Main risks:

- runner image drift or missing system tools
- overcomplicating the scenario model
- accidentally turning the `act` backend into a full GitHub runner emulator

Mitigations:

- keep `gh` and `docker` mocked
- add real CLI execution only where it materially improves confidence
- keep the custom backend for low-level deterministic tests
- introduce a custom runner image only when the default `act` image becomes a real blocker

## Recommendation

Proceed with the phased plan.

The highest-value next implementation step is:

1. Phase 1
2. Phase 2 for `releasey-10` and `releasey-40`
3. Phase 3 for real local SVN support

That order gives early value without requiring the most complex workflow first.
