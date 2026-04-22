---
title: Codebase Layout
description: "Maintainer guide to core release logic, adapters, commands, verification, and the workflow harness."
weight: 100
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

# Production Source Tree

Production release code lives in `src/buildish_release_tooling/release/`. The CLI and documented
file contracts are supported integration surfaces; Python module paths are internal.

## Provider-neutral core

- `core/config.py` defines component identity, source policy, lifecycle, candidate policy,
  artifacts, signing, publication composition, and tags.
- `core/models.py`, `core/state.py`, and `core/naming.py` derive provider-neutral release identity
  and state.
- `core/manifests.py` defines manifest references and promotion evidence.
- `direct_release.py`, `candidate_release.py`, and `manifests.py` define stable lifecycle state and
  top-level manifests.

Foundation or hosting-provider fields must not be added to these modules merely because the first
implementation needs them. Use an explicit adapter and typed extension point.

## Hosting platforms and foundations

- `platforms/github/` contains GitHub config, API models, refs, Releases, checks, text, lifecycle
  helpers, and commands.
- `foundations/asf/` contains ASF-named config, dist behavior, and manifests.
- `signing/openpgp.py` contains the OpenPGP implementation independently of any foundation.

A future GitLab or Forgejo implementation belongs under `platforms/`. A future foundation policy
belongs under `foundations/`. Core orchestration may depend on an adapter interface or typed union,
but must not silently adopt one adapter's vocabulary.

## CLI orchestration

- `cli.py` registers commands and normalizes arguments.
- `commands/lifecycle.py` resolves direct, candidate, and promotion state.
- `commands/release_publication.py` and `commands/rc_preparation.py` orchestrate bounded release
  steps.
- `commands/vote_materials.py` creates optional vote packages.
- `commands/artifact_registration.py` and `artifact_registration/` handle typed secondary
  artifacts.
- `command_manifests.py`, `manifest.py`, and `summary.py` write machine and human outputs.

Commands should remain independently composable. They may create or revalidate one bounded unit of
external state, but workflow policy and approval sequencing belong in component-owned workflows.

## Verification

`verification/` implements signed-source, secondary-artifact, reproducibility, inspection-bundle,
and report contracts. Artifact-kind implementations are split between `artifact_registration/kinds/`
and `verification/secondary/`; reproduction diagnosis lives under `verification/inspection/`.

Provider-specific release verification remains with its adapter. Generic manifest and promotion
evidence remains in the core.

## Harness

`src/buildish_release_tooling/harness/` is a test-only workflow simulator. It runs synthetic scenarios
or checked-in GitHub workflows through `act`, using local shims and inspectable workspace state for
external mutations. It is validation evidence for workflow shape and command composition, not a
production release backend and not proof of GitHub Environment settings.

## Placement rules

- Put deterministic identity and lifecycle rules in `core/`.
- Put GitHub, GitLab, Forgejo, or another host's protocol and data under `platforms/<provider>/`.
- Put ASF or another foundation's policy-specific fields and operations under
  `foundations/<foundation>/` with explicit type names and discriminator values.
- Put credentials in runtime integration, never authored config values.
- Add CLI flags in `cli.py` and bounded orchestration in the relevant `commands/` module.
- Update schemas, public contract docs, and tests together when a supported file contract changes.
