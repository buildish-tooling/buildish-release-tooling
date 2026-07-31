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

The checked-in `release-config.yaml` currently selects the direct lifecycle, GitHub as the
authoritative publication, GitHub-generated source snapshots, and the exact `Required Checks` CI
gate. It publishes no separately built assets and selects no foundation policy profile.

The direct and candidate approaches are separate. A candidate exercise starts at RC1 by default and
may publish later RCs. Promotion must use the exact accepted candidate tag and
`candidate-manifest.json` SHA-256. Voting, when used, is external to the tooling.

Buildish currently treats GitHub as authoritative and does not require a separately built source
snapshot. Those are component-configurable choices, not universal tooling requirements.

## Self-bootstrap strategy

The workflow executes the tooling from its own repository checkout. For a dispatched run, GitHub
binds that checkout to the workflow run's exact commit; the wrapper recognizes the repository root
as the tooling project and invokes it with `uv --frozen`. It does not download an earlier package or
an unpinned copy of itself.

Resolution separately binds the release source to an exact commit. For the first release, dispatch
the workflow from the reviewed commit and select that same commit as `source_ref`. All later jobs
consume the recorded source identity and digest-bound state rather than resolving `main` again.

Do not dispatch a release until the selected commit is pushed, its `Required Checks` result is
successful, the workflow and config are reviewed, required repository settings are in place, and
the corresponding local harness scenario passes. The release workflows need no signing or
publication secrets for the current no-built-asset GitHub composition; write operations use the
job-scoped GitHub token.

See the development documentation for the [direct lifecycle](../docs/direct-release.md),
[candidate lifecycle](../docs/candidate-release.md), and
[workflow composition](../docs/release-workflows.md).
