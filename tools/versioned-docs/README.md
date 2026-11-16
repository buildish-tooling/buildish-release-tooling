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

# Versioned documentation worktrees

These developer scripts use Bash, Python 3.11+ (standard library only), and Git.
Creating a new branch requires Git with `worktree add --orphan` support. They are
repository maintenance commands, not part of the installed Release Tooling CLI.
Run them from any directory; defaults are relative to this source checkout.

The `versioned-docs` branch contains only released documentation and its inventory:

```text
provider-snapshot.json
0.1.3/
  _index.md
  ...
```

The default worktree location is `docs/releases/`. Each version is copied from
`docs/` at its exact stable Git tag, without rewriting links or documentation.
The source checkout remains on its original branch. The inventory uses Site
Pipeline's v1 provider snapshot format and artifact key `release-tooling`.
Provider type `git-tags` identifies the actual source; this is not a live GitHub
API response. It records the version, tag, resolved commit and GitHub release URL.
It deliberately does not claim publication timestamps or verified release assets.

## First checkout

For an already published branch:

```sh
tools/versioned-docs/checkout.sh
```

If the branch exists locally, this attaches it without fetching; otherwise it
fetches just that branch from
`https://github.com/buildish-tooling/buildish-release-tooling.git` and creates a
local branch. No tracking remote or Git configuration is installed. An existing
checkout is checked for the expected repository/branch and a clean worktree.

To create the branch for the very first time instead:

```sh
tools/versioned-docs/checkout.sh --create
```

This creates an empty orphan branch with no automatic commit, fetch or push.
Import the first version next. Do not use `--create` to recover an existing branch.
If the branch is already checked out elsewhere, Git refuses the second checkout.

## Updating from the published branch

```sh
tools/versioned-docs/update.sh
```

Fetches the branch from the same default HTTPS URL and fast-forwards the docs
worktree. Dirty worktrees and divergent histories are rejected. It never resets,
rebases, merges divergent history, commits, or pushes. A local branch ahead of the
remote retains its commits. An unpublished orphan branch must first be imported
and committed before it can merge a published branch.

Both checkout and update accept `--remote URL_OR_NAME`, `--branch NAME`,
`--source PATH`, and `--worktree PATH`. Import accepts the latter three only.
The worktree must belong to the source repository. Default `--worktree` is always
`<source>/docs/releases`, including when `--source` is supplied.

## Importing released docs

Review which releases actually completed publication, then import them from local
tags. For the first successful release:

```sh
tools/versioned-docs/import.sh --version 0.1.3
```

For ordinary incremental maintenance:

```sh
tools/versioned-docs/import.sh
```

The default scans all local stable tags `vX.Y.Z`, excluding candidate/prerelease
tags. There is no project-specific cutoff. `--minimum-version X.Y.Z` optionally
limits discovery. Repeat `--version X.Y.Z` to select exact versions instead;
explicit versions override that optional floor.

**A final-looking Git tag does not prove a successful GitHub/PyPI publication.**
After a failed promotion, use explicit versions until the release is complete.
No GitHub API calls are made and no tags are fetched by import. Fetch missing tags
separately using your normal Git process. Consider verified publication inventory
as a future enhancement rather than silently treating this inventory as proof.

Incremental import adds missing versions and retains previous inventory entries,
including manually curated metadata. Existing docs are left byte-for-byte
unchanged. Both import modes reject a moved tag for an existing selected version.
Repeating a no-op incremental import does not change timestamps.

For a retracted release, edit its existing record in `provider-snapshot.json` to
include `"publicationState": "withdrawn"`, then review and commit that change.
Keep the record rather than deleting it: deletion would let import rediscover the
tag. Both incremental import and full rebuild preserve the entire existing record,
including publication state, support status, URLs, and other curated fields.
Records are retained even when their tags are absent locally or not selected.
The Site Pipeline consumer must honor publication state when publishing the site;
these scripts retain the tagged docs and do not decide website visibility.
The scripts reject dirty worktrees; review and commit each batch before another
import or update. They also reject foreign snapshot records, unowned destination
directories, symbolic links in imported docs, and tags without `docs/_index.md`.
All selected docs exports are prepared successfully before existing files change.
Filesystem failures during final writes can still leave partial changes: inspect
`git diff` and recover with ordinary Git commands after preserving wanted work.

## Full rebuild

```sh
tools/versioned-docs/import.sh --full-rebuild
```

On a clean docs worktree, reconstructs the selected version directories from their
local tags, adding any newly discovered versions to the inventory. Existing
inventory records and curated metadata are preserved. Unselected versions and
other branch files, such as a root README, are preserved too. This intentionally
replaces manual edits committed inside selected managed docs directories, including
ignored files there. Use explicit `--version` options to rebuild a controlled
subset. The original snapshot is validated before it is trusted to identify
managed directories. Full rebuild does not prune release history.

Review all generated changes in the docs worktree. Commit and publish separately
when authorized; these scripts never stage, commit or push. The source checkout's
`.gitignore` excludes `docs/releases/`, so inspect changes with
`git -C docs/releases status` and `git -C docs/releases diff`.

## Website integration

The website build checks out the source branch for development docs and the
`versioned-docs` branch under `docs/releases/`. The catalog must declare the
artifact key `release-tooling`, release selection, `lifecycle.latestStable`, and
the component-owned snapshot path. Configurable component snapshot paths and
optional local checkout behavior require the pending Site Pipeline change;
merely generating this file does not enable website publication today.

The snapshot contains the whole component's imported release history. It is not
one file per release. The website should consume docs and inventory from the same
branch commit. CI publication should require its checkout, while local development
without it must remain usable under the new pipeline contract.

## Checks

```sh
python3 -m pytest tests/test_versioned_docs_scripts.py -q
make check
```

The regression tests exercise local temporary Git repositories and require no
network, configured Git identity, signing key, or actual `versioned-docs` branch.
