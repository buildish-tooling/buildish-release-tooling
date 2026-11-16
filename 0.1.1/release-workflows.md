---
title: Workflow Composition
description: "How component-owned workflows compose release CLI operations and approval boundaries."
weight: 30
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

# Workflow Composition

Components own thin workflows that call the CLI. The CLI does not choose GitHub Environment names,
repository secret names, runner groups, or an organization's approval policy.

The checked-in Buildish workflows show a GitHub-authoritative, platform-generated-source
composition. Other components can split or combine jobs differently as long as they preserve the
state, integrity, and permission boundaries below. See
[Self-releasing Buildish Release Tooling](../self-release/) for the complete reference deployment
and its external GitHub and PyPI settings.

## Current workflows

| Workflow | Purpose | Mutation boundary |
| --- | --- | --- |
| `release-candidate.yml` | Publish the next exact candidate and durable manifest | candidate tag and GitHub prerelease/draft |
| `release-promote.yml` | Promote one named candidate manifest and publish its distributions | final tag, GitHub Release, and PyPI |
| `release-testpypi.yml` | Exercise `DirectReleaseState`, build an exact version, and publish it directly to TestPyPI | TestPyPI only |
| `release-verify-candidate.yml` | Independently verify one named candidate | read-only |

The generic direct GitHub lifecycle is retained as
`buildish-release-tooling/harness/workflows/release-direct.yml` for component authors and harness
coverage. It is not a live self-release workflow in this repository.

All external actions use immutable commit pins. Workflow-level permissions default to
`contents: read`; only jobs that mutate GitHub refs or Releases receive `contents: write`.

## Handoff rules

Small scalar identities may cross a job boundary through `GITHUB_OUTPUT`. Complete state crosses the
boundary as a JSON file:

- direct state for direct publication;
- candidate state inside candidate publication;
- promotion state for final candidate promotion;
- publication results for final manifest creation.

The producing job emits a SHA-256 for each release-critical state or result. A consuming job verifies
the exact bytes after downloading the workflow artifact and before invoking a mutation command.

`release_notes.path_template`, when configured, is resolved against the exact selected source
commit. The path must contain `{version}` exactly once and identify a non-empty, bounded UTF-8
Markdown regular file. State and manifests carry the exact Markdown, source path, and SHA-256 so a
privileged publication job never rereads mutable workspace notes. Omitting `release_notes` is the
explicit generic no-custom-notes mode; a configured but missing file is not treated as empty.

GitHub workflow artifacts are only a same-run transport. Cross-run promotion uses
`candidate-manifest.json` attached to the candidate GitHub Release. The external gate retains the
candidate tag and manifest SHA-256; the promotion workflow requires both.

## Concurrency

Mutation workflows use one non-canceling group per repository and exact version:

```yaml
concurrency:
  group: buildish-release-${{ github.repository }}-${{ inputs.version }}
  cancel-in-progress: false
```

This prevents candidate and promotion runs for the same version from racing. The direct TestPyPI
workflow uses its own non-cancelling group for each exact version. Waiting is intentional:
cancelling a run after it created a tag or staged a release does not roll that external state back.

The CLI itself does not implement a distributed lock. Maintainer-shell invocations and custom
workflows must provide equivalent serialization when they can target the same release identity.

## GitHub Environments

The self-release workflows use `testpypi` and `pypi` environments for their respective Trusted
Publishing jobs. Candidate signing and candidate publication additionally use the
`release-candidate` environment. That environment must be restricted to `main` and should require
review where the maintainer model permits it. Selected release source is data in those jobs; the
CLI and configuration executed across signing and repository-write boundaries come from the
workflow revision identified by `github.workflow_sha`.

If project policy says approval is required before all release mutations, inspect every job with
`contents: write`, including tag creation and final manifest attachment, and give each the intended
`environment:`. Environment-scoped secrets gate only jobs that actually declare that environment.

The local harness validates workflow shape and command behavior. It cannot prove that required
reviewers, deployment branches, or environment secrets are configured correctly in GitHub.

## Source checks and build jobs

An optional `source.checks` block selects a hosting-platform check gate. The implemented
`platform: github` adapter can require exactly named successful or intentionally skipped check runs
or legacy status contexts on the exact source commit. When `trusted_workflow_path` is configured,
legacy statuses and same-name checks from other producers do not satisfy the gate: the check must
belong to the GitHub Actions check suite for that workflow path and optional event/branch. The
self-release config binds `Required Checks` to a `push` run of `.github/workflows/ci.yml` on `main`.

`source.require_default_branch_ancestor: true` adds a separate source-authorization boundary. The
resolved source commit must already be reachable from the configured default branch. The Buildish
self-release configs enable it for protected `main`; arbitrary branch code therefore cannot become
release source merely because it reproduces a check display name.

Same-run component tests are workflow-owned jobs, not a boolean promise in release config. A thin
component workflow may run them before the mutation jobs, may rely on named results from its normal
CI workflow, or may compose both controls. Omitting `source.checks` means the release CLI applies no
external platform-status gate; it does not claim that tests ran elsewhere.

The self-release candidate workflow builds a wheel and sdist twice with the selected commit's
`SOURCE_DATE_EPOCH`, requires byte-identical output, rebuilds the wheel from the sdist, and smoke
tests both distributions. It adds checksums and detached OpenPGP signatures before candidate
publication. Promotion downloads and verifies those candidate bytes; only the wheel and sdist are
sent to PyPI, while the complete signed set remains attached to GitHub. See
[Source artifacts and signing](../source-artifacts-and-signing/).

Before production upload, an unprivileged job compares PyPI's existing version state with the exact
candidate distributions. An absent or matching partial publication may proceed; a complete match
skips upload; any unexpected filename, size, or SHA-256 stops the workflow. The OIDC publisher uses
`skip-existing` only after that preflight, and a later unprivileged job requires the complete exact
set before final-manifest attachment. This supports failed-job recovery without accepting unrelated
existing bytes. The explicit PyPI publication adapter performs those JSON API reads through one
pooled, bounded HTTP session and converts its result into provider-neutral manifest references.
Its authored secondary-target block binds the exact project, JSON and Integrity service URLs, and
Trusted Publisher repository/workflow/environment. Selecting the target makes complete publication
and attestation evidence mandatory in the stable final manifest. A release configuration permits
one secondary target of each provider kind; use separate configurations for PyPI and TestPyPI.
Components that invoke
`verify-pypi-attestations` from an installed tool use the `buildish-release-tooling[pypi]` extra.

The direct TestPyPI workflow uses the same absent, matching-partial, complete, and conflicting-state
preflight. Its retained `DirectReleaseState` and producer digests bind the source decision and exact
distribution bytes. Both TestPyPI and production verification also download the PEP 740 provenance,
select bundles for the configured repository/workflow/environment identity, and cryptographically
verify each attestation against its retained distribution with pinned `pypi-attestations` tooling.
Production promotion requires a PyPI Publish Attestation for every distribution and retains the
selected exact evidence as GitHub Release assets. Bundles from unrelated publishers are ignored.
The fetched mutable provenance remains in the temporary publication artifact for diagnosis.
Durable evidence assets use a reserved `buildish-verification-evidence--` prefix. If a run stops
after those immutable assets are uploaded but before the stable manifest is attached, an all-jobs
rerun temporarily tolerates only the exact configured evidence names in that reserved namespace.
The immutable attachment step
then requires the regenerated bytes to match exactly before attaching the manifest; unrelated or
conflicting assets still stop recovery.

## External gates and automation

The candidate workflow stops after publishing a verified candidate. The promotion workflow starts
from explicit immutable inputs. Nothing between them assumes how approval was obtained.

An automated voting or approval service can therefore dispatch promotion only after its own policy
passes. It must preserve and submit the exact candidate tag and manifest SHA-256. It must not replace
those inputs with "latest candidate" discovery.

The current workflows expose `workflow_dispatch`. A component may add its own `workflow_call`
wrapper, bot, or GitHub App integration without changing the CLI contracts.

## Other hosting platforms

GitHub is the only implemented hosting-platform adapter today; PyPI is a separate secondary
publication adapter. Provider-neutral state and manifests carry generic identities and typed
extension points. A future GitLab, Forgejo, package-index, or registry adapter should add its own
config, evidence validation, and workflow integration rather than placing provider fields in the
core models or another adapter.
