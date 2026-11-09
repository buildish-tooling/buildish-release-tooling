---
title: First Self-Release
description: "Prepare and publish the first Buildish Release Tooling release."
weight: 36
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

# First Self-Release

Use this procedure for the first publication of `buildish-release-tooling`. It uses the existing
GitHub Actions workflows: TestPyPI rehearsal, signed GitHub candidate, independent verification,
and promotion to GitHub and PyPI. No additional release tool is required.

Run local commands from the Release Tooling repository root. GitHub CLI examples assume an
authenticated maintainer with workflow-dispatch access. These commands start live workflow runs:
candidate and promotion workflows create tags and Releases, and index workflows upload immutable
package files.

## Establish the release deployment

Audit the [self-release deployment settings](../self-release/) before selecting a source commit:

- Protected `main` must require CI's `Required Checks`; the source gate also checks its exact
  workflow, push event, and branch provenance.
- The `v*` tag ruleset must allow initial tag creation and prevent later mutation.
- Actions policy must allow the pinned actions used by the release workflows.
- Environments `testpypi`, `release-candidate`, and `pypi` must restrict deployment to `main`.
  Choose required-reviewer policy explicitly; merely creating an environment supplies no reviewer.
- `release-candidate` must contain `BUILDISH_RELEASE_GPG_SECRET_SUBKEY` and
  `BUILDISH_RELEASE_GPG_PASSPHRASE`. Their presence does not prove that the key is valid or usable.
  The organization/repository variable `BUILDISH_RELEASE_GPG_SIGNING_FINGERPRINT` must match the
  reviewed production configuration and public signing key in `https://buildish.org/KEYS`.
- Register the exact Trusted Publishers on both TestPyPI and PyPI. For a project that does not yet
  exist, use the index's pending-publisher registration. Production uses `release-promote.yml`
  with environment `pypi`; TestPyPI uses `release-testpypi.yml` with environment `testpypi`.

The expected owner and repository for both publishers are `buildish-tooling` and
`buildish-release-tooling`. Check registrations in the index account; GitHub environment existence
cannot establish that the package index trusts the workflow.

## Prepare an exact source

1. Choose a final version matching `pyproject.toml`, initially `0.1.0` unless changed deliberately.
   Review `buildish-release-tooling/release-notes/<version>.md` at the selected source commit.
2. Run `make check`. Run `make release-integration-check` to execute the checked-in candidate and
   promotion workflows with isolated service substitutes. It needs the existing `act` runner
   (or `gh act` extension) and Docker; it does not establish live signing or OIDC readiness.
   If those tools are unavailable, record the gap and run the rehearsal on a prepared machine.
3. After review and merge, choose a clean, pushed source commit reachable from protected `main`.
   Require successful push CI on that exact commit. Any release-preparation edits require checks
   on the resulting commit again.
4. Record the workflow revision used by each dispatch as well as the source SHA. These are
   separate identities: privileged jobs execute the dispatched workflow revision.

Set these shell values to reviewed identities before using the later examples:

```bash
release_repo=buildish-tooling/buildish-release-tooling
release_version=0.1.0
release_source=REPLACE_WITH_FULL_REVIEWED_SOURCE_SHA
```

Inspect existing tags, releases, and both indexes for conflicts. Do not assume that a previously
used version is reusable, and do not remove published state to make the checks pass.

## Rehearse with the real TestPyPI service

Dispatch the TestPyPI workflow:

```bash
gh workflow run release-testpypi.yml --repo "$release_repo" --ref main \
  -f version="$release_version" -f source_ref="$release_source"
```

Record the exact run ID from the Actions UI or `gh run list`, then inspect that run with
`gh run view RUN_ID --repo "$release_repo"` and wait for every required job to succeed. The workflow
builds reproducible wheel/sdist bytes, uploads missing files, reads them back, and verifies their
Trusted Publisher attestations. It creates neither a Git tag nor a GitHub Release.

Inspect its retained distributions and publication evidence. Install the exact downloaded wheel
and sdist in separate disposable environments, resolving dependencies from production PyPI, and
run both `buildish-release-tooling --help` and `buildish-release-harness --help`. Avoid resolving all
dependencies from TestPyPI. The workflow performs packaging smoke tests too; these manual checks
exercise the bytes retrieved from the index.

If a source or packaging change alters already-uploaded files, choose a new version before
repeating this rehearsal. TestPyPI filenames cannot be replaced. Its namespace is independent of
production PyPI, so a successful rehearsal does not consume the production version.

## Publish and review a candidate

Dispatch the candidate workflow:

```bash
gh workflow run release-candidate.yml --repo "$release_repo" --ref main \
  -f version="$release_version" -f source_ref="$release_source" \
  -f candidate_label=rc -f vote_profile=none
```

The workflow signs the distributions and creates a tag and public GitHub prerelease. Capture the
resolved candidate tag from this run, rather than assuming `rc1` or choosing the newest release.
Download its `candidate-manifest-RUN_ID` workflow artifact and independently compute
`sha256sum candidate-manifest.json`. Compare the result with the producer's recorded digest and the
manifest attached to that candidate. Record the exact tag and lowercase SHA-256:

```bash
release_candidate_tag=REPLACE_WITH_RESOLVED_CANDIDATE_TAG
release_candidate_digest=REPLACE_WITH_CANDIDATE_MANIFEST_SHA256
```

Check source SHA, final version, release notes, wheel/sdist inventory, checksums, and detached
signatures. Verify OpenPGP signatures separately against the reviewed public key and fingerprint;
a matching inventory digest alone does not establish signer identity. Do this in a disposable
keyring, without importing keys into the operator's normal keyring.

Independently dispatch the read-only verifier for that identity:

```bash
gh workflow run release-verify-candidate.yml --repo "$release_repo" --ref main \
  -f candidate_tag="$release_candidate_tag" \
  -f candidate_manifest_digest="$release_candidate_digest"
```

Require a successful result and retain its evidence before approving promotion. A change to source,
notes, metadata, signatures, or artifacts requires a new candidate.

## Promote and accept the release

After approval of the exact candidate tag and digest:

```bash
gh workflow run release-promote.yml --repo "$release_repo" --ref main \
  -f version="$release_version" -f candidate_tag="$release_candidate_tag" \
  -f candidate_manifest_digest="$release_candidate_digest"
```

This creates the final tag and GitHub Release and publishes the candidate's retained wheel and
sdist to production PyPI. Require the entire workflow to succeed, including verification and final
manifest attachment. A visible GitHub Release alone is not completion.

Accept the release only when:

- the final tag targets the reviewed source SHA and the candidate remains retained;
- GitHub contains the expected distributions, sidecars, final `release-manifest-v1.json`, and
  reserved `buildish-verification-evidence--*` assets;
- candidate and final distribution digests match, and PyPI contains exactly that wheel and sdist;
- verified PyPI provenance names the expected repository, `release-promote.yml`, and `pypi`;
- the final manifest binds the exact candidate and durable attestation evidence;
- installation of each production distribution exposes both working CLI help commands; and
- release notes describe the shipped behavior and consumers can select an immutable tooling tag
  or commit.

Retain the source SHA, workflow SHAs, run IDs, candidate identity/digest, final manifest digest,
distribution hashes, and approval decision in the project's release record before the workflows'
30-day artifact retention expires. Final release manifests and retained evidence remain on GitHub.

Use the [follow-up release guide](../follow-up-releases/#failure-and-recovery) for interrupted-run
recovery. The [self-release overview](../self-release/) explains the deployment and trust model.
