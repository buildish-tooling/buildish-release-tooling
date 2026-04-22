---
title: Test Suite Layout
description: "Maintainer guide to core, adapter, command, workflow, and harness verification."
weight: 110
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

# Test Source Tree

The suite combines deterministic unit tests, local Git/GPG/SVN integration tests, command tests,
schema and documentation checks, and GitHub workflow simulation.

## Release tests

- `tests/release/core/` covers provider-neutral config dependencies, naming, versioning, state,
  manifests, and vote-profile rules.
- `tests/release/platforms/github/` covers GitHub checks, refs, Releases, direct publication, and
  candidate publication.
- `tests/release/foundations/asf/` covers ASF dist behavior and URL enforcement.
- `tests/release/signing/` covers isolated OpenPGP import and signing.
- `tests/release/commands/` covers bounded CLI operations, lifecycle resolution, exact candidate
  promotion, publication, artifact registration, voting materials, and verification.
- `tests/release/workflows/` checks lifecycle workflow policy and handoff structure.

The remaining modules directly under `tests/release/` cover shared adapters and the deeper RC,
reproducibility, report, bundle, schema, and generated-documentation contracts.

## Harness tests

`tests/harness/` covers scenario loading, job selection, runtime behavior, command tracing, and
`act`-based workflow execution. Checked-in scenarios under `buildish-release-tooling/harness/`
exercise direct release, candidate publication, exact promotion, and read-only candidate
verification.

Harness tests replace external writes with controlled local state. They do not verify repository
settings, GitHub Environment reviewers, service availability, or real credentials.

## Legal and shared-library tests

Tests directly under `tests/` cover release legal reports, legal-file generation and distribution,
archive safety, downloads, parsing, I/O, and wheel contents.

## Running checks

Use the narrowest relevant test while iterating, then run the repository gate:

```bash
make check
```

Changes to published site content or routes also require `make site-check-local` from the Buildish
site repository. If a check needs unavailable external tooling, report that limitation rather than
treating an unexecuted check as passing.
