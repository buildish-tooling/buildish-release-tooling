---
title: "ASF Project Fit Assessment"
description: "Portfolio-level assessment of how broadly buildish-release-tooling could fit active ASF projects."
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

# ASF Project Fit Assessment

## Scope

This document answers a portfolio-level question:

- could `buildish-release-tooling`, in principle, be used by active Apache projects beyond Buildish?

This is not a project-by-project release audit. It is a fit assessment based on:

- the current active ASF project inventory
- the current architecture and assumptions in `buildish-release-tooling`
- representative active project documentation for source releases and secondary artifacts

Assessment date:

- 2026-04-26

## Executive Summary

Yes, `buildish-release-tooling` could work in principle for a substantial subset of active ASF projects, but not for the whole ASF portfolio as-is.

The strongest reusable core is:

- Git-based source selection
- RC tagging
- signed source release staging to ASF dist
- RC vote-manifest generation
- final promotion from `dist/dev` to `dist/release`

The biggest blockers to broader ASF adoption are:

- strict `x.y.z` semantic-version assumptions
- implicit preference for GitHub-shaped flows
- lack of first-class support for Maven/Nexus, PyPI, OCI, npm, and other secondary artifact ecosystems
- lack of a clear portability story for non-GitHub Git projects and for still-SVN-centric source projects

My conclusion is:

- the current design is already close to usable for a meaningful set of Java and source-centric ASF projects
- it needs medium to large extension work before it can credibly claim to cover "any ASF project"

## Method

I used official ASF sources only.

- `https://projects.apache.org/json/foundation/projects.json`
- `https://projects.apache.org/json/foundation/podlings.json`
- `https://projects.apache.org/projects.html`

Important caveat from the ASF project directory:

- the directory explicitly says the displayed project information relies on DOAP files
- DOAP files are not mandatory
- the DOAP data may be incomplete or out of date

That matters here. The numbers below are useful signals, not exact onboarding truth.

For active-project counts, I treated:

- non-Attic TLPs from `projects.json` as active top-level projects
- entries in `podlings.json` as active incubating projects
- duplicate IDs across those feeds as one project

On 2026-04-26 that yielded:

- 301 active non-Attic TLPs
- 28 active podlings
- 328 combined active projects after de-duplication

## Current Tooling Assumptions

Today the release-tooling codebase assumes, or strongly prefers, all of the following:

- one checked-out source tree is the authority for the release
- the release source is addressable through Git
- the project version is a strict semantic version like `1.2.3`
- there is one primary source artifact that is always signed and checksummed
- ASF dist `dev` and `release` paths are part of the release flow
- GitHub remains the main release-mirror or release-metadata endpoint
- secondary artifacts can be modeled with a small number of built-in target families

Those assumptions are a good fit for Buildish. They are not yet a good fit for the full ASF project portfolio.

## Portfolio Findings

### 1. The source-release layer is broadly reusable

At the ASF policy level, the most reusable part of the current design is the signed source release flow.

That is promising because many ASF projects, regardless of language, still center their official vote on:

- a staged source artifact
- detached signatures
- checksums
- a KEYS file

This makes the following buildish-release-tooling features broadly portable:

- RC source selection from Git
- signed source artifact staging
- RC manifesting
- RC verification planning
- final promotion into `dist/release`

### 2. The official ASF project inventory already shows a large Git-based subset

Across the 328 active projects:

- 246 advertise at least one repository URL in the official inventory
- 179 advertise an explicit Git-shaped repository
- 153 advertise GitHub or GitBox repositories
- 65 advertise SVN only
- 82 have no repository field in the current official inventory

Implications:

- a large subset already looks compatible with a Git-centered release flow
- but the tooling cannot rely on the ASF inventory alone for discovery or onboarding
- explicit local project config will remain necessary

### 3. The current strict semantic-version rule is a real blocker

Among the 178 active TLPs that currently expose release metadata in the official ASF inventory:

- 115 have a latest release revision that matches strict `x.y.z`
- 63 do not

Examples of active projects whose published latest release revisions do not fit strict `x.y.z`:

- Apache Airavata: `0.11`
- Apache ManifoldCF: `2.30`
- Apache NetBeans: `29`
- Apache Causeway: `4.0.0-M1`
- Apache Maven: `4.0.0-rc-5`
- Apache Polaris: `1.3.0-incubating`

That means the current version parser is not just a niche limitation. It would block or complicate onboarding for a visible part of the ASF portfolio.

Important nuance:

- the `-incubating` suffix is not really a milestone or prerelease concept
- it is an incubator branding and policy marker

So for tooling purposes, I would treat:

- `-alphaX`, `-betaX`, `-M1`, `-rcN` as version-shape qualifiers
- `-incubating` as an orthogonal incubator marker that should be modeled separately where possible

### 3a. Alpha, beta, milestone, and RC lines can be official ASF releases

ASF release policy is clear on two points:

- anything published beyond the development community is a release
- official Apache releases must be approved by the PMC and then published in the canonical ASF download channel

The same policy also distinguishes:

- release candidates as test packages that are not yet official releases
- beta releases as approved releases intended for testers and developers
- alpha releases as approved milestone-style releases intended for bleeding-edge users

So the answer is:

- internal RCs under vote are not official releases
- alpha, beta, milestone, and even `rc`-named versions can still be official ASF releases if the PMC votes them through and publishes them as releases

Representative active examples:

- Apache Maven publishes `4.0.0-rc-5` release notes stating that "Apache Maven 4.0.0-rc-5 is available for download"
- Apache Causeway’s official releases page lists `4.0.0-M1` as a release, while separately stating that nightly and weekly builds are not official ASF releases
- Apache NetBeans 29 explicitly links to the PMC vote and PMC vote result on its official download page

Implication for buildish-release-tooling:

- the tool should not reject `-rc`, `-M1`, `-alpha`, or `-beta` versions on the assumption that they are never real releases
- instead, project config should declare which version patterns are valid official release lines for that project
- the verify and publication flow should continue to treat vote-stage RCs in `dist/dev` as non-released candidates, regardless of the version text

### 4. Secondary artifact diversity is the main adoption bottleneck

Representative active ASF projects show several very different secondary-artifact patterns:

- Apache Airflow publishes reference Docker images in DockerHub for each release and documents installation from PyPI
- Apache Superset documents installation from the `apache_superset` package on PyPI and also has Docker Compose and Docker build paths
- Apache Arrow publishes a signed source release, official binary wheels on PyPI, and additional package repositories for Linux distributions
- Apache Camel’s download page shows multiple coordinated subprojects and multiple signed source archives plus SBOMs

This means a generic "secondary artifact" field is not enough by itself.

To work across ASF projects, the tooling needs first-class verifier and registration support for at least:

- generic file artifacts
- Maven or Nexus staged repositories
- PyPI distributions
- OCI container images
- npm packages
- SBOM sidecars and related metadata

Two of those families are comparatively tractable:

- `generic-file`
- `sbom`

My assessment:

- `generic-file` is a relatively simple target family
- an `sbom` target can initially be treated almost the same way as a generic file, assuming the SBOM is already generated by the project build

That means phase 1 support for SBOMs does not need deep semantic validation. It can focus on:

- identity
- digest verification
- detached signature verification when present
- optional reproducibility checks if the SBOM is generated deterministically

### 5. Verify-RC should stay scoped to explicitly in-vote artifacts

Apache Arrow is a good example.

Its install page presents:

- a signed source release
- official binary wheels on PyPI
- package repositories and package-manager paths for multiple operating systems

That creates an important scoping question:

- which artifacts are explicitly part of the RC vote?
- which artifacts are convenience artifacts produced later, after the vote?

My recommendation is narrower than the previous draft:

- `verify-rc` should concern itself only with artifacts explicitly listed in the `rc-vote-manifest`
- convenience artifacts created after a successful vote are out of scope for `verify-rc`

So the policy burden is not "model every eventual convenience artifact".

It is:

- make the RC-preparation flow explicitly register the artifacts that belong to the vote
- keep later convenience publication outside the `verify-rc` scope unless a project explicitly chooses to include those artifacts in the RC vote

### 6. Podlings are architecturally promising, but metadata-poor

The current tool already has useful incubator-aware concepts:

- incubator vote wording
- incubator dist paths
- incubating source artifact naming support

So podlings are not a bad target in principle.

However, the official `podlings.json` feed is sparse compared with the TLP inventory. On 2026-04-26 it did not provide repository URLs at all.

Implication:

- podlings are a good conceptual fit for the source-release layer
- but they will need explicit hand-authored config, not metadata-driven onboarding

### 7. Non-GitHub-first and SVN-only projects are different cases

These should not be treated as one bucket.

#### Non-GitHub-first but still Git-based

Projects that primarily use:

- GitBox
- self-hosted Git mirrors
- non-GitHub website or release pages

can still use buildish-release-tooling in principle as a CLI tool.

What they need is:

- explicit repository configuration
- optional GitHub-specific commands or disabled GitHub mirroring
- no assumption that GitHub Releases are part of the process

This is mostly a host-integration problem, not a source-control-model problem.

#### Still-SVN-centric source projects

This is a harder mismatch.

Among active non-Attic TLPs in the official inventory:

- 65 advertise SVN-only repositories

Those are not all dead projects. Based on the current ASF inventory metadata:

- 13 SVN-only active TLPs show releases in 2023-2026
- 6 SVN-only active TLPs show releases in 2025 or 2026

Representative currently active SVN-only projects from the official feed include:

- Apache PDFBox
- Apache HTTP Server
- Apache SpamAssassin
- Apache Torque
- Apache Portable Runtime
- Apache POI
- Apache Subversion
- Apache XMLBeans
- Apache Velocity

So SVN-only source projects are a minority, but not a negligible or dead minority.

Implication:

- non-GitHub Git projects are still plausible CLI-tool users
- SVN-only source projects are a weaker fit because current release-tooling orchestration is deeply Git-based
- for SVN-only projects, only parts of the stack look directly reusable today, such as dist publication, verification planning, and maybe manifesting

## Suitability Tiers

### Tier A: Near-Direct Fit

These are projects that look close to the current release-tooling model:

- one main source repository
- strict `x.y.z` style release versions
- one main signed source artifact
- no mandatory ecosystem-specific verification beyond generic files

Representative examples from the active inventory:

- Apache Ant
- Apache Accumulo
- Apache Solr
- Apache Tomcat
- many Apache Commons components

What these projects would still need:

- explicit `release-config.yaml`
- explicit KEYS URL configuration
- possibly generic-file handling for binary convenience archives or SBOM files

### Tier B: Good Fit After Moderate Extensions

These are projects where the source-release layer looks reusable, but secondary artifact handling or release-shape flexibility is required.

Representative examples:

- Apache Camel
- Apache Kafka
- Apache Maven
- Apache NiFi
- Apache Pulsar
- Apache Flink

Typical gaps:

- Maven or Nexus repository verification
- multiple source artifacts or coordinated subprojects
- release lines that include RC, beta, or milestone notation
- GitBox and non-GitHub-first release workflows

### Tier C: Good Fit After Major Secondary-Artifact Work

These are projects whose source release is still compatible with ASF process, but whose real release surface extends well beyond one source archive.

Representative examples:

- Apache Airflow
- Apache Superset
- Apache Arrow
- Apache Beam

Typical gaps:

- PyPI verification
- OCI image verification
- multi-platform artifact verification, which in practice mainly means OCI manifest lists and per-platform image digests
- project-specific reproducibility policies
- explicit declaration of which artifacts belong to the RC vote

### Tier D: Weak Fit for the Current Architecture

These are not "bad ASF projects" for the tool. They are simply poor fits for the current assumptions.

Representative cases:

- projects whose public versioning is not strict `x.y.z`
- projects with sparse or ambiguous repository metadata
- projects with multi-repository release trains
- projects whose official public release surface is not easily reduced to one checked-out source tree plus a small set of generic secondaries

Examples of version-shape friction from the active inventory:

- Apache NetBeans: `29`
- Apache Airavata: `0.11`
- Apache ManifoldCF: `2.30`
- Apache Causeway: `4.0.0-M1`

NetBeans is worth calling out separately:

- its official public download page uses `29` in the artifact names, for example `netbeans-29-source.zip`
- that same page links to the PMC vote and vote result

So, for tooling purposes, NetBeans should be treated as an integer-style official release line, not assumed to secretly mean `29.0.0`.

These projects are not impossible targets. They just require architectural changes first.

## What the Current Tool Could Probably Cover Today

If I ignore secondary artifact verification and focus on the current source-release-centered flow, the active ASF inventory already shows a meaningful lower-bound subset.

Using only projects that currently advertise both:

- a GitHub or GitBox repository, and
- a latest release revision that matches strict `x.y.z`

the official inventory still yields at least 72 active TLPs that look close to the current model.

That number is a lower bound because:

- many active projects have incomplete DOAP metadata
- some projects have no release metadata in the inventory
- some projects almost certainly use Git even though the feed does not say so

So the answer is not "only Buildish". The answer is "Buildish plus a meaningful source-centric subset of ASF projects, even before broadening the design".

## What Needs to Change for Broad ASF Applicability

If the goal is "could work, in principle, for most active ASF projects", I would prioritize these changes:

### 1. Make version parsing configurable

The current strict `x.y.z` rule should become a project-level version policy.

At minimum the tool should support:

- strict `x.y.z`
- `x.y`
- integer-only versions
- qualifier-bearing versions such as `-rc`, `-M1`, `-alpha`, or `-beta`
- an optional incubator marker such as `-incubating`, treated as a separate policy concern rather than as an ordinary prerelease qualifier

### 2. Treat repository layout as explicit config, not discovery

The tool should not assume that:

- GitHub is the only important repository host
- the ASF project directory is complete enough for onboarding

Projects should be able to declare explicitly:

- the authoritative source repository
- optional mirror repositories
- whether GitHub release mirroring is used at all

### 3. Add first-class secondary-artifact families

The verifier and RC vote-manifest model should grow first-class support for:

- generic file artifacts
- Maven or Nexus repositories
- PyPI distributions
- OCI images
- npm packages
- SBOM artifacts

### 4. Add policy for official versus convenience artifacts

Projects like Arrow and Airflow need a policy model that can say:

- this artifact is vote-critical
- this artifact is published for convenience only
- this artifact is reproducibility-checked but not a release blocker

### 5. Do not try to become a multi-repository orchestrator

Some ASF release families are not one repo, one tarball, one version line.

I do not think this project should try to become the full multi-repository orchestrator for those cases.

A better boundary is:

- make one invocation work well for one authoritative source repository and its in-scope voted artifacts
- let larger projects compose multiple invocations in their own higher-level release workflow if needed

That still leaves room for:

- multiple typed secondary-artifact groups
- multiple in-scope artifacts from one repo

But it avoids turning buildish-release-tooling into a general release-train coordinator.

### 6. Keep a source-only mode as a first-class path

For many ASF projects, the first win is not "verify every ecosystem artifact".

It is:

- reliably stage and verify the signed source release
- optionally mirror convenience artifacts
- add typed secondary verification later

That source-only path should remain first-class.

## Bottom Line

`buildish-release-tooling` is already a plausible foundation for a subset of ASF projects, especially source-centric Git-based projects with straightforward `x.y.z` release lines.

It is not yet a general ASF release framework.

The biggest gaps are not in the ASF source-release process itself. They are in:

- version-shape flexibility
- repository-host flexibility
- secondary-artifact verification
- multi-component release modeling

If those areas are addressed, the tool could credibly expand beyond Buildish and become useful for a broad slice of active ASF projects.

## References

- ASF project directory: <https://projects.apache.org/projects.html>
- ASF TLP inventory feed: <https://projects.apache.org/json/foundation/projects.json>
- ASF podling inventory feed: <https://projects.apache.org/json/foundation/podlings.json>
- ASF release policy: <https://www.apache.org/legal/release-policy.html>
- ASF release creation process: <https://infra.apache.org/release-publishing.html>
- Apache Airflow Docker image docs: <https://airflow.apache.org/docs/docker-stack/>
- Apache Airflow PyPI installation docs: <https://airflow.apache.org/docs/apache-airflow/stable/installation/installing-from-pypi.html>
- Apache Superset PyPI installation docs: <https://superset.apache.org/admin-docs/installation/pypi/>
- Apache Arrow install page: <https://arrow.apache.org/install/>
- Apache Camel downloads: <https://camel.apache.org/download/>
- Apache Causeway releases page: <https://causeway.apache.org/docs/latest/landing-page/releases.html>
- Apache Causeway release verification page: <https://causeway.apache.org/comguide/latest/verifying-releases.html>
- Apache Maven 4.0.0-rc-5 release notes: <https://maven.apache.org/docs/4.0.0-rc-5/release-notes.html>
- Apache NetBeans 29 download page: <https://netbeans.apache.org/front/main/download/nb29/>
- Apache HTTP Server release guidelines: <https://httpd.apache.org/dev/release.html>
