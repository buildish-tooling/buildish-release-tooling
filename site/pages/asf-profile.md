---
title: "Optional ASF Profile"
description: "ASF-specific release infrastructure and vote material remain an explicit adapter."
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

ASF support is selected explicitly. It adds ASF-named configuration and operations for ASF dist,
`KEYS`, vote text, Incubator status, and optional Apache Trusted Release integration. Generic
projects do not inherit those requirements or names.

The core does not force an `-incubating` source filename suffix. A component chooses its own source
archive template. Incubator disclaimer behavior applies only when the ASF profile declares the
project as incubating.

The generic checked-in GitHub workflows are not turnkey ASF release workflows. Apache projects must
compose a separately built and signed source artifact, the applicable vote process, and canonical
ASF publication according to current ASF policy.

See the [unreleased ASF profile guide](../development/asf-profile/) for current development details
and links to authoritative ASF policy.
