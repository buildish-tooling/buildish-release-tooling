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
with `prerelease=false`. For immutable releases, attach evidence and the sealed
`release-manifest-v1.json` before publication, then verify without uploading. An existing tag or release is
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

Candidate manifests record the canonical tag URL rather than GitHub's temporary `untagged-*`
draft URL. That publication reference remains stable when the draft becomes a public prerelease.
Finalization revalidates the manifest against the published Release before reporting success.

## Promotion

Promotion names the exact candidate tag and candidate-manifest SHA-256. It does not select the most
recent tag. The adapter re-reads the candidate Release, verifies its manifest and every declared
asset, then stages the final Release as a draft. Configured secondary packages are published and
verified before evidence and the sealed manifest are attached to that draft. Finalization requires
the producer-emitted manifest SHA-256 and publishes GitHub last.

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

## Immutable release sealing

GitHub locks release assets when an immutable release is published. All assets, including durable
verification evidence and the final manifest, must be attached while the Release is a draft.
The CLI's `attach-github-release-assets --immutable` flag means exact, no-clobber attachment; it
cannot add assets to a GitHub Release that is already locked.

`create-release-manifest` accepts a staging result and emits `ReleaseManifestV1` for a draft.
The manifest binds its canonical tag URL, Release ID and creation timestamp, exact artifact
identities, and configured secondary verification evidence. Its GitHub extension records the
observed draft snapshot, with `draft=true` and no `published_at`; its `created_at` is the Release
creation time. Publication time is observed later in the publication command result, never predicted
or written back into sealed bytes. Readback permits only the expected visibility/publication-time
transition; source, Release identity, URL, artifact inventory and evidence remain checked.

Use `publish-github-final-release --require-manifest-digest SHA256` to require the attached sealed
manifest's exact digest before and after finalization. The checked-in promotion workflow always
uses that gate. Existing `ReleaseManifestV1` files created after publication retain their original
publication-timestamp semantics and remain readable. Creating from a published result retains
those semantics; creating from a draft result records the sealed draft snapshot. Consumers that
assumed every manifest describes an already-published Release must update that assumption.

For GitHub's lifecycle restrictions, see [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
