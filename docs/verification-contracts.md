---
title: Manifests And Verification
description: "Stable candidate, vote-package, release, and optional reproducibility contracts."
weight: 70
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

# Manifests And Verification

Release Tooling uses typed JSON documents to bind independently executable workflow phases. A
manifest is evidence about an exact release object; it is not evidence that a governance vote or
approval succeeded.

## Stable lifecycle manifests

`CandidateManifestV1` records:

- candidate identity and immutable tag;
- exact source revision;
- declared artifact names, sizes, and digests;
- platform publication records;
- verification evidence and tooling provenance.

The GitHub candidate workflow attaches the exact document as `candidate-manifest.json`. Its SHA-256
is the cross-run selection handle used by independent verification, external approval systems, and
promotion.

`VotePackageV1` optionally binds rendered opening and result material to one candidate-manifest
digest. The selected `generic` or `asf` profile must match authored config. The package intentionally
contains no vote outcome.

`ReleaseManifestV1` records the final release. A direct release has no promoted-candidate reference.
A promoted release identifies the exact candidate manifest and includes typed evidence for each
promoted artifact:

- `byte-identical` for files with identical digest sets;
- `registry-identity` for an unchanged immutable package or image identity;
- `same-source-revision` for hosting-platform snapshots generated from candidate and final tags at
  the same commit.

The generated field-by-field contracts are in the [Reference](../reference/).

## GitHub candidate verification

`verify-github-candidate` accepts the exact candidate tag and expected lowercase SHA-256. It
downloads `candidate-manifest.json` from that release and verifies:

- the manifest bytes match the supplied digest;
- the component, version, candidate number, tag, and source commit agree;
- the tag and GitHub Release resolve to the declared identity;
- each declared uploaded asset has the expected name, size, and digest;
- the candidate publication state matches its recorded lifecycle state.

The read-only `release-verify-candidate.yml` workflow is a reusable independent-verification entry
point. It retains the verified manifest and command result as same-run workflow artifacts.

## Final-release verification

Final verification compares the exact resolved direct or promotion state with the final tag, draft
or public GitHub Release, expected body, and asset inventory. Publication revalidates that same state
instead of assuming an earlier job's observation remains valid.

The final manifest is attached without clobbering. Attachment then verifies the downloaded bytes,
size, and digest and rechecks the final release. If attachment fails after publication, the release
may be public without its final manifest until a convergent rerun completes; workflows and monitors
should treat that as an incomplete release operation.

## Workflow handoff integrity

Same-run state and command results move as JSON files through workflow artifacts. Producers emit a
SHA-256 through job output; every release-mutating consumer verifies the downloaded bytes before
acting. Workflow artifacts are transport, not a durable cross-run approval record.

Candidate promotion instead re-downloads the manifest from the candidate publication and verifies
the digest supplied by the external gate. Neither verification nor promotion discovers a candidate
by a moving alias such as "latest RC".

## Optional full RC verification

`verify-rc` is the deeper signed-source and reproducibility subsystem used by release compositions
that publish an explicit source candidate. It verifies a signed RC vote manifest, trust-root data,
the staged source artifact, and configured secondary artifacts. `inspect-repro` reads a saved report
and curated inspection bundle without rerunning the build.

These versioned contracts remain supported:

- `verify-rc` report `schema_version: "1"`;
- inspection bundle `bundle_schema_version: "1"` and `inspection-bundle.json`;
- `inspect-repro --json` output `schema_version: "1"`.

Reports record environment-variable names, not values. Supported comparison modes include exact
bytes for file-like artifacts, repository-tree comparison for Maven repositories, and immutable
platform-digest or provenance-only comparison for OCI images. Incompatible changes require a new
explicit schema version.

The optional full RC verifier does not make the generic candidate lifecycle ASF-specific. A
component selects it when its artifact or foundation policy requires that additional evidence.

## Trust boundary

Digest verification detects substitution relative to a value obtained through an independent,
trusted channel. A digest published beside the object it protects is useful for consistency but is
not an independent authenticity proof. Projects remain responsible for deciding how candidate
manifest digests, signing-key fingerprints, and approval results reach the promotion authority.
