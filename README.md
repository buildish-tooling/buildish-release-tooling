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

# Buildish Release Tooling

`buildish-release-tooling` is the shared release implementation component for Buildish projects.

It exists to move the growing release logic out of loosely coupled bash libraries and into a
versioned Python tool with:

- a stable CLI surface for Buildish release workflows
- structured models for release state and component policy
- reusable Git, SVN, GPG, and GitHub-check integrations
- unit and integration tests that run from a repo-local `build/` tree

The intended consumption model is:

- Buildish component repositories pin an exact immutable Git ref for this tool
- GitHub workflows check out that exact ref
- component-local wrappers run the tool via `uv run --project`

Examples:

```bash
uv run --project buildish-release-tooling buildish-release-tooling prepare-rc \
  --component-config buildish-mammoth-cache/buildish-release-tooling/release-config.yaml \
  1.2.3
```

```bash
uvx --from git+https://github.com/apache/buildish-release-tooling@v0.1.0 \
  buildish-release-tooling prepare-rc \
  --component-config ./buildish-release-tooling/release-config.yaml \
  1.2.3
```

`uvx` is a convenience hook for ad hoc use. The release workflows should prefer a checked-out,
exact pinned ref over pulling from an index.

## CLI commands

- `create-release-branch`
- `verify-source-ref-checks`
- `prepare-rc`
- `create-source-artifact`
- `build-source-rc`
- `release-version`
- `verify-rc`

## Development

```bash
make check
```
