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
state, integrity, and permission boundaries below.

## Current workflows

| Workflow | Purpose | Mutation boundary |
| --- | --- | --- |
| `release-direct.yml` | Publish an exact final release without an RC | final tag and GitHub Release |
| `release-candidate.yml` | Publish the next exact candidate and durable manifest | candidate tag and GitHub prerelease/draft |
| `release-promote.yml` | Promote one named candidate manifest | final tag and GitHub Release |
| `release-verify-candidate.yml` | Independently verify one named candidate | read-only |

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

This prevents direct, candidate, and promotion runs for the same version from racing. Waiting is
intentional: cancelling a run after it created a tag or staged a release does not roll that external
state back.

The CLI itself does not implement a distributed lock. Maintainer-shell invocations and custom
workflows must provide equivalent serialization when they can target the same release identity.

## GitHub Environments

The checked-in workflows do not prescribe GitHub Environment names. A component may attach an
environment to every write job, only to final publication, or to additional build/signing jobs.

If project policy says approval is required before all release mutations, inspect every job with
`contents: write`, including tag creation and final manifest attachment, and give each the intended
`environment:`. Environment-scoped secrets gate only jobs that actually declare that environment.

The local harness validates workflow shape and command behavior. It cannot prove that required
reviewers, deployment branches, or environment secrets are configured correctly in GitHub.

## Source checks and build jobs

`source.checks` chooses whether the release composition runs selected-ref tests itself, requires an
existing successful GitHub check on the exact source commit, or both. A workflow must not silently
skip both checks; the config schema rejects that composition.

The checked-in workflows publish no separately built artifact. A component that selects
`source.snapshot.mode: built-asset` or other produced artifacts adds component-specific build,
verification, and artifact-transfer jobs, then passes the exact files to the relevant stage command.
See [Source artifacts and signing](../source-artifacts-and-signing/).

## External gates and automation

The candidate workflow stops after publishing a verified candidate. The promotion workflow starts
from explicit immutable inputs. Nothing between them assumes how approval was obtained.

An automated voting or approval service can therefore dispatch promotion only after its own policy
passes. It must preserve and submit the exact candidate tag and manifest SHA-256. It must not replace
those inputs with "latest candidate" discovery.

The current workflows expose `workflow_dispatch`. A component may add its own `workflow_call`
wrapper, bot, or GitHub App integration without changing the CLI contracts.

## Other hosting platforms

GitHub is the only implemented platform adapter today. Provider-neutral state and manifests carry
generic identities and typed extension points. A future GitLab or Forgejo adapter should add its own
config, publication extension, and workflow integration rather than placing provider fields in the
core models.
