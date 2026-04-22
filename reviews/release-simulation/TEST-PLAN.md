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

# Release Simulation Test Plan

This directory records a logical release simulation review of `buildish-release-tooling`.

The simulation follows the current checked-in workflow drafts and Python command handlers, but does
not execute real releases. The goal is to let another reviewer or another AI chat repeat the same
exercise against the same scenario matrix and turn it into a broader scenario test suite later.

## Method

- Follow the checked-in workflow job graph, not the aspirational process docs.
- For each workflow job, trace the exact `buildish-release-tooling` CLI invocation.
- Re-resolve state from the same Python helpers the workflows use.
- For `prepare-rc`, treat the `resolve-state` job as the source of the authoritative `rc_tag` for
  later jobs in the same workflow run.
- For `release-version`, treat the exact-version draft GitHub Release as the authoritative source
  of the selected RC number.
- Record whether the scenario succeeds, partially succeeds, or fails.
- Record whether rerunning an individual job is safe after a transient error.
- Treat known `TODO` jobs as gaps in the actual release path, not as implemented behavior.

## Scenario Matrix

| Scenario | Focus | Component / workflow family |
| --- | --- | --- |
| `01-tooling-initial-release` | Baseline `0`-secondary-artifact release | `buildish-release-tooling` |
| `02-same-version-follow-up-rc` | Existing RCs for the same exact version | generic tooling logic |
| `03-parallel-minor-rcs-same-major` | Parallel RCs on `1.2.x` and `1.3.x` | generic tooling logic |
| `04-lower-minor-after-higher-minor-release` | `1.2.3` after `1.3.4` | moving-tag logic |
| `05-single-secondary-artifact` | `1` secondary artifact target | `buildish-no-gradle-wrapper-jar` |
| `06-multiple-secondary-artifacts` | `2+` secondary artifact targets | `buildish-site-pipeline` |
| `07-detached-materialization` | Detached materialization commit path | `buildish-mammoth-cache` |
| `08-job-rerun-resumability` | Transient-job-failure rerun safety | cross-cutting |

## Per-Scenario Review Template

Each scenario review should capture:

1. Assumptions and initial repository / dist state.
2. Workflows traversed.
3. Jobs traversed in order.
4. Exact CLI command invoked by each job.
5. State transitions in Git, ASF SVN, and GitHub Releases.
6. Behavior if another RC / release exists on the same major line.
7. Behavior if the job is rerun after a transient failure.
8. Findings, with code or workflow references.

## Scope Notes

- The review includes the checked-in consumer workflows in the actual component repositories because
  secondary artifact behavior only becomes visible through those component-specific job graphs.
- The review focuses on the currently implemented commands plus the actual draft job graph. It does
  not assume future `TODO` jobs will exist.
- When a component-specific secondary artifact job is still a placeholder, simulate the intended
  state transition logically but record the workflow as incomplete.
