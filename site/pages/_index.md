---
title: "Release Tooling"
description: "Composable direct and candidate release automation for Buildish components and other Git-hosted projects."
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

`buildish-release-tooling` is a composable release CLI. It supports a direct, one-dispatch final
release and an RC-based lifecycle that promotes one exact candidate after an external approval or
voting process.

GitHub is the first implemented hosting platform. Core release identity, state, manifests, artifact
policy, signing, and promotion evidence are provider-neutral. ASF behavior is available only through
an explicit optional foundation profile.

- [Release lifecycles](release-lifecycles/)
- [Optional ASF profile](asf-profile/)
- [Unreleased development documentation](development/)

Each component owns a thin workflow and its release config. The CLI provides bounded, rerunnable
operations and stable machine-readable manifests; the component chooses job boundaries, GitHub
Environments, secret policy, artifacts, signing, and any external gate.

Use `make check` as the standard local and CI gate.
