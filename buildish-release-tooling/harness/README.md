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

# buildish-release-harness

`buildish-release-harness` is the integration-test harness for Buildish release automation.

Its purpose is to validate what Buildish release workflows and release CLI commands would do,
including transient failures and reruns, without needing live GitHub or registry access.

## Scope

The harness is designed around three layers:

1. a runner-agnostic scenario model
2. one or more execution backends
3. normalized assertions over traces, summaries, manifests, Git state, and ASF SVN state

The scenario model should stay reusable across backends. The same scenario should be usable with:

- the current custom backend
- the current `act`-based workflow smoke-test backend

## Current implementation

The current repository contains the first working slice:

- a scenario model in `src/buildish_release_tooling/harness/models.py`
- a YAML loader in `src/buildish_release_tooling/harness/scenario.py`
- a backend dispatcher in `src/buildish_release_tooling/harness/backend.py`
- a custom execution backend in `src/buildish_release_tooling/harness/runtime.py`
- an `act` execution backend in `src/buildish_release_tooling/harness/act_backend.py`
- a generic shim entrypoint in `src/buildish_release_tooling/harness/shim_entrypoint.py`
- a CLI entrypoint:
  - `buildish-release-harness run <scenario.yaml>`
  - `buildish-release-harness run <scenario.yaml> --seed-from <workspace>`
  - `buildish-release-harness run-sequence <scenario-a.yaml> <scenario-b.yaml> ...`
  - `buildish-release-harness rerun-failed <scenario.yaml> <workspace>`

The current custom backend supports:

- disposable workspaces under `build/`
- initial workspace files
- initial disposable Git repositories with an initial commit
- job and step execution with dependency ordering
- persisted job status for rerun support
- generic command shims with scripted responses
- deterministic fail-once or fail-on-N behavior
- trace capture in JSONL format
- per-step `GITHUB_STEP_SUMMARY` files
- a `BASH_ENV` hook that defines function shims such as `gh()` and `docker()`

The current backend does not yet implement:

- target-family-specific assertions for Maven, Docker Hub, or PyPI publication results

The `act` backend is intentionally narrow. It is meant to execute the real checked-in workflow
YAML files with enough harness rewriting to make them deterministic and locally runnable. It is not
intended to become a replacement GitHub Actions runner.

## Directory layout

`buildish-release-tooling/harness/` is the standard home for committed harness-facing files in a Buildish
component repository.

Recommended layout:

```text
buildish-release-tooling/
  release-config.yaml
  release-tooling.sh
  RELEASE-PROCESS.md
  harness/
    README.md
    release-harness.yaml
    release-harness.local.yaml   # gitignored, optional
    scenarios/
    fixtures/
```

That keeps harness files together instead of scattering them between the repository root and
multiple subdirectories.

Component repositories do not need to create `buildish-release-tooling/harness/` until they
actually add committed harness scenarios, fixtures, or config files there.

## Repository bindings

Workflow testing needs stable local bindings for:

- the workflow repository under test
- explicitly checked out companion repositories such as `buildish-tooling/buildish-release-tooling`

The harness uses a committed `buildish-release-tooling/harness/release-harness.yaml` file plus an
optional gitignored `buildish-release-tooling/harness/release-harness.local.yaml` file next to it.

The committed file should stay machine-neutral. It should contain only logical repository identity
and local checkout policy, not machine-specific absolute paths.

Committed example:

```yaml
schema_version: "1"

self_repository:
  repository_id: buildish-tooling/buildish-mammoth-cache
  local_checkout_mode: when_repository_omitted

repository_overrides:
  buildish-tooling/buildish-release-tooling:
    local_checkout_mode: always
```

Optional local override example:

```yaml
self_repository:
  local_path: /home/snazy/devel/buildish-tooling/buildish/buildish-mammoth-cache

repository_overrides:
  buildish-tooling/buildish-release-tooling:
    local_path: /home/snazy/devel/buildish-tooling/buildish/buildish-release-tooling
```

Resolution rules:

1. load `release-harness.yaml`
2. if `release-harness.local.yaml` exists, merge it on top
3. determine the repository root from the config location
4. if a repository binding still has no `local_path`, derive it as `../<repo-name>` relative to the
   repository root
5. resolve explicit relative `local_path` values from the repository root as well

For the standard layout above, `self_repository.repository_id: buildish-tooling/buildish-mammoth-cache`
defaults to `../buildish-mammoth-cache` from the component repository root, which resolves back to
the component repository itself. `buildish-tooling/buildish-release-tooling` defaults to
`../buildish-release-tooling`.

This keeps the committed config portable while still making the common sibling-repository layout
work out of the box.

The current custom backend does not yet parse workflow YAML or execute `actions/checkout`, so these
repository bindings are currently resolved and inspectable through the harness CLI and are intended
to be consumed by the workflow-aware `act` backend.

## Running with `uv` and `uvx`

From the `buildish-release-tooling` repository root, run the harness with the checked-out project
environment via `uv run`:

```bash
uv run --frozen buildish-release-harness --help
uv run --frozen buildish-release-harness run buildish-release-tooling/harness/scenarios/basic-success.yaml
```

To run it as a tool from the local checkout via `uvx`, point `--from` at the repository root:

```bash
uvx --from /home/snazy/devel/buildish-tooling/buildish/buildish-release-tooling \
  buildish-release-harness --help
uvx --from /home/snazy/devel/buildish-tooling/buildish/buildish-release-tooling \
  buildish-release-harness run \
  /home/snazy/devel/buildish-tooling/buildish/buildish-release-tooling/buildish-release-tooling/harness/scenarios/basic-success.yaml
```

The `uv run` form is the preferred choice while developing the harness in this repository. The
`uvx --from` form is useful when another repository or script wants to invoke the harness from a
pinned local checkout.

To inspect resolved repository bindings from a committed harness config:

```bash
uv run --frozen buildish-release-harness resolve-config /path/to/buildish-release-tooling/harness/release-harness.yaml
uvx --from /home/snazy/devel/buildish-tooling/buildish/buildish-release-tooling \
  buildish-release-harness resolve-config \
  /path/to/buildish-release-tooling/harness/release-harness.yaml
```

## Running the `act` backend

The committed lifecycle scenarios use the `act` backend and run the real checked-in workflow YAML
through a rewritten disposable workspace. The harness replaces same-run GitHub workflow artifact
actions and GitHub Release operations with deterministic workspace-local implementations.

Example:

```bash
uv run --frozen buildish-release-harness run \
  buildish-release-tooling/harness/scenarios/release-candidate.yaml
```

To seed one workflow run from a prior workspace's Git, GitHub Release, and optional SVN state:

```bash
uv run --frozen buildish-release-harness run \
  buildish-release-tooling/harness/scenarios/release-promote.yaml \
  --seed-from /path/to/previous/workspace
```

To run multiple workflows in order, with each run seeded from the previous workspace:

```bash
uv run --frozen buildish-release-harness run-sequence \
  buildish-release-tooling/harness/scenarios/release-candidate.yaml \
  buildish-release-tooling/harness/scenarios/release-candidate.yaml \
  buildish-release-tooling/harness/scenarios/release-promote.yaml
```

This sequence publishes retained `rc1` and `rc2` candidates, then promotes the explicitly selected
`rc2` candidate and its exact manifest digest.

That requires:

- Docker
- either the standalone `act` executable on `PATH`
- or GitHub CLI plus the `gh act` extension

The harness prefers the standalone `act` executable when it is present. If `act` is missing, it
falls back to the installed `gh-act` extension binary itself instead of invoking `gh act`, so the
outer `gh` wrapper is not part of the long-running process chain.

The harness also passes explicit medium runner-image mappings for Ubuntu runners so `act` does not
stop on its first-run interactive image-selection prompt. It passes `--rm` so failed runs do not
leave `act` job containers behind, and `--bind` so generated harness files such as local composite
checkout actions are visible inside the runner workspace.

The rewritten workflow in the disposable workspace is clearly marked as harness-generated and keeps
a verbatim `*.original.yml` copy of the source workflow next to it for comparison.

The `act` backend retains GitHub Releases and their assets across seeded workflow runs. It also
prepares a harness-owned local ASF SVN repository under
`.buildish-release-harness/svn/repository/`, checks out an inspectable working copy under
`.buildish-release-harness/svn/working-copy/`, and rewrites the workspace
`buildish-release-tooling/release-config.yaml` to use `file://...` URLs that point at that local
repository.

Example installation via GitHub CLI extension on Linux and macOS:

```bash
gh extension install https://github.com/nektos/gh-act
gh act --help
```

Once installed, the harness can consume that extension without any additional wrapper script or
shell alias. If you prefer the standalone `act` binary, install it separately and ensure
`act --help` works on your `PATH` before running the harness.

The `act` backend scenarios can also be rerun from an existing workspace:

```bash
uv run --frozen buildish-release-harness rerun-failed \
  buildish-release-tooling/harness/scenarios/release-promote.yaml \
  /path/to/existing/workspace
```

For workflow scenarios, the `workflow.svn_fixture` block can pre-seed the local ASF SVN repository
with a small preset-style initial state such as:

- `absent`
- `empty`
- `preexisting-current-rc`
- `preexisting-previous-rc`
- `preexisting-future-rc`
- `preexisting-other-version`

Scenarios can also add explicit `dev_dist_entries` and `release_dist_entries` under the configured
`asf_dist_dev_base` and `asf_dist_release_base` roots.

Scenarios for an explicit ASF composition can seed repository-relative SVN files through
`workflow.svn_fixture.repository_files`.

When a run uses `--seed-from` or `run-sequence`, the harness applies SVN directories and
`repository_files` additively:

- existing carried-over SVN directories are kept
- existing carried-over SVN files are not overwritten
- missing fixture paths are still created

That lets one scenario stay runnable both standalone and as part of a multi-workflow chain.

## Inspecting a workspace

Every harness run prints the workspace root to `stderr` and includes an `inspectable_paths` object
in its JSON output.

Important paths:

- `workspace_root`
  - the primary mutable Git checkout for the workflow repository under test
- `rewritten_workflows`
  - the rewritten workflow YAML that `act` actually executed
- `repo_sources`
  - staged repository sources used by local checkout overrides and imports
- `git_origins`
  - harness-owned local Git origins
- `self_git_origin`
  - the local origin used as `origin` for the workflow repository under test
- `svn_repository`
  - the harness-owned local ASF SVN repository used by real-CLI scenarios
- `svn_working_copy`
  - an inspectable checkout of that local SVN repository, refreshed after each run or rerun
- `git_checkouts`
  - reserved for additional mutable Git checkouts when scenarios need them
- `step_summaries`
  - individual step summaries
- `job_summaries`
  - GitHub-like per-job concatenated summaries

For the current `act` backend, the main repository under test should be inspected at the workspace
root, not under `.buildish-release-harness/`.

Harness CLI exit codes:

- `0` if the scenario completed without failed or blocked jobs
- `1` if the scenario ran but reported failed or blocked jobs
- `2` if required local runner tooling such as `act` or the installed `gh-act` extension binary is unavailable

For `run`, `run-sequence`, and `rerun-failed`, the harness also writes human-facing diagnostics to
`stderr`:

- the created workspace path under `build/harness/scenario.<timestamp>.<suffix>/`
- backend progress lines such as config loading, workflow rewriting, and the final `act` command
- live mirrored `act` stdout and stderr while the workflow is running
- a short failed/blocked job summary when the scenario did not succeed
- the captured `.buildish-release-harness/act-stderr.log` contents when an `act`-backed run fails

Each workspace also contains:

- per-step captured summaries under `.buildish-release-harness/summaries/`
- aggregated per-job summaries under `.buildish-release-harness/job-summaries/`

The per-job files concatenate non-empty step summaries in execution order, which is much closer to
how GitHub Actions presents one job summary to users.

## Design rules

The harness intentionally does not try to emulate all of GitHub Actions.

The preferred strategy is:

- keep `git` real whenever possible
- keep detached local ASF SVN repositories real whenever possible
- keep local filesystem mutations real
- replace service-facing tools such as `gh`, `docker`, and optionally `gpg` with deterministic
  shims
- optionally intercept JVM launchers through a fixture `JAVA_HOME` whose `bin/java` and
  `bin/javac` entries are shims

This gives high-value integration coverage without trying to become a full workflow runner.

## Backends

The harness exposes one scenario model with multiple execution backends.

- `custom`
  - executes harness-declared jobs and shell steps directly
  - owns the current deterministic rerun and fail-once behavior
- `act`
  - executes real checked-in workflow YAML through `act`
  - relies on harness-generated workflow rewrites, local composite actions, and command shims

Backends should share:

- scenario loading
- command-trace format
- summary capture format
- result normalization

Backends do not need to share the same internal execution model.

## Scenario model

A scenario YAML file describes the initial state and the expected external behavior.

The current scenario model supports:

- `name`
- `env_capture`
- `env`
- `secrets`
- `workspace_files`
- `git_repositories`
- `tool_behaviors`
- `jobs`

High-level shape:

```yaml
name: example
env_capture:
  - EXAMPLE_FLAG
env:
  EXAMPLE_FLAG: enabled
workspace_files:
  - path: repo/README.md
    content: |
      hello
tool_behaviors:
  gh:
    - match:
        argv_prefix: [api, repos/demo]
      result:
        stdout: "{\"ok\":true}\n"
        summary: "api call succeeded\n"
jobs:
  - id: prepare
    steps:
      - id: call-gh
        cwd: repo
        run: |
          gh api repos/demo
          printf 'summary ok\n' >> "$GITHUB_STEP_SUMMARY"
```

See the checked-in examples in `buildish-release-tooling/harness/scenarios/`.

This repository currently includes:

- the lightweight custom-backend examples:
  - `basic-success.yaml`
  - `fail-once-rerun.yaml`
- committed `act` scenarios for the four lifecycle workflows:
  - `release-direct.yaml`
  - `release-candidate.yaml`
  - `release-promote.yaml`
  - `release-verify-candidate.yaml`
- a committed `buildish-release-tooling/harness/release-harness.yaml` binding file for the
  tooling repo itself

For `act` scenarios, the workflow block can also declare:

- `real_cli_commands`
  - exact `buildish-release-tooling` subcommands that should run for real through `uv run ...`
    instead of going through mocked shim behavior
- `repository_fixture`
  - lightweight Git state to seed into the workflow repository checkout before the workflow runs
  - currently supports:
    - `tags`
    - `branches`
- `release_config`
  - complete scenario-local release configuration installed only in the disposable workspace

Example:

```yaml
workflow:
  path: ../../../.github/workflows/release-verify-candidate.yml
  harness_config: ../release-harness.yaml
  inputs:
    candidate_tag: v9.9.9-rc1
    candidate_manifest_digest: <exact-sha256>
  real_cli_commands:
    - verify-github-candidate
  repository_fixture:
    tags:
      - name: v9.9.9-rc1
```

## Shim strategy

The harness uses two interception mechanisms:

- executable `PATH` shims for cross-process interception
- Bash function shims loaded through `BASH_ENV` for Bash-based `run:` steps

The Bash function shims are useful because they keep the interception logic close to the original
step script and allow future step-level directives in comments. They also propagate to nested
non-interactive Bash invocations because `BASH_ENV` is inherited.

They do not replace executable `PATH` shims, because other code may invoke the same tools from:

- non-Bash processes
- absolute paths
- wrapper scripts

For the `act` backend, the harness also provides:

- a `bash` executable shim that redirects `GITHUB_STEP_SUMMARY` to harness-owned summary files and
  then mirrors the content back to the original step-summary path
- a purpose-built `uv` shim that can either:
  - delegate to the real `uv` installed in the runner, or
  - route `uv run --project ... buildish-release-tooling ...` through scripted harness behavior
    or a direct Python fallback
- direct summary writes from mocked `buildish-release-tooling` invocations into the harness-owned
  step summary file, so the captured summaries stay meaningful even when the CLI call itself is
  scripted

## Trace format

Each intercepted tool invocation appends one JSON object to the command trace file:

- `tool`
- `argv`
- `cwd`
- `env`
- `exit_code`
- `stdout`
- `stderr`
- `delegated`

The trace is stored at:

- `<workspace>/.buildish-release-harness/command-trace.jsonl`

Per-step summaries are stored at:

- `<workspace>/.buildish-release-harness/summaries/<job-id>__<step-id>.md`

## Java and wrapper tools

Wrapper launchers such as:

- `./gradlew`
- `./mvnw`
- SDKMAN `gradle`
- SDKMAN `mvn`

can be intercepted reliably by using a fixture `JAVA_HOME` whose `bin/java` entry is a shim.
Where necessary, the same fixture JDK can also provide `bin/javac`.

A plain `PATH`-based `java` shim remains useful as a fallback when a launcher resolves `java`
through `command -v java`, but `JAVA_HOME` is the more deterministic mechanism.

## Rerun model

The custom backend persists job statuses in the workspace and supports rerunning only:

- failed jobs
- downstream jobs that were previously blocked by those failures

That mirrors the Buildish goal of approximating GitHub's `Rerun failed jobs` behavior while
keeping the partially mutated workspace intact.

## `act` backend

The `act` backend reuses the same scenario model. It adds:

- workflow-YAML execution through `act`
- generated local composite actions
- the same command shims
- best-effort step-summary capture through a test-only `bash` shim and `BASH_ENV`

That backend should complement the current custom backend, not replace it.

### `act` workflow preparation

The `act` backend prepares a disposable repository workspace before invoking `act`:

1. materialize the workflow repository under test from the locally bound repository source
2. stage any explicitly bound companion repositories under
   `.buildish-release-harness/repo-sources/`
3. generate local composite actions under `.buildish-release-harness/actions/`
4. generate workflow-rewritten YAML under `.github/workflows/`
5. invoke `act` against the rewritten workflow file and a generated `workflow_dispatch` event payload

### Composite-action overrides

The `act` backend intentionally avoids reimplementing marketplace actions. Instead, it rewrites the
small set of action usages that Buildish release workflows currently depend on:

- `astral-sh/setup-uv@...`
  - rewritten to a harness-generated local composite action that behaves as a no-op for mocked
    scenarios
  - left intact for scenarios that declare `workflow.real_cli_commands`, so the runner gets a real
    `uv` installation
- `actions/checkout@...` for explicitly bound companion repositories
  - rewritten to a harness-generated local composite action that performs a deterministic local
    checkout from `.buildish-release-harness/repo-sources/...`

The self-checkout case with `repository` omitted is not rewritten. The `act` backend instead
materializes the workflow repository under test into the workspace before `act` starts, so the
workflow still operates on local repository state and does not depend on the repository having been
pushed to a remote.

### Local checkout semantics

For explicit companion repositories such as `buildish-tooling/buildish-release-tooling`, the generated local
checkout action currently supports:

- `local-git-clone`
  - clone from a staged local Git repository and optionally `checkout` the requested `ref`
- `local-source-tree`
  - copy a plain working tree without `.git`

Buildish release workflows should generally prefer `local-git-clone`, because local refs and Git
history can matter for release logic and for "not yet pushed" local commits.

### Bootstrap step injection

For each workflow job, the `act` backend injects one bootstrap shell step before the original job
steps. That bootstrap step configures later steps by writing to `GITHUB_ENV`:

- prepend the harness shims directory to `PATH`
- expose the harness state file path
- expose the original runner `PATH` for real-tool delegation

For each `run:` step, the `act` backend also injects stable harness metadata into `env`:

- `BUILDISH_HARNESS_JOB_ID`
- `BUILDISH_HARNESS_STEP_ID`

That metadata is consumed by the `bash` shim so step summaries can be redirected to deterministic
paths under `.buildish-release-harness/summaries/`.

### Current `act` limitations

The current `act` backend is deliberately limited:

- it assumes `workflow_dispatch` workflows
- it only rewrites the small action set listed above
- rerunning failed jobs currently selects failed jobs plus downstream dependents, but still relies
  on `act` job selection semantics rather than a full GitHub rerun emulator
- it does not try to emulate GitHub environments, permissions, or concurrency perfectly
