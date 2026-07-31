---
title: Candidate Release And Promotion
description: "Publish retained candidates and promote one exact candidate manifest to a final release."
weight: 20
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

# Candidate Release And Promotion

The candidate lifecycle publishes one or more immutable candidates and promotes one explicitly
selected candidate to the final release. Voting or approval is external: Buildish records exact
candidate evidence but does not decide whether a candidate passed.

This separation lets a manual decision, a GitHub Issue bot, a foundation-specific voting process, or
another approval system gate final publication without changing candidate identity or promotion
semantics.

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
  mode: candidate
candidate:
  label: rc
  start_number: 1
  visibility: public-prerelease
  retention: retain-published
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

The default candidate number is one. With this configuration, version `1.2.3` starts at
`v1.2.3-rc1`.

## Create candidates

Run `.github/workflows/release-candidate.yml` with the exact version and optional source ref or
candidate-label override. The workflow:

1. resolves the next unused candidate number and exact source commit;
2. verifies configured source checks on that commit;
3. creates the immutable candidate tag;
4. stages the GitHub candidate and any configured artifacts;
5. creates and attaches `candidate-manifest.json`;
6. verifies the tag, release metadata, asset inventory, manifest bytes, size, and SHA-256;
7. applies configured visibility.

`public-prerelease` produces a public GitHub prerelease. `draft` retains a non-public draft. A later
run for the same version and label selects the next number after the highest existing matching tag;
published candidates are retained.

For example, a rejected or superseded `v1.2.3-rc1` can remain available while a new run publishes
`v1.2.3-rc2` from another exact commit.

## Zero-based numbering

Projects that prefer RC0 can choose it explicitly:

```yaml
candidate:
  label: rc
  start_number: 0
  visibility: draft
  retention: retain-published
```

That configuration begins at `v1.2.3-rc0`. Numbering is project policy; it has no effect on the
unsuffixed final version or final tag.

## Independent verification

Run `.github/workflows/release-verify-candidate.yml` with:

- the exact candidate tag;
- the lowercase SHA-256 of `candidate-manifest.json`.

The read-only workflow downloads the durable manifest from the candidate GitHub Release and checks
the supplied digest, candidate identity, source commit, release metadata, and asset identities. It
also retains the verified manifest and result as a workflow artifact for inspection.

## Exact promotion

After the external gate accepts a candidate, run `.github/workflows/release-promote.yml` with:

- `version`, such as `1.2.3`;
- `candidate_tag`, such as `v1.2.3-rc2`;
- `candidate_manifest_digest`, the exact lowercase SHA-256 selected by the gate.

Promotion never discovers "the latest RC". It downloads and verifies the named candidate manifest,
downloads each candidate asset named by that manifest, verifies the bytes, and creates
`PromotionState`. The remaining jobs create the final tag, stage and verify the final release,
publish it, and attach `release-manifest-v1.json`.

The final manifest records the promoted candidate and its manifest digest. Per-artifact promotion
evidence distinguishes byte-identical assets, immutable registry identities, and hosting-platform
snapshots generated from tags at the same exact source revision.

## Optional vote package

Voting is not a precondition of candidate publication. A component that wants reusable voting
materials can add a generic profile:

```yaml
vote_materials:
  profile: generic
  release_name: Example
  verification_guide_url: https://example.org/releases/verify/
  instructions: Verify the candidate manifest and all referenced artifacts.
```

Dispatch the candidate workflow with `vote_profile: generic`, or call `create-vote-package` over the
exact candidate manifest. `VotePackageV1` binds the rendered opening/result templates to that
manifest's digest. Vote duration, voter eligibility, quorum, veto rules, and outcome remain the
responsibility of the external authority.

The [optional ASF profile](../asf-profile/) provides ASF-specific terminology and trust-root data
without changing the generic candidate or promotion contracts.
