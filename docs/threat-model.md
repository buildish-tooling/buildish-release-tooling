---
title: Threat Model
description: "Security boundaries, controls, residual risks, and deployment responsibilities for release tooling."
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

Status: maintained design model for the development snapshot dated 2026-07-31.

This document covers the release CLI, its checked-in GitHub workflows, stable manifests, OpenPGP
signing, optional artifact verification, and explicit provider or foundation adapters. It separates
controls implemented by this repository from controls that a component or hosting deployment must
provide.

## Security objectives

The release path should:

- bind a release to one exact source commit and immutable version/tag identity;
- prevent a different candidate or different artifact from being silently promoted;
- detect conflicting pre-existing tags, Releases, assets, and manifests;
- limit credentials to the job and adapter that require them;
- avoid placing secret values in authored config, logs, manifests, or reports;
- make interrupted operations safely rerunnable when external state is already identical;
- keep foundation-specific policy opt-in and explicit.

Availability of GitHub, registries, ASF infrastructure, runners, and networks is not guaranteed by
the CLI. The tooling aims to fail safely and preserve diagnosable state when those dependencies fail.

## Protected assets

- source commits selected for release;
- immutable candidate and final tags;
- candidate and final Release metadata and uploaded assets;
- candidate, vote-package, and release manifests;
- manifest digests passed across workflow or approval boundaries;
- signing private keys and passphrases;
- GitHub, registry, and optional foundation credentials;
- workflow definitions, component config, tooling revision, and generated verification evidence.

## Actors and trust assumptions

| Actor | Assumed authority | Not inherently trusted for |
| --- | --- | --- |
| Component maintainer | Dispatch permitted workflows and select release inputs | Bypassing configured policy or substituting artifacts |
| External approval or voting authority | Decide whether an exact candidate may advance | Rewriting candidate identity or release bytes |
| GitHub Actions runner | Execute the selected workflow and access job-scoped credentials | Long-term secret storage or an independent approval record |
| GitHub | Store refs, workflow artifacts, Releases, and assets | Protecting release state from repository administrators who already hold write authority |
| Artifact or foundation service | Store the publication assigned to that adapter | Defining another service's identity or policy |
| Release consumer or verifier | Verify published evidence using independently trusted inputs | Inferring authenticity from a digest fetched beside the protected object |

Repository administrators and credentials with equivalent write authority can mutate GitHub release
state outside this CLI. The tooling detects conflicts it observes; it cannot make GitHub state
immutable against those already-authorized actors.

## Trust boundaries and flows

### Source selection

A workflow dispatch supplies a version and optionally a source ref. Resolution validates configured
selection policy, resolves the ref to an exact commit, and persists typed state. Later jobs use that
commit rather than re-resolving a moving branch.

The component is responsible for branch protection, review policy, CI definitions, and deciding who
may dispatch a release. `verify-source-ref-checks` checks the configured GitHub status/check policy;
it does not prove the quality of the tests themselves.

### Same-run job handoff

Complete state moves between jobs as JSON in GitHub workflow artifacts. A producer emits its
SHA-256, and every release-mutating consumer checks the downloaded bytes before acting. Small scalar
identities pass through job outputs.

This protects against accidental or unauthorized substitution relative to the producing job's
digest. It still trusts the workflow run, GitHub Actions control plane, selected action revisions,
and runner execution environment.

### Cross-run candidate promotion

The candidate Release carries `candidate-manifest.json`. An external gate retains the exact
candidate tag and an independently obtained SHA-256. Promotion re-downloads the manifest and all
declared candidate assets, validates identities and digests, and creates promotion state from those
exact inputs.

The approval or voting mechanism is outside scope. It must bind its decision to that tag and digest;
using a mutable issue field, comment, label, or "latest candidate" lookup without preserving those
values would weaken the boundary.

### External publication

GitHub, package registries, and ASF services are separate trust domains. Provider-neutral manifests
use typed publication records and promotion evidence. Each adapter must validate the identity and
integrity properties its service can actually provide.

GitHub-generated source archives are related by exact source revision, not promised to be
byte-identical across tag names. Uploaded file assets require explicit byte digests. Registry
artifacts require an immutable ecosystem identity.

### Signing

OpenPGP private-key material and an optional passphrase enter through environment variables named in
config. The signer imports exactly one primary secret key into an isolated temporary GnuPG home,
optionally enforces a full fingerprint, removes secret variables from the signing subprocess
environment, supplies a passphrase through loopback input, and sanitizes known secret values from
errors.

The component controls key generation, custody, rotation, secret-store policy, job placement, and
public trust distribution. A compromised authorized runner or workflow with access to the signing
job can use the key during that job; process isolation cannot eliminate that platform trust.

## Principal threats and controls

| Threat | Implemented control | Residual risk or owner |
| --- | --- | --- |
| Moving source ref changes during a run | Resolve once to an exact commit and persist typed state | Git host and repository administrators remain trusted |
| Existing tag points elsewhere | Create-or-verify behavior fails on a commit mismatch | Authorized actors can later mutate or delete refs unless repository policy prevents it |
| Wrong candidate is promoted | Require exact candidate tag and manifest SHA-256; never discover latest | External gate must retain and authenticate both values |
| Candidate asset is replaced | Re-download and verify declared size and SHA-256 before promotion | An attacker controlling both the publication and the gate's digest channel can replace both |
| Same-run state is substituted | Verify producer-emitted SHA-256 before every privileged consumer | Workflow run and Actions infrastructure remain trusted |
| Existing release asset is overwritten | No-clobber upload and exact inventory validation | Authorized manual mutation outside the CLI remains possible |
| Partial failure creates ambiguous state | Bounded commands revalidate identical state and fail on conflicts | Public final release can temporarily lack its final manifest if the last job fails |
| Two releases race for one version | Non-canceling repository/version workflow concurrency | Custom workflows and maintainer-shell commands must provide equivalent serialization |
| Untrusted filename escapes staging directory | Validate artifact names and project-relative paths | New adapters must preserve the same path discipline |
| Secret appears in logs or child environment | Secret values stay out of config; constructed environments and error sanitization | Third-party tools and runners must also handle secrets correctly |
| Wrong signing key is imported | Exactly one primary key; optional full fingerprint check | A production component should configure a fingerprint and protect its trust channel |
| Foundation policy leaks into generic use | Explicit `policy_profiles.asf`, ASF types, and target discriminators | Each project remains responsible for current policy compliance |
| Harness result is mistaken for production assurance | Harness is documented and tested as a local simulation | Deployment settings and live services require separate review |

## Workflow permissions

Checked-in workflows default to `contents: read`. Only jobs that create tags, stage or publish
Releases, or attach manifests receive `contents: write`; source-check jobs receive read access to
checks and statuses. Checkout credentials are not persisted.

All third-party workflow actions are referenced by immutable commits. This reduces unintended
upstream change during a run, but reviewing and updating those dependencies remains repository
maintenance rather than a proof that their code is safe.

GitHub Environment placement is component policy. A component that requires approval before all
mutations must attach an environment to every relevant write job, not only the job that reads an
environment-scoped secret. The local harness cannot validate repository Environment rules.

## Optional ASF and verification subsystems

The ASF adapter validates explicit ASF dist targets and keeps ASF credentials, trust roots, vote
wording, Incubator status, and ATR settings in ASF-named types. It does not automate vote outcome
decisions. Apache projects must follow current ASF policy and their project governance.

The full `verify-rc` subsystem verifies signed source candidates and can rebuild or inspect declared
artifact kinds. Its report describes checks performed; it does not prove an external vote passed,
that every possible platform was tested, or that a successful build contains no malicious behavior.

## Out of scope and deployment responsibilities

The following are not vulnerabilities in this repository without evidence that the CLI crosses its
promised boundary:

- a user who already has repository write authority changing release state;
- a component granting secrets or GitHub Environments to the wrong jobs;
- weak branch protection, runner isolation, or external approval policy;
- compromise of GitHub, a registry, ASF infrastructure, or a configured signing key;
- unavailable external services or local tools;
- a project choosing policy that is insufficient for its foundation or ecosystem.

Those are real deployment risks. Components should document their dispatch authorization,
environment approvals, runner trust, secret access, signing-key trust path, external gate, and
incident response.

## Review triggers

Review this model when adding a hosting provider, foundation profile, publication target, credential
type, signing mechanism, untrusted workflow trigger, self-hosted runner, reusable workflow boundary,
manifest schema version, artifact kind, or automated approval integration.

Report suspected vulnerabilities through the repository's
[security policy](https://github.com/buildish-tooling/buildish-release-tooling/security/policy). A
security finding should identify the actor, required access, trust boundary crossed, affected asset,
and concrete security impact; a test that grants the actor the protected capability is not by itself
proof of a boundary crossing.
