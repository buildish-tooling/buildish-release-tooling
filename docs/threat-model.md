---
title: Threat Model
description: "Draft security model for buildish-release-tooling release orchestration, verification, and harness surfaces."
weight: 120
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

# Threat Model

## 1. Header

- Project: `buildish-release-tooling`
- Bound source revision: `e66582254e07cfb1eabe375474953e1f57180439`
- Project version at this revision: `0.1.0`
- Threat model date: `2026-06-05`
- Threat model authors: Codex, based on repository documentation and source inspection
- Status: draft, pending maintainer review on `2026-06-05`
- Version binding: this threat model is versioned alongside the project. A report against project
  version N should be triaged against the model as it stood at version N, not against later HEAD.
- Reporting cross-reference: findings that violate claimed properties in [Security properties the
  project provides](#8-security-properties-the-project-provides) should be reported to
  [security@buildish.org](mailto:security@buildish.org) per the repository `SECURITY.md`; findings that
  fall under [Out of scope](#3-out-of-scope-explicit-non-goals) or
  [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide)
  may be closed citing this document.
- Provenance legend: *(documented)* means supported by repository docs or tests; *(maintainer)* means
  maintainer-confirmed but not yet otherwise documented; *(inferred)* means inferred from source or
  project structure and awaiting maintainer confirmation.
- Draft confidence: 33 documented / 0 maintainer / 35 inferred claims.

`buildish-release-tooling` is a Python CLI component used by Buildish projects to orchestrate Apache
release workflows. It selects and validates source commits, creates release branches and tags,
builds and stages release candidates, writes signed vote-manifest data, publishes final release
materials, verifies staged release candidates, records secondary artifacts, and simulates GitHub
Actions workflows through a local harness. *(documented)*

## 2. Scope And Intended Use

Primary intended uses: *(documented)*

- Run Buildish release workflow commands from GitHub Actions or a maintainer-controlled shell.
- Produce and stage source release candidate artifacts, signatures, checksums, manifests, vote
  materials, and final release metadata.
- Verify source and secondary release artifacts against signed vote manifests and configured
  reproducibility profiles.
- Run a local release harness for testing workflow behavior and release-playbook changes.

Deployment contexts: *(documented)*

- Python 3.11+ command-line tool invoked through `uv run --project` or `uvx`.
- GitHub Actions release jobs with checked-out component repositories and scoped credentials.
- Maintainer-controlled local development and verification machines.
- Local harness workspaces that simulate GitHub Actions, Git, SVN, and release-tool behavior.

Caller expectations: *(documented)*

- The caller is a trusted maintainer, release manager, GitHub Actions workflow, or verifier.
- The target component repository, its selected source ref, and its `release-config.yaml` are data
  inputs, not automatically trusted release facts.
- The tool is not intended to be exposed as a network service or as a direct interface for arbitrary
  untrusted users. *(inferred)*

Component-family table:

| Family | Representative entry points | External process, filesystem, network, or environment use | In model? |
| --- | --- | --- | --- |
| Release CLI orchestration | `buildish-release-tooling create-release-branch`, `prepare-rc`, `release-version` | Reads Git worktree, component config, environment hooks, and writes manifests and summaries | yes |
| RC artifact staging and signing | `create-source-artifact`, `build-source-rc`, `finalize-rc-vote-materials` | Runs Git, GPG, SVN; reads credentials; writes staged artifacts and signed manifests | yes |
| Final publication | `publish-source-release-svn`, `create-final-tag`, `finalize-draft-github-release`, moving tags and aliases | Mutates ASF SVN, GitHub refs/releases, and Docker Hub aliases | yes |
| Verification and inspection | `verify-rc`, `inspect-repro` | Downloads or reads release materials; may execute configured rebuild commands after explicit mode selection | yes |
| Secondary artifact registration | `record-artifact` | Reads local files or external package registries; writes registration fragments | yes |
| Local harness | `buildish-release-harness`, workflow shims, `act` backend | Creates local workspaces, rewrites workflows, invokes subprocesses, simulates external services | yes, as test tooling only |
| Python modules | `buildish_release_tooling.*` imports | Internal implementation modules | no public API; in model only when reachable through CLI or harness |
| Site and documentation content | `docs/`, `site/pages/` | Static content consumed by the site pipeline | no security properties beyond docs correctness |
| Release-legal helper | `python -m buildish_release_tooling.legal.release_legal` | Reads dependency metadata and writes generated legal artifacts | yes for local-file safety; no release-publication guarantees |

## 3. Out Of Scope: Explicit Non-Goals

- This project does not secure a compromised maintainer account, GitHub repository administrator,
  ASF account, ASF SVN service, GitHub service, Docker Hub service, ATR service, package registry, or
  GPG private key. Those actors can already change or authorize release state. *(inferred)*
- This project does not make candidate source code safe to execute. Full reproducibility mode can run
  component-defined build commands from the verified source tree and is not a sandbox. *(documented)*
- This project does not provide a network daemon or remote multi-tenant service. Reports requiring
  arbitrary unauthenticated network users to call the CLI directly are out of model. *(inferred)*
- This project does not promise that component-authored `release-config.yaml` is benign. The tool
  validates selected fields and contracts, but component policy remains an authored release input.
  *(documented)*
- This project does not defend against malicious local users with write access to the same worktree,
  temporary directories, Git checkout, GPG home, Docker config, or process environment. *(inferred)*
- This project does not guarantee correctness for non-production release targets enabled with
  `--allow-non-production-release-targets`; that mode exists for local harness and test runs.
  *(documented)*
- This project does not treat the local harness as a production release mechanism. Harness fixtures,
  generated shims, and `file://` or `http://` targets are test-only surfaces. *(documented)*
- This project does not provide confidentiality for public release artifacts, manifests, vote
  materials, checksums, or generated summaries. Those outputs are intended to be shareable release
  records. *(inferred)*
- Generated schema files under `site/pages/schemas/` are generated documentation artifacts and are
  not independently threat-modeled as code. *(inferred)*

## 4. Trust Boundaries And Data Flow

The main trust boundary is the CLI invocation boundary: command-line arguments, `release-config.yaml`,
checked-out Git state, environment hooks, local files, and remote service responses enter trusted
Python orchestration code. The tool then validates, normalizes, signs, publishes, or reports release
state through local filesystem writes and external adapters. *(inferred)*

Primary data flows: *(documented)*

- Component release config and Git metadata flow into derived RC or final-release state.
- Source Git content flows into a reproducible source archive, checksum sidecars, detached
  signatures, staged SVN content, and vote manifests.
- Staged RC content and signed vote manifests flow into verification reports and final publication
  checks.
- Component-defined secondary artifact metadata flows into registration fragments, vote manifests,
  verification reports, and inspection bundles.
- External service state from GitHub, ASF SVN, Docker Hub, ATR, and package registries flows into
  command decisions and human-readable summaries.
- Harness scenario files and workflows flow into temporary simulated repositories, rewritten
  workflows, shim state, and trace output.

Reachability preconditions per component family:

| Family | Finding is in model only if it is reachable from |
| --- | --- |
| Release CLI orchestration | CLI arguments, component config, Git state, or documented environment hooks used by a supported command |
| RC artifact staging and signing | selected source ref, release config, staging URLs, GPG/SVN credentials, or staged RC bytes |
| Final publication | selected RC tag, final-release state, staged RC vote manifest, GitHub/SVN/Docker credentials, or remote service responses |
| Verification and inspection | vote manifest, artifact URI, local override file, downloaded artifact bytes, archive metadata, or selected rebuild profile |
| Secondary artifact registration | `record-artifact` CLI parameters, local artifact file bytes, package registry metadata, or collection inventory |
| Local harness | harness config, scenario YAML, rewritten workflow data, local fixture state, or intercepted shim calls |
| Release-legal helper | local project metadata, dependency metadata, license files, and generated output paths |

## 5. Assumptions About The Environment

- The runtime is Python 3.11 or later with the project dependencies declared in `pyproject.toml`.
  *(documented)*
- Git, SVN, GPG, Docker, `uv`, GitHub CLI, `act`, and other external tools are trusted when invoked
  by commands that require them. Compromised binaries are outside this model. *(inferred)*
- Release workflows run in a Git worktree for the target component and have fetched the needed heads
  and tags before commands that inspect release refs. *(documented)*
- Release credentials are supplied through environment variables or the platform credential store and
  are scoped to the intended release operation. *(documented)*
- GitHub Environment protection, including required reviewers and environment-scoped secrets, is
  enforced by GitHub. The local harness can exercise workflow shape but does not validate GitHub
  Environment approval semantics. *(documented)*
- Local filesystem paths passed to the tool are controlled by the caller or by trusted workflow
  configuration, except where a command explicitly reads a release artifact, manifest, or override
  file for verification. *(inferred)*
- Subprocess execution is allowed in release workflows and harness runs. The project assumes the host
  allows these subprocesses to run with the caller's privileges. *(documented)*
- The checked-in Prepare RC and Release Version workflows serialize by repository and exact version.
  Direct local CLI invocations do not take a distributed release lock, so concurrent local commands
  that mutate the same release tags, SVN directories, GitHub releases, Docker aliases, or output
  paths are not assumed safe unless the caller serializes them or the external service itself rejects
  conflicts. *(documented)*
- Time and clocks matter for reproducibility through `SOURCE_DATE_EPOCH`, but the tool does not
  claim to secure the host clock against tampering. *(inferred)*
- Network transport to production ASF dist targets uses the configured HTTPS production prefixes
  unless non-production target mode is explicitly enabled. *(documented)*

No-surprise side effects inventory:

| Side effect | Model statement |
| --- | --- |
| Network access | Release and verification commands may contact ASF SVN/dist, GitHub, Docker Hub, ATR, package registries, and artifact URIs. *(documented)* |
| Child processes | Many commands spawn Git, SVN, GPG, Docker, shell, `uv`, `act`, or configured rebuild commands. *(documented)* |
| Environment reads | The tool reads documented release credentials, GitHub summary/output paths, progress controls, and harness variables. *(documented)* |
| Environment mutation | Host-direct rebuilds receive a scrubbed, constructed environment; harness workflow rewriting may inject harness variables into simulated jobs. *(documented)* |
| Filesystem writes | Commands write manifests, summaries, archives, signatures, checksums, worktrees, harness fixtures, generated docs, and release-legal outputs. *(documented)* |
| Process-wide locale/FPU/signal state | No project behavior intentionally mutates locale, FPU state, or signal handlers. *(inferred)* |
| stdout/stderr | Commands write progress, sanitized command traces, errors, and summaries to stdout/stderr as normal CLI output. *(documented)* |

## 5a. Build-Time And Configuration Variants

| Variant | Default | Effect on security model | Maintainer stance |
| --- | --- | --- | --- |
| `--allow-non-production-release-targets` | off | Allows `file://` and `http://` ASF dist target URLs for local/test targets. Production release target properties do not hold. | Test-only; do not use for production releases. *(documented)* |
| `--mode` for `verify-rc` | `auto` | Controls whether verification remains integrity-only or runs host-direct rebuild commands. Full mode executes candidate build code. | Full mode requires explicit request or interactive confirmation. *(documented)* |
| Local verify-rc override file | absent | Can override rebuild recipes for local, non-canonical reproducibility runs. Canonical release verification properties depend on the signed manifest and component config, not local overrides. | Local override only. *(documented)* |
| `BUILDISH_COMMAND_CAPTURE_OUTPUT` | off | Forces subprocess output capture and sanitized logging, affecting log handling but not release integrity. | Operational/debug option. *(documented)* |
| `BUILDISH_COMMAND_LOG_STDERR` | on | Controls whether command traces are echoed to stderr. | Operational/debug option. *(documented)* |
| `BUILDISH_HARNESS_SUBPROCESS_TIMEOUT_SECONDS` | default harness timeout | Changes harness subprocess timeout only. | Harness-only. *(documented)* |
| Component `release-config.yaml` fields | component-authored | Select target URLs, tag behavior, secondary targets, ATR policy, and verification profiles; changes can change which release properties hold for that component. | Component policy contract. *(documented)* |

No compile-time feature flag is known to remove a claimed security property. *(inferred)*

## 6. Assumptions About Inputs

The tool accepts release workflow inputs from CLI arguments, YAML config files, JSON manifests,
artifact files, remote HTTP(S) resources, `file://` resources in local/test contexts, Git metadata,
SVN state, GitHub API state, package registry metadata, Docker image references, environment
variables, and harness scenario files. *(documented)*

Per-parameter trust table:

| Entry point | Parameter or input | Attacker-controllable? | Caller must enforce |
| --- | --- | --- | --- |
| All production release commands | `--component-config` | no, trusted component policy on selected release ref | Review and pin the release-tooling ref and component config before release |
| All production release commands | version, source ref, release line, selected RC tag | no, trusted workflow/maintainer input | Use exact intended values; do not pass user-supplied release identifiers |
| Release commands with external side effects | credentials in environment | no, trusted secret material | Scope credentials to the least privilege needed for the command |
| `create-source-artifact` and related commands | selected Git source tree | partly; project source may be adversarial for verification scenarios | Do not execute untrusted build code unless intended; review release source |
| `build-source-rc` | GPG private key | no, trusted secret material | Keep key secret and rotate if exposed |
| `finalize-rc-vote-materials` | staged RC artifact and sidecars | yes if staging area is mutable by another actor | Protect ASF dev staging and rely on manifest revalidation before final publication |
| `publish-source-release-svn` | staged RC directory and vote manifest | yes if staging area is mutable by another actor | Publish only the approved selected RC tag and verify staged bytes match the manifest |
| `record-artifact` | `--file` local bytes | no for production release; trusted artifact produced by workflow | Ensure file is the intended release artifact |
| `record-artifact` | registry metadata and remote inventory | yes, registry/service responses can be adversarial or stale | Use immutable digests/checksums and trusted registry endpoints |
| `verify-rc` | vote manifest URI/file and artifact URIs | yes, verifier may inspect untrusted candidate materials | Run on trusted hardware and review signature/checksum results |
| `verify-rc --override-config` | local override file | no, verifier-owned local policy | Do not treat override results as canonical release policy |
| `verify-rc --mode full` | configured rebuild command | yes, command is from candidate/component policy and runs on host | Only run in an isolated environment appropriate for candidate code |
| `inspect-repro` | retained artifacts, reports, and archive contents | yes, release artifacts may be malformed | Treat output as diagnostic; do not extract artifacts with unsafe external tools |
| `buildish-release-harness` | harness scenario YAML and workflow files | no, maintainer/test-authored | Do not run arbitrary untrusted harness scenarios on a sensitive host |
| Release-legal helper | project metadata and dependency metadata | partly, local project/dependency data | Treat generated output as review input, not an external security boundary |

Size, shape, and rate assumptions: *(documented)*

- YAML config parsing is bounded to `5 MiB` by default.
- JSON manifest parsing is bounded to `25 MiB` by default.
- Archive inspection defaults to at most `250,000` entries, `2 GiB` per member, and `8 GiB` total
  member bytes.
- HTTP error bodies logged by the downloader are bounded to `1 MiB`.
- Captured subprocess output reads are bounded in logs, with a default output-file log limit of
  `4 MiB` and captured output read limit of `16 MiB`.
- Most logged subprocesses default to a `3600` second timeout.
- Some collection-style artifact inventory operations may use configured workers, such as Maven
  repository inventory workers.

## 7. Adversary Model

In-scope adversaries:

- A remote network or registry peer serving malformed, inconsistent, oversized, or misleading
  artifacts, metadata, HTTP responses, redirects, or package inventory. *(inferred)*
- A malicious or mistaken component configuration change that attempts to redirect release targets,
  alter verification profiles, or create unsafe release metadata. *(inferred)*
- A mutable staging-area actor that can alter staged RC bytes or sidecars between workflow steps.
  *(inferred)*
- A verifier inspecting a release candidate containing malformed archives or metadata. *(inferred)*
- A scanner, fuzzer, or AI analysis tool reporting possible security issues in reachable CLI and
  verification code. *(inferred)*

Attacker goals considered:

- Cause publication of the wrong source commit, wrong tag, wrong staged bytes, or wrong final release
  material.
- Bypass release-target URL restrictions or downgrade production release endpoints.
- Leak release credentials through command arguments, logs, reports, summaries, or subprocess output.
- Cause unbounded memory, disk, CPU, or log growth with large inputs, artifacts, archives, or command
  output.
- Confuse verifiers through malformed vote manifests, sidecars, archive contents, or secondary
  artifact metadata.

Explicitly out-of-scope actors:

- Attackers with control over the calling process, maintainer workstation, GitHub runner, release
  credentials, signing key, or external tool binaries. *(inferred)*
- Attackers with administrator control of GitHub, ASF SVN/dist, Docker Hub, ATR, package registries,
  or Buildish site infrastructure. *(inferred)*
- Attackers whose only path is to make a maintainer intentionally pass untrusted shell commands or
  run full reproducibility checks on an unsafe host after the documented prompt. *(documented)*

## 8. Security Properties The Project Provides

| Property | Conditions | Violation symptom | Severity tier | Provenance |
| --- | --- | --- | --- | --- |
| Production ASF dist targets use expected HTTPS ASF prefixes | `--allow-non-production-release-targets` is not used | A production command accepts `file://`, plain `http://`, or non-ASF dist target URL for `asf_dist_dev_base` or `asf_dist_release_base` | security-critical | documented |
| Non-production targets are explicit | Caller must pass `--allow-non-production-release-targets` | Local/test `file://` or `http://` targets work without an explicit opt-in | hardening/security-critical depending on release context | documented |
| Structured local input parsing is bounded | Inputs use shared bounded parsing helpers | Large YAML/JSON/TOML files are read into memory without configured limits | security-critical for untrusted verification inputs; hardening otherwise | documented |
| Archive inspection is bounded | Archive is inspected through shared bounded tar/zip readers | Archive with too many entries or too much member data causes unbounded resource use | security-critical for verifier-facing inputs | documented |
| Downloaded resources can be bounded and hashed without full buffering | Callers use downloader APIs with explicit `max_bytes` for reads/downloads | Remote resource causes unbounded memory or disk growth | security-critical for verifier-facing inputs | documented |
| Subprocess command lines and captured output are sanitized for known secret values | Secrets are present in documented environment variables or extra secret values | Secret appears in command trace, failure detail, captured output, or summary generated by command logging | security-critical | documented |
| Subprocess execution has a default timeout | Commands use `run_logged_command` without disabling timeout | External tool hangs indefinitely under normal command execution | availability/hardening | documented |
| Host-direct rebuild reports omit environment variable values | Reproducibility report generation uses the built-in payload helpers | Report includes secret or machine-local environment values rather than names only | security-critical | documented |
| Host-direct rebuild environment is scrubbed of common CI and credential variables | Rebuild uses `build_host_direct_environment` | Candidate build receives inherited GitHub, cloud, package, SVN, GPG, or SSH credentials by default | security-critical | documented |
| Full host-direct reproducibility execution is not silent in auto mode | `verify-rc --mode auto` on an interactive terminal | Candidate build code runs without full mode or interactive confirmation | security-critical | documented |
| Rebuild output path collection rejects symlinks and paths escaping the project root | Outputs are collected through `collect_profile_output_paths` | Rebuild output glob causes files outside project root to be treated as candidate outputs | security-critical | documented |
| Project-relative paths cannot escape the project root where shared validators are used | Code path uses `resolve_project_relative_path` or related validators | `..` or absolute paths escape the intended project root | security-critical | documented |
| Final SVN publication revalidates staged RC directory against the mirrored vote manifest | Publication uses current final publication command flow | Final publication publishes bytes that do not match the approved mirrored manifest | security-critical | documented |
| Checked-in release workflows serialize release mutations by repository and version | Downstream uses the provided Prepare RC and Release Version workflow pattern with the shared non-canceling concurrency group | Two production release workflows for the same repository and exact version mutate RC or final publication state concurrently | hardening | documented |
| Harness `act` backend does not copy ambient GitHub tokens into generated secret files | Harness uses current workflow helper behavior | Local harness run leaks ambient `GITHUB_TOKEN` or `GH_TOKEN` into generated `act` secrets | security-critical | documented |
| Python module layout is not a public API | Consumers invoke through CLI | Security or compatibility report depends only on direct import of internal modules | correctness-only | documented |

## 9. Security Properties The Project Does Not Provide

- No sandbox for candidate source code or configured build commands. Full reproducibility mode runs
  selected build commands directly on the host after explicit selection or confirmation. *(documented)*
- No guarantee that a signed vote manifest means the release is approved by ASF governance; it records
  candidate facts, not vote outcome. *(inferred)*
- No guarantee that checksums alone authenticate artifacts. Checksums detect accidental or
  out-of-band byte changes only when compared against a trusted signed manifest or trusted channel.
  *(inferred)*
- No cryptographic protection for unsigned JSON manifests, summaries, generated reports, or harness
  traces unless a command explicitly signs the relevant vote-manifest material. *(inferred)*
- No defense against a compromised or malicious component `release-config.yaml` beyond the validation
  rules documented in this model. *(inferred)*
- No protection against intentionally overbroad credentials supplied by the operator or workflow.
  *(inferred)*
- No constant-time, side-channel, or cryptographic primitive guarantees. The project orchestrates
  release operations; it is not a cryptographic library. *(inferred)*
- No guarantee that external services return immutable, available, or globally consistent state.
  Service outages, API behavior changes, registry compromise, and stale mirrors are outside this
  project's security boundary. *(inferred)*
- No universal denial-of-service protection. The project has explicit read, archive, subprocess, and
  log budgets in many paths, but does not promise bounded total runtime for all external tools,
  networks, package registries, or configured build commands. *(inferred)*
- No guarantee that local harness results prove production release safety. The harness is a simulator
  for workflow behavior and regression testing. *(documented)*
- No built-in guarantee that GitHub Environment approval gates every release mutation. Projects that
  require approval before all GitHub release writes must declare the relevant `environment:` on every
  write job and configure the environment in GitHub. *(documented)*

False-friend properties:

- Checksums are integrity evidence only when anchored to trusted release metadata; they are not
  authentication by themselves. *(inferred)*
- The local harness simulates release workflows; it is not a production isolation boundary.
  *(documented)*
- `--allow-non-production-release-targets` is useful for tests; it is not a safe degraded production
  mode. *(documented)*
- Local verify-rc overrides help verifiers rebuild on their own machines; they do not replace the
  canonical component policy selected by the signed vote manifest. *(documented)*
- GitHub draft releases and moving tags are release metadata conveniences; they are not ASF release
  approval markers. *(inferred)*

Well-known attack classes left to callers or operators:

- Candidate-build code execution: run full reproducibility checks only in a host context appropriate
  for executing release-candidate code. *(documented)*
- Credential exfiltration by external tools: provide only credentials needed by each workflow step.
  *(inferred)*
- Mutable registry metadata: prefer immutable digests, signed manifests, and staged byte comparison
  over tag or latest-version lookups. *(inferred)*
- Archive extraction attacks: the verifier inspection code reads archive metadata and hashes; callers
  should not extract untrusted archives with unsafe external tooling. *(inferred)*

## 10. Downstream Responsibilities

- Pin `buildish-release-tooling` to an exact immutable Git tag or commit in release-critical
  workflows. *(documented)*
- Run production release commands from a trusted GitHub Actions workflow or trusted maintainer shell.
  *(inferred)*
- Review and protect component `release-config.yaml`; treat changes to release targets, tag modes,
  ATR settings, secondary targets, and verification profiles as release-policy changes. *(documented)*
- Do not use `--allow-non-production-release-targets` for production release publication.
  *(documented)*
- Scope `GH_TOKEN`, `GITHUB_TOKEN`, `BUILDISH_SVN_DEV_USERNAME`, `BUILDISH_SVN_DEV_PASSWORD`,
  `BUILDISH_GPG_PRIVATE_KEY`, `DOCKERHUB_USER`, and `DOCKERHUB_TOKEN` to the command that requires
  them. *(documented)*
- Protect GPG private keys and passphrases outside the tool; rotate them if exposed. *(inferred)*
- Fetch required Git heads and tags before commands that inspect source refs or tags. *(documented)*
- Treat full reproducibility mode as candidate code execution and run it in an isolated environment
  appropriate for that risk. *(documented)*
- Verify release candidates on trusted hardware using the signed vote manifest, signatures,
  checksums, and configured release verification guide. *(documented)*
- Keep Prepare RC and Release Version workflows on the same non-canceling concurrency group keyed by
  repository and exact version when copying or customizing the Buildish workflow pattern.
  *(documented)*
- If project policy requires approval before all release mutations, declare an appropriate GitHub
  `environment:` on every release job with `permissions.contents: write`, including tag and GitHub
  Release update jobs that use `github.token`. *(documented)*
- Verify GitHub Environment required-reviewer rules in GitHub repository settings; the local `act`
  harness does not validate those protection semantics. *(documented)*
- Treat harness output as test evidence, not as production release authorization. *(documented)*

## 11. Known Misuse Patterns

- Running production release workflows from a moving branch or unpinned package lookup instead of an
  exact immutable tooling ref. *(documented)*
- Enabling `--allow-non-production-release-targets` outside local harness or test scenarios.
  *(documented)*
- Passing unreviewed component config from an untrusted branch into production release commands.
  *(inferred)*
- Treating full verify-rc reproducibility mode as safe because it is part of verification, even
  though it executes candidate build code. *(documented)*
- Treating checksum sidecars as authentication when they are not anchored to the signed vote manifest
  or another trusted channel. *(inferred)*
- Treating harness simulations as proof that external production services will behave identically.
  *(inferred)*
- Supplying broad repository, SVN, Docker, or cloud credentials to workflow jobs that only need a
  narrower subset. *(inferred)*
- Publishing moving tags or aliases before the immutable final release state has been selected and
  approved. *(inferred)*
- Removing or splitting the shared release workflow concurrency group so Prepare RC and Release
  Version runs for the same repository and exact version can overlap. *(documented)*
- Assuming that an environment-gated secret-consuming job also gates later GitHub write jobs that do
  not declare an `environment:` themselves. *(documented)*
- Treating a passing local `act` harness run as evidence that GitHub Environment required-reviewer
  protection is configured or enforced. *(documented)*

## 11a. Known Non-Findings: Recurring False Positives

| Reported pattern | Why it is not a finding under this model | Licensed by |
| --- | --- | --- |
| `subprocess.run` with non-literal command arrays in release adapters | The CLI is trusted orchestration and external tools are part of the intended release environment; command execution itself is not a vulnerability unless attacker-controlled parameters cross a trust boundary without validation | [Assumptions about the environment](#5-assumptions-about-the-environment), [Assumptions about inputs](#6-assumptions-about-inputs) |
| Environment variables used for credentials | Documented release workflows use environment-provided credentials; findings must show leakage, overbroad propagation, or misuse, not mere presence | [Scope and intended use](#2-scope-and-intended-use), [Security properties the project provides](#8-security-properties-the-project-provides) |
| `file://` or `http://` support in URI transport | These schemes are allowed for local/test reads and only for release targets when explicit non-production mode is enabled | [Build-time and configuration variants](#5a-build-time-and-configuration-variants) |
| Full verify-rc mode executes configured build commands | This is documented candidate-code execution and is guarded by mode selection or prompt behavior | [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |
| Internal Python modules are importable | The supported public contract is the CLI, schemas, and documented file contracts; direct imports are not public API | [Scope and intended use](#2-scope-and-intended-use) |
| Generated schema files lack independent validation logic | Schemas are generated documentation artifacts, not executable security enforcement points | [Out of scope](#3-out-of-scope-explicit-non-goals) |
| Harness shims modify workflows or inject local variables | Harness behavior is intentionally a local simulator and is not production release behavior | [Scope and intended use](#2-scope-and-intended-use), [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |
| Local harness does not enforce GitHub Environment approvals | GitHub Environment required-reviewer semantics are service-side controls; harness tests cannot prove them | [Assumptions about the environment](#5-assumptions-about-the-environment), [Downstream responsibilities](#10-downstream-responsibilities) |

## 12. Conditions That Would Change This Model

Revise this model when any of the following occur:

- A new public CLI command, supported file contract, manifest schema, or release workflow is added.
  *(inferred)*
- A command starts accepting a new class of remote input, archive format, package registry metadata,
  credential, or local override file. *(inferred)*
- The project gains a network service, daemon mode, plugin system, or multi-tenant execution model.
  *(inferred)*
- A default changes for `--allow-non-production-release-targets`, verify-rc mode selection,
  credential propagation, command logging, or harness secret handling. *(inferred)*
- The production release target validation policy changes, including accepted schemes, hosts, or
  path prefixes. *(inferred)*
- Host-direct rebuild execution becomes sandboxed, containerized, or otherwise changes privilege
  boundaries. *(inferred)*
- Harness code is promoted from test tooling to production release orchestration. *(inferred)*
- A vulnerability report cannot be cleanly assigned to one of the dispositions in
  [Triage dispositions](#13-triage-dispositions). *(inferred)*

## 13. Triage Dispositions

| Disposition | Meaning | Licensed by |
| --- | --- | --- |
| `VALID` | Violates a property the project claims, through an in-scope adversary and in-scope input | [Security properties the project provides](#8-security-properties-the-project-provides), [Assumptions about inputs](#6-assumptions-about-inputs), [Adversary model](#7-adversary-model) |
| `VALID-HARDENING` | No claimed property is violated, but a known misuse is easy enough that the project elects to harden it | [Known misuse patterns](#11-known-misuse-patterns) |
| `OUT-OF-MODEL: trusted-input` | Requires attacker control over an input this model marks trusted | [Assumptions about inputs](#6-assumptions-about-inputs) |
| `OUT-OF-MODEL: adversary-not-in-scope` | Requires attacker capabilities this model excludes | [Adversary model](#7-adversary-model) |
| `OUT-OF-MODEL: unsupported-component` | Lands in generated docs, static site content, or other code placed out of scope | [Out of scope](#3-out-of-scope-explicit-non-goals) |
| `OUT-OF-MODEL: non-default-build` | Only manifests when explicit non-production or local-only modes are used outside their documented purpose | [Build-time and configuration variants](#5a-build-time-and-configuration-variants) |
| `BY-DESIGN: property-disclaimed` | Concerns a property the project explicitly does not provide | [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |
| `KNOWN-NON-FINDING` | Matches a recurring false-positive pattern already documented here | [Known non-findings](#11a-known-non-findings-recurring-false-positives) |
| `MODEL-GAP` | Cannot be cleanly routed to one of the dispositions above | [Conditions that would change this model](#12-conditions-that-would-change-this-model) |

## 14. Open Questions For Maintainers

Wave 1:

| Question | Proposed answer | Lands in |
| --- | --- | --- |
| Should the threat model be published under `docs/` as versioned component docs? | Yes. It belongs with the CLI contract and release verification docs. | [Header](#1-header) |
| Is the project comfortable claiming production release commands are not intended for arbitrary untrusted direct callers? | Yes. The intended callers are trusted maintainers, workflows, and verifiers. | [Scope and intended use](#2-scope-and-intended-use), [Adversary model](#7-adversary-model) |
| Are compromised external services, maintainer accounts, GPG keys, and runner hosts out of scope? | Yes. The tool can validate release state but cannot secure those trust anchors. | [Out of scope](#3-out-of-scope-explicit-non-goals), [Adversary model](#7-adversary-model) |
| Is `--allow-non-production-release-targets` strictly test/harness-only? | Yes. Production workflows should never enable it. | [Build-time and configuration variants](#5a-build-time-and-configuration-variants), [Downstream responsibilities](#10-downstream-responsibilities) |
| Should full verify-rc mode be described as unsandboxed candidate code execution? | Yes. The prompt and mode selection are warnings, not containment. | [Out of scope](#3-out-of-scope-explicit-non-goals), [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |

Wave 2:

| Question | Proposed answer | Lands in |
| --- | --- | --- |
| Should the project claim no intentional locale, FPU, or signal-handler mutation? | Yes, unless maintainers know of a hidden side effect. | [Assumptions about the environment](#5-assumptions-about-the-environment) |
| Are concurrent release invocations against the same tags/SVN paths/aliases unsupported unless external services reject conflicts? | Yes for direct local CLI use. Checked-in workflows serialize release publication for a repository/version. | [Assumptions about the environment](#5-assumptions-about-the-environment), [Security properties the project provides](#8-security-properties-the-project-provides) |
| Should reports against direct imports of internal Python modules be treated as out-of-contract unless reachable through CLI behavior? | Yes. The CLI and documented file contracts are the supported API. | [Scope and intended use](#2-scope-and-intended-use), [Known non-findings](#11a-known-non-findings-recurring-false-positives) |
| Does the project want to claim all verifier-facing archive and parsing paths are bounded, or only the shared helper paths listed here? | Only the shared helper paths until a specific audit confirms every verifier path. | [Security properties the project provides](#8-security-properties-the-project-provides) |
| Should `release_legal` be in this threat model at all? | Yes for local-file/resource safety, but not for release-publication integrity. | [Scope and intended use](#2-scope-and-intended-use), [Out of scope](#3-out-of-scope-explicit-non-goals) |

Wave 3:

| Question | Proposed answer | Lands in |
| --- | --- | --- |
| Should unsigned manifests and command summaries be explicitly described as non-authoritative unless tied to signed vote-manifest data? | Yes. This prevents consumers from over-trusting convenience outputs. | [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |
| What quantitative DoS line should apply to package registry inventory operations? | Use documented worker counts and bounded reads where implemented; do not claim total runtime bounds for external registries. | [Security properties the project provides](#8-security-properties-the-project-provides), [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide) |
| Should malformed public release artifacts that only crash `inspect-repro` be security bugs? | Yes when reachable from verifier-facing untrusted artifact bytes and not covered by explicit bounds; otherwise correctness or hardening. | [Triage dispositions](#13-triage-dispositions) |
| Should the `SECURITY_REVIEW.md` historical findings remain as provenance for this model? | Yes, where it documents fixed behaviors such as secret handling and final SVN revalidation. | [Header](#1-header), [Security properties the project provides](#8-security-properties-the-project-provides) |

## 15. Optional Machine-Readable Companion

No `threat-model.yaml` sidecar is produced in this draft. If automated triage adopts this model, add
a generated or manually maintained sidecar containing:

- entry points and per-parameter trust levels from [Assumptions about inputs](#6-assumptions-about-inputs)
- component families and scope status from [Scope and intended use](#2-scope-and-intended-use)
- configuration variants from [Build-time and configuration variants](#5a-build-time-and-configuration-variants)
- claimed and disclaimed properties from [Security properties the project provides](#8-security-properties-the-project-provides) and [Security properties the project does not provide](#9-security-properties-the-project-does-not-provide)
- known non-findings from [Known non-findings](#11a-known-non-findings-recurring-false-positives)
- disposition labels from [Triage dispositions](#13-triage-dispositions)
