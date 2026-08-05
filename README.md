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

# Buildish Release Tooling

`buildish-release-tooling` is a composable release CLI for Git-hosted projects. It currently ships
GitHub adapters and component-owned GitHub Actions workflows, while keeping platform-neutral release
identity, state, manifests, signing policy, and promotion evidence in the core model.

Two release lifecycles are supported:

- direct: resolve one exact source revision and publish the final release end to end;
- candidate: publish one or more retained candidates, let an external process decide whether a
  candidate may advance, and promote one exact candidate manifest to the final release.

Voting is optional and external to release publication. The CLI can create generic or ASF-specific
vote packages over an exact candidate manifest, but it does not count votes or decide an outcome.

The supported integration surface is:

- the `buildish-release-tooling` CLI;
- component-owned `release-config.yaml`;
- stable candidate, vote-package, and final release manifests;
- thin component workflows that call the CLI.

The Python module layout is internal. Release-critical consumers should pin an exact immutable Git
revision of this component and invoke the CLI from a checked-out copy.

## Status

Buildish has not published a Release Tooling release yet. The repository and its
`development/` documentation describe unreleased development work, and interfaces may change before
the first release. A document described as a stable contract has a defined compatibility policy; it
does not mean that a Buildish release has already been published.

## Getting started

Release Tooling requires Python 3.11 or newer. Install a published release by exact version:

```bash
uv tool install buildish-release-tooling==0.1.0
buildish-release-tooling --help
buildish-release-harness --help
```

The base installation includes the provider-neutral lifecycle and PyPI publication-state client.
Install the adapter's optional cryptographic verifier when using
`verify-pypi-attestations`:

```bash
uv tool install 'buildish-release-tooling[pypi]==0.1.0'
```

That extra is not required for components that do not select a PyPI secondary target.

Before the first production package is available, or when reviewing unreleased development, use
Git and [`uv`](https://docs.astral.sh/uv/) to inspect and check out an exact commit instead of
running the moving `main` branch:

```bash
git clone https://github.com/buildish-tooling/buildish-release-tooling.git
cd buildish-release-tooling
git checkout --detach <reviewed-commit-sha>
uv run --frozen buildish-release-tooling --help
```

The final command installs the locked environment and exercises the non-mutating CLI help path.
Component release commands validate their `release-config.yaml` when they run; use the local harness
and the component's own checks before allowing a command to access credentials or publication
services.

## Workflows

The repository contains four live GitHub release workflows:

- `.github/workflows/release-candidate.yml`;
- `.github/workflows/release-promote.yml`;
- `.github/workflows/release-testpypi.yml`;
- `.github/workflows/release-verify-candidate.yml`.

Buildish Release Tooling itself uses the candidate and promotion workflows for production releases.
Promotion requires the exact version, candidate tag, and candidate-manifest SHA-256 selected by the
external approval process, and publishes the candidate's exact wheel and sdist to PyPI. The
TestPyPI workflow is a manually dispatched direct-lifecycle package-index rehearsal: it resolves and
retains `DirectReleaseState`, safely recovers matching partial or complete uploads, and creates no
GitHub release. A generic direct GitHub release workflow remains covered as a local harness fixture.

## Development

```bash
make check
```

The local harness runs the checked-in workflows through `act` while replacing GitHub mutations with
inspectable workspace-local Git and GitHub Release state.

## Documentation

- [Component website](https://buildish.org/components/release-tooling/)
- [Buildish Release Tooling documentation](https://buildish.org/components/release-tooling/)
- [Direct release walkthrough](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/direct-release.md)
- [Candidate and promotion walkthrough](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/candidate-release.md)
- [Workflow composition](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/release-workflows.md)
- [How Release Tooling releases itself](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/self-release.md)
- [Source artifacts and OpenPGP signing](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/source-artifacts-and-signing.md)
- [Optional ASF profile](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/asf-profile.md)
- [Threat model](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/docs/threat-model.md)
- [Unreleased generated reference](https://buildish.org/components/release-tooling/development/reference/)

## Community

- [Contributing](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/CONTRIBUTING.md)
- [Security policy](https://github.com/buildish-tooling/buildish-release-tooling/security/policy)
- [Code of Conduct](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/CODE_OF_CONDUCT.md)
- [License](https://github.com/buildish-tooling/buildish-release-tooling/blob/main/LICENSE)
- [Issue tracker](https://github.com/buildish-tooling/buildish-release-tooling/issues)
