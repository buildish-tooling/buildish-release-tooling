---
title: Codebase Layout
description: "Guide to the production Python package and where each release-tooling responsibility lives."
weight: 100
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

# Production Source Tree

This page maps the production Python code in `src/apache_buildish_release_tooling/`.

The package is organized around one rule:

- the CLI is the supported external contract
- the Python module layout is internal implementation detail
- modules should stay focused on one release concern at a time

## Entry points and command flow

- `release/__main__.py`: Python module entrypoint for `python -m apache_buildish_release_tooling.release`
- `release/cli.py`: argparse command registration and argument normalization
- `release/commands/`: command handlers plus command-local orchestration helpers grouped by workflow family

The `release/commands/` package is intentionally the orchestration layer. It should decide:

- which repo state to load
- which external adapters to call
- which manifest and summary files to write

It should not absorb low-level protocol details that belong in a dedicated adapter module.

## Configuration and shared models

- `config.py`: loads `release-config.yaml` and validates secure/non-production target rules
- `models.py`: pydantic models for component policy and derived command state
- `prepare_rc_state.py`: derives the authoritative RC state from config, Git refs, and version input
- `release_state.py`: pure version, tag, release-line, and pruning logic

If a behavior is mostly deterministic data derivation and does not need I/O, it should usually
land in `prepare_rc_state.py` or `release_state.py` instead of in one of the command handlers.

## External system adapters

- `git_repo.py`: local Git worktree operations
- `asf_svn.py`: SVN URL and working-copy operations
- `github_checks.py`: GitHub check-run and commit-status policy
- `github_git_refs.py`: low-level GitHub Git ref and annotated-tag API calls
- `github_releases.py`: draft/final GitHub Release API calls and asset upload/download helpers
- `gpg_signing.py`: detached signing and private-key import
- `dockerhub.py`: Docker Hub moving-alias publication
- `process.py`: subprocess execution and normalized command errors
- `command_logging.py`: redacted command rendering for logs and failures

These modules exist to keep credentials, CLI flags, and protocol rules out of higher-level release
logic. New integration code should usually start in one of these adapters.

## Release artifacts and human-facing output

- `source_artifact.py`: reproducible source archive creation and checksum helpers
- `rc_vote_manifest.py`: authoritative RC vote manifest structure plus staged-artifact readers
- `manifest.py`: JSON manifest writing used by most commands
- `summary.py`: Markdown step-summary helpers
- `email_templates.py`: vote-result, vote-request, and announce email rendering

The release flow has two output classes:

- machine-consumed manifests in JSON
- human-consumed summaries, emails, signatures, and checksums

Keeping those concerns in dedicated modules helps command handlers stay readable.

## Harness package

The `harness/` package is a local workflow simulator used by tests and release-playbook reviews.

- `harness/cli.py` and `harness/__main__.py`: harness CLI entrypoints
- `harness/config.py`: checked-in harness config plus local override support
- `harness/models.py`: scenario, repository, and workspace model types
- `harness/runtime.py`: shared workspace layout, disposable checkout creation, and generic runtime helpers
- `harness/backends/custom.py`: simple local-exec backend for synthetic shell scenarios
- `harness/backends/act/`: `act`-driven GitHub Actions simulation backend
- `harness/uv_shim.py`: shared `uv` shim rendering used by both harness backends
- `harness/scenario.py`: scenario file loading
- `harness/shim_entrypoint.py`: Python entrypoint for shell-tool shims
- `harness/backend.py`, `harness/backends/`, and `harness/errors.py`: backend dispatch, interface, and user-facing harness errors

Shared shell-shim behavior should prefer `harness/uv_shim.py` or another helper instead of being
copied into both backends.

## Practical placement rules

- Add new CLI flags in `release/cli.py` and consume them in the relevant `release/commands/` module.
- Add new release-state derivation in `prepare_rc_state.py` or `release_state.py` when possible.
- Add new external API or CLI interaction in the corresponding adapter module.
- Add new manifest or summary formatting in `manifest.py`, `summary.py`, or `email_templates.py`.
- Add new harness-only behavior under `harness/`, not in the production CLI modules.

When in doubt, prefer a new helper module over growing one command module or one harness backend
with another protocol-specific block.
