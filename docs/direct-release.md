---
title: Direct Release
description: "Publish one exact final GitHub release without creating a release candidate."
weight: 10
---

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

# Direct Release

The direct lifecycle turns one exact source revision into the final tag and final GitHub Release in
one manually dispatched workflow. It does not create a candidate, require a vote, or introduce a
candidate-shaped placeholder in final release state.

"One click" means one workflow dispatch. The workflow still separates resolution, source checks,
tag creation, staging, verification, publication, and manifest attachment so a component can place
policy boundaries between those jobs.

## Minimal configuration

```yaml
component:
  id: example
  display_name: Example
versioning:
  scheme: semver
  final_tag_template: "v{version}"
source:
  selection: explicit-ref-or-default-branch
  default_branch: main
  snapshot:
    mode: platform-generated
  checks:
    run_selected_ref_tests: false
    require_release_branch_ci: true
lifecycle:
  mode: direct
artifacts:
  produced: []
  checksums: []
publication:
  authoritative:
    kind: github-release
    repository: example/example
tags:
  final_mode: exact-source-commit
  moving: []
policy_profiles: {}
```

This example treats GitHub as authoritative and relies on the source archives GitHub generates from
the immutable final tag. It publishes no separately built source artifact.

## Dispatch

Run `.github/workflows/release-direct.yml` with:

- `version`: the exact final version, for example `1.2.3`;
- `source_ref`: an optional exact branch, tag, or commit allowed by the configured source-selection
  policy.

When `source_ref` is omitted, the example configuration resolves `main`. Resolution records the
exact commit; later jobs use that commit identity rather than re-resolving a moving branch.

## Workflow phases

1. `resolve` creates `DirectReleaseState` with the release identity, exact source commit, final tag,
   and artifact policy.
2. `verify-source` checks the configured GitHub check-run/status requirement on that exact commit.
3. `create-final-tag` creates or revalidates the immutable final tag.
4. `stage` creates or completes the draft final GitHub Release.
5. `verify-final` compares the observed tag, release metadata, and assets with the resolved state.
6. `publish` makes the exact release public or confirms that an identical publication already
   exists.
7. `manifest` creates `release-manifest-v1.json`, validates both workflow handoff digests, attaches
   the manifest without clobbering an existing asset, and revalidates the release.

Same-run JSON files move through GitHub workflow artifacts. Every privilege-bearing consumer checks
the SHA-256 emitted by the producing job before acting.

## Reruns and conflicts

The mutation commands are convergent for identical state:

- an identical tag, draft release, public release, or manifest attachment reports an
  `already-complete` outcome where applicable;
- an existing tag at another commit, mismatched release body, unexpected asset, size mismatch, or
  digest mismatch fails closed;
- asset upload never uses clobber behavior.

The workflow uses non-canceling concurrency keyed by repository and version. A second run waits
instead of cancelling a run that may already have changed external release state.

## Variations

- Use a [separately built and signed source artifact](../source-artifacts-and-signing/) when the
  hosting-platform snapshot is not sufficient.
- Add `environment:` to the jobs selected by project policy; see
  [Workflow composition](../release-workflows/).
- Create a release branch separately with `create-release-branch` when a component needs maintained
  release lines. The direct lifecycle itself does not require one.
- Use the [candidate lifecycle](../candidate-release/) when publication must wait for an external
  approval or vote over an exact candidate.
