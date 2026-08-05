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

# Release Tooling Release Process

Buildish Release Tooling publishes Python distributions as `buildish-release-tooling`. Maintainers
first rehearse the exact version through the direct lifecycle on TestPyPI. Production publication
uses a retained GitHub candidate followed by explicit promotion of that candidate's immutable
manifest and artifact bytes.

The operator performing a release must have permission to dispatch the repository's release
workflows. GitHub Environments enforce any additional approval required for signing, TestPyPI, or
PyPI publication. The person approving production promotion must obtain the candidate tag and
candidate-manifest SHA-256 from the candidate run or an independent verification run; promotion
must not select a candidate by recency.

## Before starting

1. Choose the final version and ensure it exactly matches the version in `pyproject.toml`.
2. Prepare and review the Markdown fragment at
   `buildish-release-tooling/release-notes/<version>.md`. It must be present in the selected source
   commit; candidate resolution binds its exact bytes and SHA-256 into release state.
3. Select an exact source commit already reachable from protected `main` and confirm the trusted
   `Required Checks` result passed for that commit.
4. Confirm the `testpypi`, `release-candidate`, and `pypi` GitHub Environments and both PyPI Trusted
   Publisher registrations described in the [self-release guide](../docs/self-release.md) are still
   correctly configured.
5. Run `make check` from a clean checkout of the selected commit. Run the local production-shaped
   candidate-to-promotion rehearsal documented in the harness guide when the release workflows or
   release tooling changed since the last successful rehearsal.

## TestPyPI rehearsal

Dispatch `.github/workflows/release-testpypi.yml` with the final version and selected source commit.
Require the workflow to verify the exact wheel and sdist, their index digests, and the PEP 740
Trusted Publisher identity. Inspect the TestPyPI project page and install both retained
distributions while resolving runtime dependencies from production PyPI.

TestPyPI and PyPI have independent immutable filename namespaces. A TestPyPI upload does not consume
the production version, but the same TestPyPI version cannot be replaced by a later candidate.
If the rehearsal exposes a source or packaging defect, fix it and choose a new final version before
another TestPyPI publication.

## Production candidate

Dispatch `.github/workflows/release-candidate.yml` with the final version, selected source commit,
candidate label `rc`, and vote profile `none` unless the project has deliberately adopted another
profile. The workflow builds reproducible wheel and sdist files, signs them, and publishes a
retained GitHub prerelease with `candidate-manifest.json`.

Record the candidate tag and SHA-256 of `candidate-manifest.json`. Confirm the candidate GitHub
Release contains the reviewed notes from `buildish-release-tooling/release-notes/<version>.md`, and
candidate assets. At least one maintainer should independently run
`.github/workflows/release-verify-candidate.yml` with that exact tag and digest before promotion.
Any source, metadata, artifact, signature, or release-note change requires a new candidate; do not
modify a published candidate in place.

## Production approval and promotion

Production approval means approval of one exact candidate tag and candidate-manifest SHA-256.
After approval, dispatch `.github/workflows/release-promote.yml` with those values and the final
version. The workflow verifies and reuses the candidate's retained bytes, creates the final GitHub
Release, publishes only the wheel and sdist to PyPI, verifies their PEP 740 provenance, and attaches
the final release manifest.

The release is complete only when all of the following are true:

- the final GitHub Release is public and contains the expected signed assets and release manifest;
- PyPI contains exactly the expected wheel and sdist with matching SHA-256 values;
- package-index provenance identifies `buildish-tooling/buildish-release-tooling`,
  `release-promote.yml`, and the `pypi` environment;
- both installed distributions expose working `buildish-release-tooling` and
  `buildish-release-harness` help commands; and
- the public release notes describe the shipped user-visible changes.

## Failure and recovery

GitHub and package-index publication are not atomic. Preserve the failed workflow run and its
artifacts before taking recovery action.

- Rerun failed jobs when the retained state and artifact digests still match.
- A matching complete PyPI file set skips upload and continues verification.
- A matching partial PyPI file set may upload only the missing file after preflight validation.
- An unexpected filename or conflicting byte digest is a hard stop. Do not overwrite or delete an
  immutable package-index file; investigate and publish a new version when recovery cannot prove
  the intended bytes.
- Do not start an independent promotion run with different candidate evidence as a substitute for
  rerunning a failed job.

There is no rollback that removes an immutable published package safely. For a defective production
release, stop further promotion, document the issue, yank the affected PyPI release when appropriate,
and publish a corrected higher version through the complete process. Preserve the GitHub Release and
manifests as audit evidence unless a security response requires restricted handling.

See the [self-release guide](../docs/self-release.md) for the workflow architecture, repository
settings, exact Trusted Publisher identities, and detailed recovery invariants. The general product
documentation describes tooling capabilities; this file defines the maintainer process for
publishing Release Tooling itself.
