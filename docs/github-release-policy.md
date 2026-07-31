---
title: GitHub Release Adapter
description: "GitHub-specific publication behavior for direct, candidate, and promoted releases."
weight: 50
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

# GitHub Release Adapter

GitHub is the first implemented hosting platform. A component selects it explicitly with a
`github-release` publication target; GitHub is not part of the provider-neutral release identity or
manifest model.

```yaml
publication:
  authoritative:
    kind: github-release
    repository: example/example
  convenience: []
  secondary: []
```

`repository` may be omitted when the workflow repository is the target. GitHub credentials and
GitHub Environment names belong to the component workflow, not this authored config.

## Direct releases

The direct path creates an immutable final tag, prepares a draft release, verifies it, publishes it
with `prerelease=false`, and attaches `release-manifest-v1.json`. An existing tag or release is
accepted only when it represents the same resolved state; conflicting state fails closed.

See [Direct release](../direct-release/) for the complete workflow.

## Candidate releases

A candidate uses an immutable tag such as `v1.2.3-rc1`. After staging and verification, its GitHub
Release is either:

- a public prerelease when `candidate.visibility` is `public-prerelease`; or
- an unpublished draft when visibility is `draft`.

The candidate body identifies it as a candidate. `candidate-manifest.json` is a durable release
asset and records the exact source revision, publication, and artifact inventory. Candidate
numbering defaults to one and can be configured to start at zero.

## Promotion

Promotion names the exact candidate tag and candidate-manifest SHA-256. It does not select the most
recent tag. The adapter re-reads the candidate Release, verifies its manifest and every declared
asset, then stages and publishes the final Release.

The final tag is unsuffixed by default. The final Release is a separate publication; promoting a
candidate does not rename a prerelease or mutate the candidate tag.

## Release assets

GitHub-generated source archives are identified by the immutable tag and source commit. They are not
uploaded assets and do not have stable bytes across candidate and final tag names. The release
manifest therefore records `same-source-revision` promotion evidence for this mode.

Separately built files are explicit release assets. The adapter checks name, size, and configured
digests, uploads without clobbering, and requires byte-identical evidence during candidate
promotion. An unexpected existing asset is a conflict, not an invitation to overwrite it.

## Permissions and serialization

The checked-in workflows default to `contents: read` and grant `contents: write` only to jobs that
create tags or mutate Releases. Mutation workflows share a non-canceling repository-and-version
concurrency group.

Components may add GitHub Environments to any job boundary required by their policy. The CLI does
not infer or enforce repository Environment configuration. See
[Workflow composition](../release-workflows/) for the handoff and approval-boundary rules.

## Provider boundary

GitHub-specific config, API models, release text, refs, and commands live under the GitHub adapter.
A future GitLab or Forgejo adapter should implement the same core lifecycle boundaries with its own
publication records and workflow integration. It must not reinterpret GitHub Release identifiers
as provider-neutral identities.
