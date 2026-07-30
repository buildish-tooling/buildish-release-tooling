---
title: "Release Tooling"
description: "Shared release implementation component with an optional ASF profile."
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

`buildish-release-tooling` is the shared release implementation component used by Buildish
repositories.

The Buildish release process is TBD. ASF-specific pages describe an optional
tooling profile and do not define the current Buildish release policy.

The stable contract is the CLI plus `release-config.yaml`. The Python package layout is internal,
but the docs tree includes maintainer guides for the current structure:

- [CLI contract and compatibility notes](development/)
- [Production package layout](development/codebase-layout/)
- [Test suite layout and layering](development/test-suite/)

Use `make check` as the standard local and CI gate.

Planning and assessment documents:

- [ASF Profile GitHub Release policy](github-release-policy/)
- [Verify RC implementation plan](verify-rc-implementation-plan/)
- [ATR integration assessment](atr-integration-assessment/)
- [ASF project fit assessment](asf-project-fit-assessment/)
