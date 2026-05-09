---
title: Test Suite Layout
description: "Guide to the unit, integration, and harness tests that protect buildish-release-tooling."
weight: 110
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

# Test Source Tree

This page maps the test code in `tests/` and explains what each layer is meant to prove.

The suite now splits first by product area:

- `tests/release/`: release CLI, release state, adapters, manifests, and release workflow contracts
- `tests/harness/`: the local workflow harness and Actions simulation behavior

Within those areas, the suite is intentionally mixed:

- pure unit tests for deterministic logic
- integration tests with local Git, SVN, and GPG sandboxes
- harness and workflow simulation tests for GitHub Actions behavior

## Shared support and fixtures

- `tests/support.py`: common sandbox creation, fake launcher helpers, fixture config copying, and
  environment builders used across most integration tests
- `tests/release/commands/support.py`: shared integration-test base class and helpers for release
  command contract coverage
- `tests/fixtures/components/`: checked-in example component repositories used by component-matrix
  and wrapper-smoke tests

The support module is the right place for reusable fake GitHub launchers, local repo builders, and
 sandbox helpers. Tests should avoid open-coding those mechanics repeatedly.

## Release unit and adapter coverage

- `tests/release/test_release_state.py`: pure version and release-line derivation
- `tests/release/test_prepare_rc_state.py`: RC state derivation from config and Git metadata
- `tests/release/test_config.py`: config loading and validation rules
- `tests/release/test_manifest.py`: JSON manifest writing
- `tests/release/test_summary.py`: Markdown summary rendering
- `tests/release/test_command_logging.py`: credential redaction in logged commands
- `tests/release/test_command_credentials.py`: git credential wiring for push/delete helper commands
- `tests/release/test_github_checks.py`, `tests/release/test_github_git_refs.py`,
  `tests/release/test_github_releases.py`: GitHub API payload shaping and response handling
- `tests/release/test_git_repo_unit.py` and `tests/release/test_asf_svn_unit.py`: low-level
  adapter command construction
- `tests/release/test_artifact_registration.py`: unit coverage for artifact registration helpers
- `tests/test_release_legal_distributions.py`, `tests/test_release_legal_report.py`, and
  `tests/test_release_legal_generation.py`: preliminary release-legal discovery, report policy,
  and artifact generation
- `tests/release/test_component_matrix.py`: fixture-backed release policy variation across component
  repositories

These tests should stay fast and isolated. They are the preferred place for branching logic,
validation, and formatting rules that do not need a real repository or subprocess.

## Release command integration coverage

Release command integration tests now live under `tests/release/commands/`, split by command area
instead of one large `test_commands.py`:

- `test_rc_preparation.py`: `prepare-rc` and related RC staging behavior
- `test_release_publication_versioning.py`, `test_release_publication_svn.py`,
  `test_release_publication_git_tags.py`, and `test_release_publication_github.py`: release
  publication, final tagging, SVN publish, GitHub release, and pruning flows
- `test_materialization.py`: RC content materialization and materialization tags
- `test_secondary_targets.py`: secondary publication targets such as moving tags and GitHub assets
- `test_artifact_registration_*.py`: `record-artifact` command coverage split by artifact kind
- `test_verification_*.py`: `verify-rc` and `inspect-repro` command coverage split by behavior
- `test_vote_materials.py`: RC vote material generation and publication steps
- `test_branching.py`: release branch creation flows
- `test_atr.py`: ATR publication and reporting commands

This layer validates that the command handlers compose the smaller adapter modules correctly and
keep their manifest, summary, and side-effect contracts stable.

Additional release integration modules remain outside the command split when they cover a single
adapter or end-to-end subsystem:

- `tests/release/test_source_artifact.py`: reproducible source archive generation across real Git
  clones
- `tests/release/test_git_repo.py`: Git repository behavior against real test repositories
- `tests/release/test_asf_svn.py`: SVN promotion and pruning against local test repositories
- `tests/release/test_gpg_signing.py`: detached signing against temporary GPG homes

## Harness and workflow simulation coverage

- `tests/harness/test_harness.py`: repo-local harness execution without `act`
- `tests/harness/test_harness_act_runtime.py` and
  `tests/harness/test_harness_act_workflow.py`: workflow rewriting, `act` backend behavior, and
  real/rewritten `uv` shim behavior
- `tests/harness/test_harness_config.py`: harness config resolution and local override files
- `tests/harness/test_harness_job_selection.py`: job selection and dependency behavior for harness
  runs

These tests exist because the release workflows are not just a Python CLI. They also depend on:

- checked-in wrapper scripts
- GitHub Actions execution shape
- harness-specific workflow rewriting
- job graph and selection behavior

## How to choose a test location

- Put release-only logic under `tests/release/` and harness-only logic under `tests/harness/`.
- Put pure data-derivation checks in the smallest unit test module that owns the logic.
- Put release command contract checks in the matching file under `tests/release/commands/` when the
  behavior crosses multiple adapters.
- Put wrapper or workflow simulation behavior in the `tests/harness/` modules.
- Put reusable setup code in `tests/support.py` or `tests/release/commands/support.py` instead of
  duplicating sandbox machinery.

## Temporary state and test discipline

Integration tests write under `build/tests/` so that:

- the repo root stays inspectable
- failures leave useful local artifacts
- Git, SVN, GPG, and harness state can be debugged without touching external systems

When adding new tests:

- prefer deterministic local fixtures over network calls
- prefer fake CLIs over patching deep command internals when testing orchestration
- keep secrets synthetic and scoped to the sandbox
- make `make check` the expected local and CI gate
