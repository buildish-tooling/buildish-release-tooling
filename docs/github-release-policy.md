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

# GitHub Release Policy

Buildish treats GitHub Releases as convenience metadata and optional convenience asset mirrors.
The authoritative ASF source release is the material published under ASF `dist/release`.

## Candidate releases

The candidate flow derives tags as:

```text
v<version>-<candidate-label><number>
```

Defaults preserve the existing RC convention:

```text
candidate label: rc
candidate_start_number: 0
first tag: v1.2.3-rc0
```

Projects can choose another candidate label per run:

```text
buildish-release-tooling prepare-rc --candidate-label alpha 1.2.3
```

If `candidate_start_number: 1` is configured, the first alpha candidate becomes
`v1.2.3-alpha1`. Once matching tags exist, Buildish always uses the next number after the highest
existing tag for the same version and label.

## Candidate visibility

`sync-draft-github-release` supports two visibility modes:

- `draft`: the default; creates or updates a non-public GitHub Release.
- `public-prerelease`: publishes the candidate GitHub Release with GitHub `prerelease=true`.

Public candidate GitHub Releases are not official ASF releases. Their generated body says this
explicitly and identifies the candidate tag. Incubating projects also include the incubating
disclaimer when candidate release pages are public.

## Final releases

Final publication rewrites the GitHub Release body before publishing it as a final release. The
final body:

- does not use draft placeholder wording
- links to the authoritative ASF source release directory
- links to the source artifact, `.sha512`, and `.asc`
- links to the ASF KEYS URL
- links to the release verification guide
- states that GitHub Release assets are convenience artifacts only
- includes the incubating disclaimer for incubating projects

Final GitHub Releases are published with `prerelease=false`.

## Release workflow concurrency

Release workflows that mutate RC or final-release state should serialize by component repository and
exact version. Use the same non-canceling concurrency group for both the Prepare RC workflow and the
Release Version workflow:

```yaml
concurrency:
  group: buildish-release-${{ github.repository }}-${{ inputs.version }}
  cancel-in-progress: false
```

Using the same group for both workflows prevents an accidental double-dispatch or rerun from racing
against the same RC tags, SVN staging directories, GitHub Releases, or final publication state.
`cancel-in-progress: false` is intentional: a later release run should wait rather than cancel a run
that may already hold partially updated external release state.

## GitHub Environment approval for release mutations

Projects that require approval before release mutations should put the relevant GitHub Environment
on every job that mutates release state, not only on jobs that read environment-scoped secrets. In
Buildish release workflows this usually means reviewing all jobs with:

```yaml
permissions:
  contents: write
```

If the project policy is "approval before all release mutations", those jobs should declare an
appropriate `environment:` as well. This includes jobs that create or update RC tags, materialization
tags, final tags, and GitHub Releases, even when they currently use `github.token` rather than an
environment-scoped PAT.

Projects may use one environment for all release writes or split the policy into clearer stages, for
example `rc-staging-release-secrets` and `final-release-publication`. The important part is that the
workflow YAML matches the intended approval boundary.

The local `act` harness does not validate GitHub Environment protection semantics. Treat harness
results as workflow-shape regression evidence only; review `environment:` declarations in workflow
YAML and verify the actual approval rules in GitHub repository settings.
