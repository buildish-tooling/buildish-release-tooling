---
title: Release Tooling Documentation
description: "Composable direct and candidate release lifecycles, stable manifests, and provider-specific adapters."
weight: 90
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

# Release Tooling Documentation

Buildish Release Tooling separates project policy, release state, platform adapters, and workflow
orchestration. A component owns its `release-config.yaml` and thin workflow. The CLI resolves exact
identities, performs one bounded operation at a time, and writes machine-readable results that the
workflow passes to later jobs.

GitHub is the first implemented hosting platform. Platform-neutral state and manifests do not treat
GitHub, the ASF, voting, a built source archive, or any secondary registry as mandatory.

## Choose a lifecycle

- [Direct release](direct-release/) publishes an exact final version without a candidate.
- [Candidate release and exact promotion](candidate-release/) publishes retained candidates and
  promotes one explicitly selected candidate.

Both approaches may use an unsuffixed final version such as `1.2.3` and final tag such as `v1.2.3`.
The candidate suffix identifies the candidate only; it does not change the final version.

## Compose a component release

- [Workflow composition](release-workflows/) explains job boundaries, artifact handoff, permissions,
  concurrency, optional GitHub Environments, and external gates.
- [Source artifacts and signing](source-artifacts-and-signing/) covers platform-generated source
  snapshots, separately built source archives, and protected or unprotected OpenPGP keys.
- [GitHub release policy](github-release-policy/) documents current GitHub candidate and final
  publication behavior.
- [Optional ASF profile](asf-profile/) adds ASF dist, vote wording, KEYS, and Incubator policy only
  when a component selects that profile.

Maintainer references:

- [Generated config and schema reference](reference/)
- [Manifest and verification contracts](verification-contracts/)
- [Codebase layout](codebase-layout/)
- [Local test and harness layout](test-suite/)
- [Release-legal maintenance](release-legal/)
- [Threat model](threat-model/)

## Supported external contract

The supported contract consists of:

- CLI commands and arguments;
- the authored `release-config.yaml` schema;
- supported JSON schemas and emitted manifest shapes;
- exit status, manifest-path output, and GitHub step summaries documented for a command.

The Python package layout is not a public API. Component workflows should invoke the CLI from an
exact immutable tooling revision.

The standard invocation shape is:

```bash
uv run --project /path/to/buildish-release-tooling --frozen \
  buildish-release-tooling <command> \
  --component-config /path/to/release-config.yaml \
  [command arguments...]
```

Commands operate on the current component Git worktree. Workflow jobs that inspect remote refs must
fetch the required heads and tags first.

## Configuration model

`release-config.yaml` is a typed composition of independent choices:

- component and version identity;
- source selection and source snapshot mode;
- source checks;
- direct or candidate lifecycle;
- optional candidate policy;
- built artifacts, checksums, and optional signing;
- authoritative, convenience, and secondary publication targets;
- immutable and moving tag policy;
- optional vote-material profile;
- optional foundation policy profiles.

The complete generated field reference is under [Reference](reference/). The walkthroughs use
minimal valid examples for their lifecycle.

## Stable manifests

Three top-level manifest contracts connect otherwise independent phases:

- `CandidateManifestV1` binds one exact candidate tag, source revision, artifact inventory,
  verification evidence, publications, and tooling provenance.
- `VotePackageV1` optionally binds human voting material to the cryptographic digest of one exact
  candidate manifest. It does not record or decide the vote outcome.
- `ReleaseManifestV1` records a direct or promoted final release. Direct releases omit candidate
  fields; promoted releases name the exact candidate manifest and use typed promotion evidence.

Current promotion evidence distinguishes byte-identical artifacts, immutable registry identity, and
platform-generated snapshots from tags that resolve to the same source revision.

## Runtime integration

`MANIFEST_PATH` selects the JSON result path for commands that emit a manifest.
`GITHUB_STEP_SUMMARY` receives human-readable summaries. Selected workflow-boundary commands append
small scalar values to `GITHUB_OUTPUT`; complete state remains in JSON files.

Credentials are operational inputs, not authored config values. GitHub tokens, signing keys,
passphrases, registry credentials, and foundation credentials belong in the workflow or deployment
secret store chosen by the component.

## Optional capabilities

Release branch creation is available through `create-release-branch`, but neither lifecycle requires
a maintained release line. Secondary publication adapters, moving aliases, generic voting, ASF
composition, and reproducibility verification are selected only by components that need them.
