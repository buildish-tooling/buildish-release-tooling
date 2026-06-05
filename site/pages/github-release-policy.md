---
title: "GitHub Release Policy"
description: "How Buildish models GitHub candidate and final release pages under ASF release policy."
---

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

Buildish treats GitHub Releases as convenience metadata and optional convenience asset mirrors.
The authoritative ASF source release is the material published under ASF `dist/release`.

## Candidate releases

Candidate tags use this shape:

```text
v<version>-<candidate-label><number>
```

The default label is `rc`, and the default `candidate_start_number` is `0`, so the first default
candidate for `1.2.3` is `v1.2.3-rc0`.

Projects can choose another label for a run:

```text
buildish-release-tooling prepare-rc --candidate-label alpha 1.2.3
```

With `candidate_start_number: 1`, the first alpha candidate is `v1.2.3-alpha1`. Once matching tags
exist, Buildish uses the next number after the highest existing tag for the same version and label.

## Candidate visibility

`sync-draft-github-release` supports:

- `draft`: the default; the candidate GitHub Release remains non-public.
- `public-prerelease`: publishes the candidate GitHub Release with GitHub `prerelease=true`.

Public candidate pages are not official ASF releases. The generated text says this directly and
identifies the candidate tag. Incubating public candidate pages also include the incubating
disclaimer.

## Final releases

Final GitHub Releases are convenience pages for already-approved ASF releases. Buildish rewrites the
body before publication so it points to the authoritative ASF source release, source artifact,
checksums, signature, ASF KEYS URL, and release verification guide. Final GitHub Releases are
published with GitHub `prerelease=false`.

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
