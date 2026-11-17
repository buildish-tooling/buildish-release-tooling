---
title: Materialized Action Releases
description: "Bind generated Action commits to reviewed source through credential-separated release jobs."
weight: 45
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

# Releasing generated GitHub Action content

The modern materialized-commit lifecycle requires **Release Tooling 0.1.4 or
later**; the 0.1.3 distribution does not include these commands. The legacy
materialization commands remain available; this page describes the modern
state/manifest lifecycle.

## Reviewed source and materialized content

Some Actions ship generated executables that are absent from the reviewed source
commit. Keep two exact Git identities:

- **S**, the reviewed source commit used for source policy, CI and release notes.
- **M**, one direct child of S containing generated files. Candidate and final
  Action tags target M. Promotion reuses that exact commit, not a rebuild of it.

The materialization binding records S, M, M's tree, permitted paths and the
SHA-256 of a retained Git bundle. Git object validation checks the sole-parent
relationship, exact tree and every changed path, including deletions and modes.
Generated symlinks/submodules and changes outside permitted paths are rejected.
Structural validation does not prove how a build ran: trusted producer identity
and independently retained job-output digests remain workflow responsibilities.

Configure trusted component policy, for example:

```yaml
tags:
  final_mode: detached-materialization-commit
  materialized_paths: [dist]
```

Paths are literal normalized repository-relative paths, not globs. Exact-source
mode remains the default. A materialized state cannot authorize its own policy;
privileged jobs load the configuration from trusted workflow/tooling code.

## Component build job

Resolve a direct/candidate state in a trusted job and retain its SHA-256 as a job
output. Pass that exact state into the selected-source build job. Build tooling
is component-owned: this can run npm, Gradle or another established build process.
It must not receive signing keys, publication tokens or persisted checkout
credentials. Keep generated files in a detached worktree based on S, commit them
using an explicit process-local Git identity, and retain M.

After building M, export its objects and bind the candidate state:

```sh
MANIFEST_PATH=bound-candidate.json buildish-release-tooling bind-materialization \
  --component-config trusted-release-config.yaml \
  --candidate-state resolved-candidate.json \
  --materialized-commit "$M" \
  --bundle-output materialized.bundle
```

For a direct release, use `--release-state resolved-direct.json` instead. The
command does not build, execute generated files, push refs, or commit changes.
It temporarily creates a local transport ref, exports a Git bundle with S as its
prerequisite, removes the temporary ref, and emits bound state. Existing binding
and bundle bytes can be reused; it rejects replacing a retained M or bundle.

Retain the original resolved state, bound state and bundle. Emit the bound-state
SHA-256 and bundle SHA-256 through independent producer job outputs. These
checksums must come from the intended producer, not solely from the downloaded
artifact containing the protected bytes.

## Trusted import and publication jobs

Verify the original resolution state's checksum against the trusted resolution
job output, and the bound-state checksum against the intended build job output.
Fetch exact S if the trusted checkout does not have it. Fetching objects must not
check out or execute selected-source code with publication credentials.

Then import the retained bundle:

```sh
MANIFEST_PATH=imported-candidate.json buildish-release-tooling import-materialization \
  --component-config trusted-release-config.yaml \
  --candidate-state bound-candidate.json \
  --source-state resolved-candidate.json \
  --bundle materialized.bundle \
  --bundle-sha256 "$BUILD_BUNDLE_SHA256"
```

The original source state comes from the trusted resolution job. Comparison permits
only adding the binding and changing the intended tag targets to M; a build
producer cannot replace S, release identity, notes or other resolved state.
Import checks configured policy before fetching, verifies a private copy against
the independently supplied digest, and imports exactly the bound ref. It requires
S locally and validates M's parent/tree/paths after import. HEAD and working files
remain unchanged. It does not publish refs or execute build/generated code.

Use the bound/imported state for the ordinary candidate tag/stage/manifest steps.
Tag creation rechecks policy and objects. In detached mode it first makes M
available to the GitHub tag API by publishing an internal Git ref:

```text
refs/heads/buildish-internal/materialized/<full-M-commit-sha>
```

This is a privileged Git write and needs the appropriate repository credentials
and namespace permissions. It checks existing local/remote tags and the internal
ref, rejects conflicts and uses a create-only lease to prevent racing updates.
The build job never performs this push. Existing matching refs are reused. The
retained internal refs can trigger applicable push workflows and remain available
for object recovery; cleanup is an explicit operator action after retention and
immutable tags have been considered.

Follow [workflow composition](../release-workflows/) for producer-bound handoffs,
job-scoped permissions and immutable GitHub draft sealing. Attach evidence and
the final sealed manifest before publication; use the producer's exact sealed
manifest digest for finalization. Nothing is uploaded after a Release locks.

## Promotion and recovery

Promotion selects an exact candidate tag and independently retained candidate
manifest digest. `resolve-promotion` carries the candidate binding forward and
sets the final tag target to the approved M. In a fresh shallow promotion runner,
fetch S and import the original bundle using `--promotion-state` instead of
`--candidate-state`. Promotion trusts the approved candidate manifest binding,
so `--source-state` must not be supplied for that import.

Retain exact M, state, manifest bytes and bundle across retries. A rebuild can
produce an identical tree with a different commit timestamp and SHA; that is not
the approved M. Missing retained bundle data fails explicitly rather than causing
a rebuild. If recovering objects via Git instead, fetch the exact approved
candidate/final tag or retained internal ref and validate against the manifest;
the mutable transport ref is never authority by itself. Do not rewrite or reseal
an already published manifest to invent new transport evidence.

Configured moving Action aliases resolve the verified final tag's M. Verify that
the actual tagged tree contains and runs the Action's main/post entry points.
Service-isolated fixtures demonstrate this with representative bundles; they do
not establish that a component's real build and consumer matrix has passed.

## Source snapshots and compatibility

All three source snapshot modes retain their distinct meaning:

| Mode | Content and promotion evidence |
| --- | --- |
| `built-asset` | Build the source archive from S explicitly; unchanged candidate artifact digests prove reuse. M remains the Action tag target. |
| `platform-generated` | GitHub's tag downloads contain M. Detached promotion records a `same-materialized-revision` relation, not a claim that the tag targets S. |
| `none` | No source snapshot evidence is invented merely because the artifact list is empty. The materialized Git-content relation still binds candidate/final M. |

New tooling reads existing exact-source states and v1 manifests. The optional
binding and new promotion relation extend the current format; old 0.1.3 readers
are not promised support for detached manifests. Existing sealed bytes/digests
must remain untouched. Package release/version selection and a consumer's pinned
dependency update are separate release decisions.
