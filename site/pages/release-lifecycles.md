---
title: "Release Lifecycles"
description: "Direct publication and exact-candidate promotion are separate composable approaches."
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

# Release Lifecycles

Buildish Release Tooling keeps two approaches separate.

## Direct release

A direct release resolves one exact source commit and publishes the unsuffixed final tag and Release
end to end. It has no candidate and no vote. Components may still split the workflow into jobs and
place GitHub Environments at their own approval boundaries.

## Candidate and promotion

The candidate lifecycle publishes immutable candidates such as `v1.2.3-rc1`. Candidate numbering
defaults to one; projects can choose zero. Each candidate carries a durable manifest that binds its
source revision, artifacts, publication, and verification evidence.

After an external manual or automated gate accepts a candidate, promotion requires that exact tag
and the SHA-256 of its manifest. It never discovers a "latest RC". The final release may use the
ordinary unsuffixed `1.2.3` version and `v1.2.3` tag.

Voting is optional and external. Generic and ASF-specific vote packages can be generated over the
exact manifest, but the CLI does not count votes or decide an outcome.

See the [unreleased direct-release walkthrough](../development/direct-release/) and
[unreleased candidate-release walkthrough](../development/candidate-release/) for current
development details.
