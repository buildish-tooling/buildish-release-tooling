---
title: "ATR Integration Assessment"
description: "Assessment of how buildish-release-tooling and Apache Trusted Releases can work together."
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

# ATR Integration Assessment

## Scope

This document assesses how `buildish-release-tooling` could work together with
the Apache Trusted Releases initiative (ATR), with emphasis on:

- what ATR currently is,
- what `buildish-release-tooling` already does that fits ATR well,
- what is missing or blocked today, and
- what an integration path should look like in practice.

Assessment date:

- 2026-04-27

This is an architectural assessment, not an implementation plan for one exact
ATR API version.

## High-Level Summary

`buildish-release-tooling` and ATR should be treated as companions, not
competitors.

The cleanest model is not "replace one with the other". It is:

- `buildish-release-tooling` remains the repo-local release orchestrator that
  knows how to select source, build artifacts, sign them, stage them, and emit
  machine-readable release metadata.
- ATR becomes the ASF-hosted release-state platform that can store candidate and
  current release records, manage committee keys and policy, run server-side
  checks, expose a UI and API, and eventually own more of the publication
  lifecycle.

That creates a practical win for ATR:

- ATR gets real candidate bundles, signatures, checksums, manifests, SBOMs, and
  project feedback from actual release workflows,
- ATR can validate its checks and data model against diverse ASF project shapes
  without first having to replace repo-local release orchestration everywhere,
- ATR gains a low-friction adoption path through projects that already have
  disciplined release metadata and artifact production.

It also creates a practical win for projects using
`buildish-release-tooling`:

- projects keep their existing repo-local release flow instead of waiting for a
  complete ATR-native migration,
- projects get centralized candidate records, server-side checks, and stable ATR
  URLs and identifiers as additional release evidence,
- projects can try ATR in advisory mode first, learn where their release shape
  does or does not fit ATR well, and tighten policy later if that proves useful.

The main near-term conclusion is:

- `buildish-release-tooling` can work with ATR now in principle, but mostly as
  an ATR-aware producer and companion tool, not as a native ATR client yet.

The main blocking conclusion is:

- ATR is still Alpha software, its public docs explicitly say the actual
  implementation will diverge, and the current Alpha still requires final
  release commits to `svn:dist/release` by hand.

So the best current strategy is:

- integrate with ATR as an optional secondary system of record for candidate
  state and automated checks,
- keep `buildish-release-tooling` authoritative for the repo-local build and
  signing flow,
- keep local human verification as first-class, because ASF policy still
  requires voters to download, verify, compile, and test signed source releases
  on their own hardware.

## What ATR Is, Today

From the current ASF Tooling pages and ATR Alpha docs, ATR is aiming to be an
ASF-hosted release platform with:

- candidate, current, archive, and other lifecycle stages,
- PMC and product-line level release records,
- committee-managed public signing keys,
- automated checks for signatures, hashes, archive layout, licensing, and SBOMs,
- release policy settings including vote timing and checklist text,
- a web UI,
- an API, and
- support for multiple distribution channels over time.

Important current-state facts:

- the Tooling initiative says ATR is intended to help ASF projects with
  compliance, SBOMs, attestations, and release-process automation,
- the public ATR Alpha is open to ASF projects for testing,
- the platform services and data-model pages both warn that they are
  discussions and that the implementation will diverge,
- the current Alpha still says releases must be committed by hand to
  `svn:dist/release`,
- ATR already exposes automated checks and a documented API surface.

This matters because the correct integration target is not a final, stable ATR
contract yet. It is a moving Alpha platform with a credible long-term shape.

## What `buildish-release-tooling` Is, Today

In contrast, `buildish-release-tooling` is a repo-local CLI orchestrator.

Its strengths are:

- selecting and validating the source ref for a release,
- creating reproducible source archives,
- generating detached signatures and checksum sidecars,
- staging source RC artifacts to ASF dist,
- publishing final source releases to ASF dist,
- mirroring convenience assets to GitHub Releases,
- generating a signed `rc-vote-manifest.json`,
- carrying tooling and workflow provenance in that manifest, and
- giving projects a versioned release CLI that can be pinned by Git ref.

Its current boundaries are also clear:

- it is strongly Git-oriented,
- it still has a GitHub-shaped release surface in several places,
- its `verify-rc` and `inspect-repro` commands now cover signed-manifest
  verification, source-artifact checks, typed secondary-artifact verification,
  and host-direct reproducibility checks, but isolated rebuild execution and
  ATR evidence ingestion remain follow-up work,
- it now has typed secondary-artifact support for Maven repositories, OCI
  images, PyPI distributions, and npm packages, but policy depth still trails a
  dedicated release-state platform,
- it does not yet have a first-class ATR integration layer.

## The Architectural Relationship

The most useful framing is:

- ATR is a platform.
- `buildish-release-tooling` is an orchestrator.

Those are not redundant roles.

### What ATR should own

ATR is a good place to own cross-project and ASF-wide concerns:

- committee keys and generated `KEYS` files,
- release lifecycle stage and phase tracking,
- vote policy settings,
- server-side automated checks,
- centralized release and candidate pages,
- audit history,
- distribution-channel metadata,
- an API that other tools can consume.

### What `buildish-release-tooling` should own

`buildish-release-tooling` is a good place to own project-repo-local concerns:

- source selection and release-branch policy,
- materialization steps needed to build release artifacts,
- project-specific build commands,
- local GPG signing invocation,
- project-specific secondary artifact registration,
- machine-readable RC vote manifests,
- local and workflow-side reproducibility verification.

### Why this split is healthy

It keeps the complex, project-specific build logic close to the repo, while
letting ATR own the ASF-shared release-state layer.

That is especially important because ASF policy still requires local human
verification. Even if ATR automates many checks, it does not eliminate the need
for a local verifier path.

## Good Fit Areas

### 1. Source-release packaging is already aligned

ATR expects candidate content to include artifacts with signatures and checksum
files. `buildish-release-tooling` already produces exactly that for the source
artifact set.

This is one of the strongest fit points:

- source artifact
- detached `.asc`
- `.sha512`
- incubator-aware naming
- ASF dist staging

In other words, the existing buildish source-RC flow is already close to the
artifact bundle ATR expects to inspect.

### 2. The `rc-vote-manifest.json` is already close to useful ATR-side metadata

The current RC vote manifest already carries several fields ATR or ATR-adjacent
consumers would care about:

- version
- release line
- release branch
- source commit SHA
- RC tag
- final tag
- tooling provenance
- GitHub workflow provenance
- trust-root metadata for ASF `KEYS`
- authoritative source artifact, signatures, and checksums
- secondary artifacts

That means the manifest is already a strong candidate for the repo-local,
machine-authored source of truth that can be mapped into ATR release records or
attached to them as provenance.

### 3. Generic secondary files and SBOMs are already tractable

ATR already has first-class logic for:

- `.sha256` and `.sha512` checksum files,
- `.asc` signatures,
- archive integrity and structure checks,
- CycloneDX SBOMs with `.cdx.json` suffix,
- SBOM-related scoring and augmentation tasks.

`buildish-release-tooling` already has a generic secondary-artifact path through
`finalize-rc-vote-materials`, and that is a good near-term fit for:

- SBOM files,
- detached signatures for SBOMs,
- additional checksum files,
- other generic metadata files that belong to the vote.

This does not yet solve every secondary ecosystem, but it is enough to make
ATR integration worthwhile before typed Maven, OCI, or PyPI support exists.

### 4. Incubator-sensitive behavior is aligned

ATR already enforces incubator-sensitive naming and archive-content checks for
podlings.

`buildish-release-tooling` already has incubator-aware concepts such as:

- incubator vote wording,
- incubator naming,
- incubator dist paths.

That is a good fit rather than a conflict.

### 5. `buildish-site-pipeline` is already prepared for ATR as a provider

This is not part of `buildish-release-tooling` itself, but it matters for the
overall ecosystem.

The existing `buildish-site-pipeline` design already anticipates:

- provider-neutral release snapshots,
- ATR as one possible provider,
- normalized candidate and released records,
- assets with `signatureUrl`, `sbomUrl`, and `provenanceUrl`.

The relevant sibling-project design work already exists in:

- `buildish-site-pipeline/docs/reference/provider-snapshot-schema.md`
- `buildish-site-pipeline/site/pages/architecture/provider-e2e-example.md`

So if ATR becomes a real candidate/current-release provider for Buildish
projects, the site-pipeline side is conceptually ready for that model.

## Where the Current Fit Is Weak

### 1. There is no ATR integration layer in `buildish-release-tooling`

Today the tool does not:

- authenticate to ATR,
- call the ATR API,
- create or update ATR candidate records,
- upload artifacts to ATR,
- fetch ATR check results,
- map local release state to ATR stages or phases.

That is the single biggest practical gap.

### 2. The current config model is not rich enough for ATR concepts

The current component config focuses on:

- ASF dist paths,
- Git/GitHub release flow,
- local vote instructions,
- secondary targets in a coarse way.

More precisely, the tool already knows that there is one authoritative source
artifact and that everything else is secondary. What it does not yet model is
the path-pattern-style source-versus-binary classification policy that ATR uses
to decide which checks apply to which archived files. That gap matters mostly
for archive-like secondary artifacts and any future richer artifact families,
not for simple checksum or signature sidecars.

ATR will require additional explicit identifiers and policy knobs, such as:

- ATR base URL,
- ATR committee key,
- ATR product-line key,
- candidate/current channel selection,
- source-artifact classification patterns,
- binary-artifact classification patterns,
- ATR strict-checking preference,
- ATR license-check mode and exclusions.

Without that, any ATR integration would be ad hoc.

### 3. The current `verify-rc` command is still not the whole ATR story

This is important because ATR does not remove the need for local human
verification under ASF release policy.

Today `verify-rc` already does the core local verification work:

- download and verify the signed RC vote manifest,
- verify source artifact authenticity and integrity end to end,
- verify staged secondary artifacts for the currently supported kinds,
- run configured host-direct reproducibility checks,
- retain curated evidence for later `inspect-repro` analysis.

What it still does not yet do is:

- enforce isolated rebuild execution or network policy for local rebuilds,
- consume external ATR verification evidence as a first-class input,
- act as a native ATR lifecycle client.

That means `buildish-release-tooling` now has the local verification half, but
it still needs an ATR-facing integration layer rather than trying to fold ATR
into the current verifier ad hoc.

### 4. Secondary artifacts are typed, but ATR can still grow beyond them

ATR’s long-term direction includes package managers and richer distribution
channels. `buildish-release-tooling` now has typed manifest and verifier
support for several important ecosystems, but ATR can still evolve broader
policy and hosted-state concepts around them.

The current typed support covers:

- Maven staging repositories,
- OCI images and manifest lists,
- PyPI distributions,
- npm packages,
- generic additional files.

Follow-up gaps still remain around:

- richer ecosystem-specific policy,
- centralized hosted evidence,
- ATR-native release-state modeling.

### 5. GitHub-shaped assumptions remain in the release-tooling model

ATR is explicitly broader than GitHub release APIs. It is trying to represent
ASF release lifecycle state directly.

`buildish-release-tooling` still assumes GitHub in several important places:

- draft GitHub Releases
- GitHub provenance
- GitHub-oriented workflow patterns
- GitHub credential handling

That does not prevent ATR integration, but it does make the current design less
neutral than it should be.

## What Is Blocking a Deeper Integration Today

### 1. ATR is still Alpha and not yet the canonical final-publication path

This is the main external blocker.

ATR’s own Alpha docs say:

- it is Alpha 2 software,
- implementation details are expected to change,
- releases still must be committed manually to `svn:dist/release`.

That means it would be premature to make ATR the only authoritative release
backend for `buildish-release-tooling`.

### 2. ASF policy still requires local human verification

ASF release policy requires binding voters to:

- download all signed source packages,
- validate signatures,
- compile as provided,
- test the result on their own hardware.

So even if ATR performs excellent server-side checks, it cannot replace the need
for a local verification path.

This is not an ATR flaw. It is a policy boundary.

The implication is:

- ATR checks are complementary evidence,
- `verify-rc` should remain the serious local verifier,
- ATR integration should add evidence and lifecycle state around it rather than
  replacing it.

### 3. ATR’s product-line and release model is richer than the current buildish model

ATR has first-class concepts for:

- committee
- product line
- stage
- phase
- vote policy
- distribution channels

`buildish-release-tooling` does not yet model most of that explicitly.

It has enough information to produce artifacts and manifests, but not enough to
act as a native ATR lifecycle client.

### 4. The current trust-root model is not yet reconciled with ATR’s key model

Today the RC vote manifest records trust-root data derived from the ASF release
base and an external `KEYS` URL.

ATR, by contrast, manages committee signing keys directly and regenerates the
committee `KEYS` file from that state.

These models are not contradictory, but the contract is not yet explicit.

The safer design is:

- let `buildish-release-tooling` keep recording the explicit KEYS URI and
  related trust-root metadata for public verification,
- let ATR remain the committee-side source of managed signing keys,
- cross-check the two rather than implicitly assuming they are always the same
  thing.

## Recommended Integration Model

### 1. Near-term: ATR as an optional candidate mirror and checks provider

This is the best fit with ATR Alpha as it exists today.

Recommended flow:

1. `buildish-release-tooling prepare-rc` resolves authoritative source state.
2. `buildish-release-tooling build-source-rc` creates the source archive, `.asc`,
   and checksum sidecars.
3. `buildish-release-tooling finalize-rc-vote-materials` stages the candidate
   bundle and writes the signed `rc-vote-manifest.json`.
4. A new optional ATR integration step uploads the voted artifact set and
   metadata to ATR as a candidate release revision.
5. ATR runs automated checks and exposes candidate state, artifacts, and check
   results through its UI and API.
6. `buildish-release-tooling verify-rc` remains the local voter-facing verifier.
7. Final release publication still flows through ASF policy-compliant final
   publication steps, including `svn:dist/release` until ATR replaces that path.

Important policy boundary:

- in this near-term model, ATR checks happen after `finalize-rc-vote-materials`
  has produced and staged the candidate bundle that ATR inspects,
- so ATR failures should not retroactively block `finalize-rc-vote-materials`
  itself,
- instead, ATR status should be surfaced in workflow summaries and manifest
  outputs, then used to decide whether later release-publication steps may
  proceed.

In that model:

- `buildish-release-tooling` stays authoritative for artifact production,
- ATR becomes authoritative for centralized candidate metadata and checks,
- neither system needs to pretend to own the other’s strongest responsibilities.

### 2. Mid-term: `buildish-release-tooling` becomes an ATR-aware client

Once the basic mirror/checks path exists, the next step is to make the tool
ATR-aware rather than merely ATR-compatible.

That would mean new capabilities such as:

- creating or updating an ATR candidate record,
- uploading artifacts and sidecars through the ATR API or official client,
- attaching the `rc-vote-manifest.json` as provenance,
- retrieving ATR check results and surfacing them in workflow summaries,
- optionally refusing to proceed when ATR strict checks fail,
- storing returned ATR URLs and identifiers in release manifests.

The clean design choice here is:

- prefer the official ATR Python client or official GitHub Actions from the
  Tooling initiative instead of writing a custom, fragile HTTP client in this
  repository.

### 3. Long-term: ATR as the provider of release-state metadata

If ATR matures into the stable ASF release-state platform it aims to be, then:

- `buildish-site-pipeline` can consume ATR provider snapshots directly,
- `buildish-release-tooling` can publish or sync normalized candidate/current
  state into ATR,
- project websites and download pages can become less dependent on repo-local
  custom metadata for release-state discovery.

That is the point where the three-way fit becomes especially strong:

- `buildish-release-tooling`: artifact production and repo-local orchestration
- ATR: centralized release-state platform
- `buildish-site-pipeline`: consumer/rendering layer for release metadata

## Recommended Missing Features in `buildish-release-tooling`

### 1. Add an optional `atr` config block

Suggested shape:

```yaml
atr:
  enabled: true
  base_url: https://release-test.apache.org
  committee: buildish
  product_line: site-pipeline
  source_artifact_paths:
    - "**/*-src.tar.gz"
    - "**/*-source.zip"
  binary_artifact_paths:
    - "**/*.jar"
    - "**/*.zip"
  strict_checking: true
  license_check_mode: both
```

This should stay optional. Non-ATR projects must not be forced into it.

### 2. Add a first-class ATR publishing command

A likely command family would be:

- `sync-atr-candidate`
- or `publish-atr-candidate`

Responsibilities:

- create or locate the ATR candidate revision,
- upload the source artifact set,
- upload vote-side metadata files such as the manifest and SBOMs,
- return ATR URLs and IDs,
- optionally poll for initial check completion.

### 3. Add ATR result consumption

After upload, the tool should be able to:

- fetch ATR check results,
- summarize failures and warnings,
- expose a concise ATR status snapshot and candidate URL in GitHub/job summaries
  and manifest outputs,
- write ATR identifiers and URLs into manifest outputs,
- decide whether a workflow should fail, continue, or require manual review.

This should be policy-driven, not hard-coded. In particular, strict ATR
failures should normally gate later final-publication steps rather than
`finalize-rc-vote-materials`, because ATR only evaluates the candidate after
that candidate bundle exists.

### 4. Add first-class SBOM registration

SBOMs are important enough in both ATR and the Tooling initiative that they
should stop being purely incidental generic files.

Suggested minimum:

- a typed `sbom` secondary artifact kind,
- required artifact linkage to its subject artifact,
- optional detached signature,
- optional provenance/attestation URL or locator,
- support for CycloneDX naming conventions.

### 5. Add source/binary classification and exclusions as explicit policy

ATR’s checks depend heavily on whether a file is classified as source or binary.
If `buildish-release-tooling` is going to sync artifacts into ATR cleanly, it
needs an explicit way to carry or derive that classification.

This is not about the main source artifact versus "all secondaries" in the
current buildish sense. It is about ATR-style classification patterns that can
say, for example:

- these tarballs and source zips are source artifacts,
- these jars or binary zips are binary artifacts,
- these path patterns should use specific license-check exclusions.

That policy would also help `verify-rc`.

### 6. Finish `verify-rc`

This still matters regardless of ATR, but the remaining work has narrowed.

The remaining `verify-rc` and `inspect-repro` work should:

- tighten rebuild isolation and execution policy where needed,
- improve deeper post-failure diagnostics,
- optionally fetch and report ATR-side checks as additional evidence,
- clearly distinguish local-required results from external-advisory results.

If a project enables strict ATR gating, that policy should generally block later
release-publication steps until the ATR failures are resolved, rather than
preventing candidate finalization before ATR has had anything to inspect.

## Things `buildish-release-tooling` Should Not Try To Do

### 1. It should not try to replace ATR’s release-state platform

`buildish-release-tooling` should not grow its own clone of:

- centralized release records,
- committee key registry,
- vote database,
- hosted candidate/current release pages,
- system-wide audit history.

That would just duplicate ATR badly.

### 2. It should not assume ATR eliminates local verification

Under ASF policy, it does not.

ATR can provide strong server-side evidence, but local verification remains a
real requirement and should stay a first-class feature of this tool.

### 3. It should not bind itself to unstable ATR internals

ATR’s public docs explicitly say the implementation is expected to diverge.

So the integration layer should prefer:

- official client libraries,
- official GitHub Actions,
- stable API contracts,

and avoid coding directly against implementation quirks of the current Alpha
deployment.

## Bottom Line

ATR and `buildish-release-tooling` are a good conceptual fit.

The fit is strongest when they are treated as different layers:

- `buildish-release-tooling` for repo-local build, signing, staging, and
  manifesting
- ATR for centralized release lifecycle state, keys, policy, checks, and API

What is already a good fit:

- signed source-release bundles
- checksum and signature sidecars
- incubator-aware release handling
- generic metadata and SBOM sidecars
- provenance-rich RC vote manifests
- eventual downstream consumption by `buildish-site-pipeline`

What is missing:

- an ATR config model
- an ATR publish/sync command
- ATR result consumption
- typed SBOM support
- a full `verify-rc` implementation

What is blocking deeper adoption today:

- ATR is still Alpha and not yet the final canonical publication path
- ATR’s model and implementation are still evolving
- ASF release policy still requires local human verification

So the recommended next step is pragmatic:

- make ATR integration optional and additive first,
- keep `buildish-release-tooling` authoritative for artifact production,
- use ATR as a candidate/checks platform,
- and only later consider ATR as a stronger source of truth for release-state
  publication once the platform and its API have stabilized.

## References

- ASF Tooling home: <https://tooling.apache.org/>
- Apache Trusted Releases overview: <https://tooling.apache.org/trusted-release.html>
- ATR platform services: <https://tooling.apache.org/platform.html>
- ATR data model: <https://tooling.apache.org/data-model.html>
- ATR Alpha: <https://release-test.apache.org/>
- ATR checks guide: <https://release-test.apache.org/docs/checks>
- ATR license checks guide: <https://release-test.apache.org/docs/license-checks>
- ATR developer/code overview: <https://release-test.apache.org/docs/overview-of-the-code>
- ASF release policy: <https://www.apache.org/legal/release-policy.html>
