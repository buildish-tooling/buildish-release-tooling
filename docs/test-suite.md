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

The suite is intentionally mixed:

- pure unit tests for deterministic logic
- integration tests with local Git, SVN, and GPG sandboxes
- harness and workflow simulation tests for GitHub Actions behavior

## Shared support and fixtures

- `tests/support.py`: common sandbox creation, fake launcher helpers, fixture config copying, and
  environment builders used across most integration tests
- `tests/fixtures/components/`: checked-in example component repositories used by component-matrix
  and wrapper-smoke tests

The support module is the right place for reusable fake GitHub launchers, local repo builders, and
 sandbox helpers. Tests should avoid open-coding those mechanics repeatedly.

## Unit-focused modules

- `test_release_state.py`: pure version and release-line derivation
- `test_prepare_rc_state.py`: RC state derivation from config and Git metadata
- `test_config.py`: config loading and validation rules
- `test_manifest.py`: JSON manifest writing
- `test_summary.py`: Markdown summary rendering
- `test_command_logging.py`: credential redaction in logged commands
- `test_github_checks.py`, `test_github_git_refs.py`, `test_github_releases.py`: GitHub API payload
  shaping and response handling
- `test_git_repo_unit.py` and `test_asf_svn_unit.py`: low-level adapter command construction

These tests should stay fast and isolated. They are the preferred place for branching logic,
validation, and formatting rules that do not need a real repository or subprocess.

## Integration-heavy command coverage

- `test_commands.py`: end-to-end command behavior using local Git repos, local SVN repos, fake
  `gh` launchers, and optional GPG state
- `test_source_artifact.py`: reproducible source archive generation across real Git clones
- `test_git_repo.py`: Git repository behavior against real test repositories
- `test_asf_svn.py`: SVN promotion and pruning against local test repositories
- `test_gpg_signing.py`: detached signing against temporary GPG homes

`test_commands.py` is the broadest integration file. It validates that command handlers compose the
smaller adapter modules correctly and keep their manifest and summary contracts stable.

## Harness and workflow simulation coverage

- `test_harness.py`: repo-local harness execution without `act`
- `test_harness_act.py`: workflow rewriting, `act` backend behavior, and real/rewritten `uv` shim
  behavior
- `test_harness_config.py`: harness config resolution and local override files
- `test_component_matrix.py`: fixture components that prove policy variation across repositories

These tests exist because the release workflows are not just a Python CLI. They also depend on:

- checked-in wrapper scripts
- GitHub Actions execution shape
- harness-specific workflow rewriting
- component policy differences

## How to choose a test location

- Put pure data-derivation checks in the smallest unit test module that owns the logic.
- Put command contract checks in `test_commands.py` when the behavior crosses multiple adapters.
- Put wrapper or workflow behavior in `test_component_matrix.py`, `test_harness.py`, or
  `test_harness_act.py`.
- Put reusable setup code in `tests/support.py` instead of duplicating sandbox machinery.

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
