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

This component supports two release exercises while Buildish establishes its initial release
practice:

- direct publication with `.github/workflows/release-direct.yml`;
- candidate publication and exact promotion with `.github/workflows/release-candidate.yml`,
  `.github/workflows/release-verify-candidate.yml`, and `.github/workflows/release-promote.yml`.

The component's `release-config.yaml` selects the active lifecycle and publication policy. Do not
dispatch a release until that config has been reviewed for the intended exercise, the workflow uses
an exact approved tooling revision, required repository settings and secrets are in place, and a
dry-run has completed.

The direct and candidate approaches are separate. A candidate exercise starts at RC1 by default and
may publish later RCs. Promotion must use the exact accepted candidate tag and
`candidate-manifest.json` SHA-256. Voting, when used, is external to the tooling.

Buildish currently treats GitHub as authoritative and does not require a separately built source
snapshot. Those are component-configurable choices, not universal tooling requirements.

See the development documentation for the [direct lifecycle](../docs/direct-release.md),
[candidate lifecycle](../docs/candidate-release.md), and
[workflow composition](../docs/release-workflows.md).
