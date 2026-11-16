---
title: Optional ASF Profile
description: "Explicit ASF policy, dist, trust-root, vote-material, and ATR integration."
weight: 60
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

# Optional ASF Profile

ASF support is an explicit foundation adapter. It adds ASF-named config, publication targets,
trust-root data, vote wording, and optional Apache Trusted Release (ATR) integration. It does not
change the provider-neutral candidate and release manifests.

Buildish itself does not select this profile. An Apache project must review the current ASF policy
and its own PMC or Incubator process before composing a release workflow; this page describes
tooling capabilities, not an independent interpretation of ASF policy.

The authoritative sources are the ASF [Release Policy](https://www.apache.org/legal/release-policy.html),
[Release Distribution Policy](https://infra.apache.org/release-distribution.html), and
[Incubator release-management guide](https://incubator.apache.org/guides/releasemanagement.html).

## Selecting the profile

```yaml
policy_profiles:
  asf:
    project_status: tlp
    dist_dev_base: https://dist.apache.org/repos/dist/dev/example
    dist_release_base: https://dist.apache.org/repos/dist/release/example
    keys_url: https://downloads.apache.org/example/KEYS

publication:
  authoritative:
    kind: asf-dist-svn
  convenience:
    - kind: github-release
      repository: apache/example
  secondary: []
```

Selecting `asf-dist-svn` requires `policy_profiles.asf` and a separately built source artifact. The
adapter validates production ASF dist URL prefixes; local fixture URLs require explicit test-target
mode.

`project_status` is either `tlp` or `incubating`. Incubator-specific disclaimer handling is enabled
only for `incubating`. Source archive names remain component configuration: the core and ASF
adapter do not force an `-incubating` filename suffix.

## ASF release composition

The ASF policy currently requires approval of an official release, a source package sufficient to
build and test the release, detached cryptographic signatures for supplied packages, and publication
through the canonical Apache distribution channel after approval. Candidate materials may be
staged under `dist/dev`; approved artifacts move to `dist/release` and become available through the
Apache download system.

The tooling provides bounded commands for the required composition, including source-archive
creation, signing, candidate staging, vote-package creation, verification, final dist publication,
GitHub convenience publication, pruning, and optional ATR operations. A component workflow decides
which jobs and approval boundaries invoke those commands.

The repository's generic GitHub workflows are not turnkey ASF release workflows. They use GitHub as
the authoritative publication and platform-generated source snapshots, so an ASF component must
provide its own thin composition.

## ASF vote materials

```yaml
vote_materials:
  profile: asf
  release_name: Apache Example
  verification_guide_url: https://example.apache.org/verify-release/
  instructions: Verify the signed source artifact and candidate manifest.
```

The ASF vote profile requires `policy_profiles.asf`. `create-vote-package` renders ASF-specific
opening and result templates and binds them to the exact candidate-manifest digest. It does not send
mail, count votes, classify binding voters, enforce a voting period, or decide the result.

Those governance decisions remain external. A future voting bot can remain compatible by retaining
the exact candidate tag and manifest digest and supplying them to promotion only after its own ASF
policy checks pass.

## Trust and credentials

The ASF profile records the project's `KEYS` URL and explicit dist endpoints. Signing keys,
passphrases, ASF credentials, PMC authorization, and trust in a particular signing key remain
deployment and project responsibilities. See [Source artifacts and signing](../source-artifacts-and-signing/)
and the [Threat model](../threat-model/).

ATR settings, when selected, are nested under `policy_profiles.asf.atr`; the names and fields remain
ASF-specific rather than leaking into the core release model.
