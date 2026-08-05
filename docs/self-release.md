---
title: Self-Releasing Buildish Release Tooling
description: "How Buildish Release Tooling uses its own lifecycles, workflows, and release controls."
weight: 35
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

# Self-Releasing Buildish Release Tooling

Buildish Release Tooling uses its own release state, commands, and workflows to publish itself.
This is the project's reference deployment of Buildish rather than a configuration that every
component must copy unchanged. Components can use different artifacts, approval policy, signing
policy, environments, and publication targets while preserving the same trust and handoff
boundaries.

The links on this page point to `main` and therefore describe the current, unreleased workflow.
For a completed release, use the files at that release's immutable tag instead.

## Checked-in release definition

The production release uses the candidate lifecycle. TestPyPI uses a separate direct-lifecycle
configuration so the project can exercise direct state composition without creating a test tag or
GitHub Release.

| File | Role |
| --- | --- |
| [`release-config.yaml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/buildish-release-tooling/release-config.yaml) | Production candidate and promotion policy, artifacts, signing, and publication targets |
| [`release-notes/`](https://github.com/buildish-tooling/buildish-release-tooling/tree/main/buildish-release-tooling/release-notes) | Reviewed version-specific Markdown fragments bound into candidate and final release state |
| [`release-testpypi-config.yaml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/buildish-release-tooling/release-testpypi-config.yaml) | Direct-lifecycle state used by the TestPyPI rehearsal |
| [`release-testpypi.yml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/.github/workflows/release-testpypi.yml) | Build, publish, recover, and verify an exact version on TestPyPI |
| [`release-candidate.yml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/.github/workflows/release-candidate.yml) | Build and sign reproducible distributions, then publish a retained GitHub candidate |
| [`release-verify-candidate.yml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/.github/workflows/release-verify-candidate.yml) | Independently verify a named candidate and manifest digest |
| [`release-promote.yml`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/.github/workflows/release-promote.yml) | Promote one exact candidate to the final GitHub Release and PyPI |

The generic direct GitHub workflow is a
[`harness fixture`](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/buildish-release-tooling/harness/workflows/release-direct.yml),
not a live self-release entry point.

The production configuration requires
`buildish-release-tooling/release-notes/{version}.md`. Candidate resolution reads the file from the
selected source commit, not the dispatching workflow checkout, and binds its exact Markdown and
SHA-256 into `candidate-manifest.json`. Promotion reuses those candidate-bound notes. Changing the
notes therefore requires a new source commit and candidate. The TestPyPI-only configuration omits
this block because it does not create a public GitHub Release.

## Trust boundaries

The self-release workflows keep release source, executable workflow code, and credentials separate:

1. The resolver checks out `github.workflow_sha`, resolves an exact source commit, and writes typed
   release state.
2. The source commit must be reachable from protected `main`.
3. The `Required Checks` result must come from `.github/workflows/ci.yml`, triggered by `push` on
   `main`. A same-name status or check from another producer does not satisfy the gate.
4. Only the unprivileged build job checks out and executes the selected source.
5. Jobs with signing material, an OIDC token, or `contents: write` execute the workflow revision
   identified by `github.workflow_sha`. Selected-source files enter those jobs only as data.
6. Each same-run state or artifact handoff has a producer-emitted SHA-256 that the consumer verifies
   before signing or publication.

These boundaries are implemented jointly by the workflows, release configurations, repository
rulesets, and GitHub Environments. The repository files cannot prove that the external settings are
still configured as described below.

## GitHub repository settings

Configure these controls before using the self-release workflows.

### Rulesets

The `main` ruleset targets the default branch and currently requires:

- pull requests with one approving review and approval after the last push;
- squash merging and linear history;
- the `Required Checks` check from the GitHub Actions integration;
- protection against deletion and non-fast-forward updates.

Administrator and maintain-level bypasses are deliberate operational escape hatches. Using a bypass
changes the assurance supplied by the branch gate and should therefore be an explicit maintainer
decision.

The `Release Tags` ruleset targets `v*` and prevents update, deletion, and non-fast-forward changes
without a bypass. Candidate and final tags both match this pattern. The separately configured
`Release Branches` ruleset targets `release/**`; the current self-release path selects protected
`main`, so it does not require a release branch.

### Actions policy

GitHub Actions is enabled with selected actions and required full-SHA pinning. GitHub-owned actions
are allowed. The release workflows additionally require these third-party publishers:

- `astral-sh/setup-uv`;
- `pypa/gh-action-pypi-publish`.

The repository pins every action invocation to a full commit SHA and leaves the corresponding
version in a comment for Renovate and human review.

### Environments

| Environment | Used by | Required configuration |
| --- | --- | --- |
| `testpypi` | TestPyPI OIDC publication | Restrict deployment branches to `main` |
| `pypi` | Production PyPI OIDC publication | Restrict deployment branches to `main`; add required reviewers if production publication needs explicit approval |
| `release-candidate` | Candidate signing and GitHub candidate publication | Create this environment, restrict it to `main`, and preferably require a reviewer |

An environment protects only jobs that declare its name. Adding a secret to an environment does not
protect a different `contents: write` job automatically.

Create all three under **Settings > Environments**. Select only `main` in each environment's
deployment-branch policy. The `testpypi` and `pypi` environments need no stored package-index
credential: their publishing jobs use GitHub OIDC and the Trusted Publisher registrations below.
For `release-candidate`, add the two environment secrets listed in the next section. If dispatching
and approving a signing operation should be separate decisions, add a required reviewer and enable
the option that prevents the initiating user from approving their own deployment.

### Secrets and variables

The candidate workflow reads these values:

| Kind | Name | Purpose |
| --- | --- | --- |
| Environment secret in `release-candidate` | `BUILDISH_RELEASE_GPG_SECRET_SUBKEY` | ASCII-armored signing-secret export |
| Environment secret in `release-candidate` | `BUILDISH_RELEASE_GPG_PASSPHRASE` | Passphrase for that signing subkey |
| Organization or repository variable | `BUILDISH_RELEASE_GPG_SIGNING_FINGERPRINT` | Expected signing-subkey fingerprint |

Store both sensitive values as secrets of this repository's `release-candidate` environment. Do not
grant this repository an organization-level or repository-level secret with either name: such a
secret could be referenced by a job that does not pass the environment gate. If another component
uses the same signing key, give that repository's signing environment its own protected copy.

If either secret is currently provided at organization or repository scope, first create the
environment-scoped copy, verify its name, and then remove this repository's access to the broader
copy. GitHub resolves a same-named environment secret for an environment-bound job, but leaving a
broader copy available would still let a different job request it without passing this gate.

The workflow references the private key and passphrase only in the `prepare-assets` job, after its
`release-candidate` environment gate; the unprivileged build job does not receive them. The public
fingerprint is not secret and can remain an organization variable. The corresponding public key is
published in the [`KEYS` file](https://buildish.org/KEYS). See the
[`release-signing key guide`](https://github.com/buildish-tooling/buildish/blob/main/RELEASE-SIGNING-KEY.md)
for generation, backup, renewal, and revocation procedures.

## PyPI Trusted Publishers

Neither package-index workflow uses a long-lived PyPI token. Configure the following GitHub Trusted
Publisher identities exactly:

| Index | Owner | Repository | Workflow | Environment |
| --- | --- | --- | --- | --- |
| TestPyPI | `buildish-tooling` | `buildish-release-tooling` | `release-testpypi.yml` | `testpypi` |
| PyPI | `buildish-tooling` | `buildish-release-tooling` | `release-promote.yml` | `pypi` |

Only the publishing jobs receive `id-token: write`. After publication, an unprivileged job reads the
package-index state and PEP 740 provenance back, requires the expected repository, workflow, and
environment identity, ignores bundles from unrelated publishers, and requires a cryptographically
verified PyPI Publish Attestation for each retained distribution.

## Release sequence

### 1. Rehearse on TestPyPI

Dispatch
[`release-testpypi.yml`](https://github.com/buildish-tooling/buildish-release-tooling/actions/workflows/release-testpypi.yml)
with the exact version and, optionally, an exact source commit. The workflow:

- resolves and retains `DirectReleaseState`;
- applies the protected-`main` and trusted-check gates;
- builds the wheel and sdist reproducibly;
- preflights existing TestPyPI state;
- publishes through the `testpypi` environment when files are absent or partially present;
- verifies the exact remote files and their PEP 740 provenance.

TestPyPI and PyPI have independent project/version namespaces, so this rehearsal does not consume
the production PyPI version.

### 2. Publish a production candidate

Dispatch
[`release-candidate.yml`](https://github.com/buildish-tooling/buildish-release-tooling/actions/workflows/release-candidate.yml)
with the final version, reviewed source commit, candidate label `rc`, and normally `none` for the vote
profile. The workflow builds the wheel and sdist twice, rebuilds the wheel from the sdist, smoke
tests both formats, creates checksums and detached OpenPGP signatures, and publishes a GitHub
prerelease with `candidate-manifest.json`.

Retain the exact candidate tag and SHA-256 of `candidate-manifest.json`. Reviewers can run
[`release-verify-candidate.yml`](https://github.com/buildish-tooling/buildish-release-tooling/actions/workflows/release-verify-candidate.yml)
with those values without mutating the candidate.

### 3. Promote the selected candidate

After the external approval decision, dispatch
[`release-promote.yml`](https://github.com/buildish-tooling/buildish-release-tooling/actions/workflows/release-promote.yml)
with the final version, exact candidate tag, and retained candidate-manifest SHA-256. Promotion:

- downloads and verifies the candidate manifest and every candidate asset;
- creates the final tag at the candidate's exact source commit;
- stages, verifies, and publishes the GitHub Release;
- publishes only the retained wheel and sdist to PyPI through the `pypi` environment;
- reads back and verifies the PyPI files and PEP 740 provenance;
- selects the verified PyPI Publish Attestations from the configured Trusted Publisher, retains
  those exact evidence documents as GitHub Release assets, and binds their asset URLs, SHA-256
  digests, distribution digests, and publisher claims into the final release manifest;
- attaches that final release manifest after both publication channels verify successfully.

The external approval process is intentionally outside Release Tooling. It selects one immutable
candidate identity; the promotion workflow does not discover or substitute the "latest" candidate.

## Recovery behavior

PyPI and GitHub publication cannot be atomic. Both package-index workflows therefore inspect the
index before requesting an upload:

- absent files proceed to publication;
- a matching partial set uploads only after every existing file matches by name, size, and SHA-256;
- a complete exact set skips publication and continues with verification;
- any unexpected or conflicting file stops the workflow.

The publisher's `skip-existing` option is used only after that preflight. A successful rerun must
still pass the exact-set and attestation verification steps. The verification handoff uses a
SHA-256 inventory covering the publication result, downloaded provenance, and selected attestation
evidence.
Candidate and promotion state files, artifact inventories, and publication results are retained as
workflow artifacts to support failed-job analysis and recovery. The final manifest remains durable
with the GitHub Release and identifies the exact retained PyPI Publish Attestation assets
independently of that temporary workflow-artifact retention. The live Integrity API response is
only the mutable source from which that exact evidence was selected.
If interruption occurs between uploading the reserved
`buildish-verification-evidence--*` assets and attaching the stable manifest, rerun the complete
promotion workflow with the same immutable inputs. Earlier jobs tolerate only the exact configured
evidence names in that reserved orphan namespace, and the attachment job accepts each existing
asset only when its size and SHA-256 match
the freshly verified evidence exactly.

## Adapting the example

A component adopting this design should copy the invariants, not necessarily the repository's
names:

- execute trusted tooling in credential-bearing jobs;
- treat the selected source and built artifacts as untrusted data until verified;
- bind cross-job and cross-run handoffs to immutable digests;
- give write, signing, and OIDC credentials only to the jobs that need them;
- configure and independently audit the repository settings that the workflow assumes;
- verify external publication after mutation rather than treating a successful upload step as final
  evidence.

See [Workflow composition](../release-workflows/) for the general model and
[Candidate release and exact promotion](../candidate-release/) for the lifecycle walkthrough.
