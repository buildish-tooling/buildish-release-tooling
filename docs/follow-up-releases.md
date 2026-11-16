---
title: Follow-Up Self-Releases
description: "Prepare subsequent releases and recover interrupted publication."
weight: 37
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

# Follow-Up Self-Releases

Use the same TestPyPI, candidate, verification, and promotion workflows after the first release.
The [first-release guide](../first-self-release/) gives the exact dispatch commands and acceptance
checks. This page covers recurring preparation and recovery; deployment identities remain in the
[self-release overview](../self-release/).

## Prepare the next version

1. Select an unused final semantic version. Update `pyproject.toml` and refresh the local project
   entry in `uv.lock` with the repository's normal lock-maintenance process. Review the diff.
2. Add reviewed notes at `buildish-release-tooling/release-notes/<version>.md`. Describe user-visible
   changes and compatibility implications for CLI arguments, configuration, and manifest consumers.
3. Confirm wheel and sdist metadata carries the selected version. The packaging tests derive
   expected archive names and metadata paths from `pyproject.toml`.
4. If dependencies or legal inputs changed, regenerate the preliminary legal artifacts with
   `make release-legal-preliminary`, review them, and verify the actual distribution legal files.
   If model contracts changed, run `make schemas` and review the generated contract changes.
5. Run `make check`; for documentation changes run the aggregate repository's
   `make site-check-local` from its `site/` directory. Run `make release-integration-check` when
   release logic, workflows, dependencies, or deployment assumptions changed since the last
   successful rehearsal.
6. Review and merge preparation changes. Select a clean, pushed exact source SHA reachable from
   protected `main`, with successful trusted push CI. Audit environments, signing-key validity,
   fingerprint, action permissions, and both Trusted Publisher registrations for drift.

The currently configured source gate requires protected `main`. A maintenance branch is not an
alternative release source without a deliberate change to source and check policy. Source version,
release notes, and workflow revision must be reviewed together.

## Rehearse, select, and promote

Follow the commands and evidence checks in the [first-release sequence](../first-self-release/):

1. Repeat TestPyPI when publication, authentication, dependencies, or packaging behavior changes.
   For documentation-only edits or a version bump after a successful rehearsal, another upload is
   optional. When running it, select the exact final version/source and verify files and attestations.
2. Create a signed production candidate with candidate label `rc` and vote profile `none`.
3. Capture the resolved tag and exact `candidate-manifest.json` SHA-256. Independently verify the
   candidate, including its signatures and installability.
4. Obtain approval for that identity, then promote it without rebuilding the distributions.
5. Require final manifest and durable evidence attachment, exact PyPI file and publisher checks,
   and successful production installation checks. Preserve the release record.

A rejected candidate stays retained. Source, artifact, signature, metadata, or note corrections
require another candidate. If the correction changes files already uploaded to TestPyPI, increment
the package version as well; increasing only the candidate number cannot replace index files.

Published contracts should be inspected at the released tag. Consumers should pin the chosen
immutable tooling revision and assess contract changes before upgrading. The Python package's
internal module layout is not a supported API.

## Failure and recovery

Publication across GitHub and PyPI is not atomic. Preserve the failing run, inputs, artifacts, and
digests before taking recovery action.

| Failure state | Recovery |
| --- | --- |
| Failure before publication | Correct operational prerequisites and rerun failed jobs with retained inputs; changed source requires a new candidate. |
| PyPI published, GitHub still draft | Keep the same candidate identity. Rerun with retained state; package preflight accepts only matching files and skips duplicate upload, then evidence/manifest sealing completes before GitHub publication. |
| Upload succeeded but index/provenance visibility timed out | Check the visible files against the candidate, then rerun failed verification jobs with retained inputs. Post-upload polling is bounded; do not choose a new version solely for a visibility delay. |
| PyPI exact file set already complete | Upload is skipped; exact-set and attestation verification must still succeed. |
| Unexpected filename, size, digest, tag target, or publisher | Stop and investigate the conflict. Do not overwrite assets or delete index files to bypass validation. |
| Draft has evidence, final manifest missing | Rerun the complete promotion with the same version, tag, and candidate-manifest digest. Exact configured reserved evidence assets are reused; attach the sealed manifest before publication. |
| Sealed draft, publication failed | Rerun finalization with the retained sealed-manifest digest, or review a complete promotion rerun. Identical existing evidence/manifest assets are reused without upload. |
| Immutable GitHub Release is public but lacks evidence/manifest | Stop: uploading cannot repair a locked release. Preserve workflow artifacts before expiry and document the incomplete record; any separately hosted completion record needs explicit review. Do not delete/recreate the Release or disable immutability as a retry strategy. |
| Retained run artifacts expired or unusable | Review a new complete promotion run with the same immutable candidate inputs. Do not substitute a different candidate for an already-published version. |

For ordinary transient failures, prefer rerunning failed jobs while their state remains available.
Full promotion reruns are supported while completing an exact draft or revalidating a complete
immutable publication. A sealed manifest uses the stable Release creation time so an identical rerun
seals the same bytes rather than inventing a publication time. A fresh candidate
dispatch resolves another candidate number; it is not a substitute for resuming a failed candidate
run. Never infer an approved candidate by recency.

An already-published defective package has no safe rollback that removes its immutable bytes.
Document the defect, consider a separately approved PyPI yank, and release a corrected higher
version through the full sequence. Preserve tags, candidates, manifests, and evidence as the release
record unless the project's security-response process requires restricted handling.

The first `0.1.2` promotion published GitHub and PyPI before durable evidence/manifest attachment.
Its GitHub Release became immutable, leaving that record incomplete despite successful package
and attestation verification. Preserve its tags and published distributions. A corrected later
release uses draft sealing and publication last; a fresh version alone cannot repair the old record.
