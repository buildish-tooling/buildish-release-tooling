---
title: Docs and Reference
description: "This `docs/` tree now holds the material that belongs under the component's versioned docs root: stable reference pages today, and release-tied docs later."
weight: 90
---

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

# CLI API Contract

This page defines the supported external contract for `buildish-release-tooling`.

## Internal implementation guides

The pages below describe the current source tree for maintainers. They are intentionally
descriptive, not contractual.

- [Codebase Layout](codebase-layout.md)
- [Test Suite Layout](test-suite.md)

The public contract is intentionally narrow:

- the `buildish-release-tooling` CLI command surface
- the required `release-config.yaml` schema
- the manifest, summary, and exit-code behavior that workflows may rely on

The Python module layout is not a public API. Buildish component workflows should consume this
component through the CLI only, pinned to an exact immutable Git ref.

## Versioning and compatibility

`buildish-release-tooling` is intended to follow semantic versioning for its external contract.

- major releases may change command names, arguments, manifest keys, or config schema in breaking
  ways
- minor releases may add commands, flags, manifest keys, or config fields in backward-compatible
  ways
- patch releases should keep the documented contract stable and only fix behavior

Release-critical workflows should pin:

- an exact immutable Git tag or commit of `buildish-release-tooling`
- not a moving branch
- not a package index lookup as the primary release path

## Invocation contract

The stable invocation model is:

```bash
uv run --project /path/to/buildish-release-tooling --frozen \
  buildish-release-tooling <command> \
  --component-config /path/to/release-config.yaml \
  [command arguments...]
```

The current working directory must be the target component repository, or inside its Git worktree.

Commands that inspect release branches or tags assume the workflow has already fetched:

- remote heads into `refs/remotes/origin/*`
- tags for the repository

Example:

```bash
git fetch --force --prune --tags origin '+refs/heads/*:refs/remotes/origin/*'
```

## Detached materialization commit model

Some components need release-only generated Git content that must not live in normal branch history,
for example a git-ignored `dist/` payload used by a GitHub Action.

For those components, the supported model is:

- resolve the source commit from the release branch as usual
- build the authoritative ASF source release from that source commit
- create a detached materialization commit from that source commit in isolated Git state
- if later workflow jobs need to see that detached commit, temporarily anchor it on a remote ref
- keep that detached commit out of `release/<line>` history
- place the RC tag on that detached materialization commit
- place the final exact tag on that same detached materialization commit after release approval

This is a component-policy exception, not the default behavior. Components that do not need
release-only generated Git content should keep both RC and final tags on the plain source commit.

## Stable inputs

### Required flag

All commands require:

- `--component-config <path>`

That file is the component policy contract between a Buildish component and this tool.

### Positional arguments

The stable interface uses explicit positional arguments such as:

- `version`
- `source_sha`
- `release_line`
- `source_ref`
- `assets...`

Environment fallbacks for positional arguments exist in a few places for workflow compatibility,
but they are not part of the long-term stable contract and should not be the preferred integration
path.

### Runtime environment integration

Environment variables are not the preferred public API surface for this tool. The preferred
integration surface is:

- explicit CLI arguments
- checked-out Git state
- `release-config.yaml`

Only a small set of runtime environment hooks should be treated as stable integration points:

- `MANIFEST_PATH`: override where the command writes its JSON manifest
- `GITHUB_OUTPUT`: optional path where selected commands append stable GitHub step outputs
- `GITHUB_STEP_SUMMARY`: required path where Markdown summary output is appended

The tool also interoperates with environment-based credentials and GitHub runner metadata when it
talks to external systems, but those should be treated as operational wiring rather than semver
stable CLI API:

- `GH_TOKEN` or `GITHUB_TOKEN` for GitHub CLI authentication and temporary detached-ref pushes
- `BUILDISH_SVN_DEV_USERNAME` and `BUILDISH_SVN_DEV_PASSWORD` for ASF SVN access
- `BUILDISH_GPG_PRIVATE_KEY` for detached signing
- `DOCKERHUB_USER` and `DOCKERHUB_TOKEN` for Docker Hub alias publication

Those variables are common in GitHub Actions, but they expand the process environment and therefore
should stay minimal. They are documented here because the current implementation uses them, not
because environment-variable integration is the preferred design.

GitHub API operations derive the repository slug from the checked-out worktree's `origin` remote
URL rather than from a separate environment-variable hint.

The following environment-variable hooks are implementation details and should not be relied on as
public contract. New functionality should prefer explicit CLI arguments, checked-out repository
state, or `release-config.yaml` over additional environment variables.

## `release-config.yaml` contract

The config file is a YAML object. The currently required fields are:

```yaml
component_id: buildish-example
source_artifact_prefix: apache-buildish-example
asf_dist_dev_base: https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example
asf_dist_release_base: https://dist.apache.org/repos/dist/release/incubator/buildish/buildish-example
moving_tags_enabled: true
latest_tag_enabled: false
secondary_targets:
  - github-action
final_tag_mode: rc-source-commit
vote_release_name: Apache Buildish Example
incubator_vote_enabled: false
release_summary_include_final_tag_mode: false
release_verification_guide_url: https://buildish.apache.org/buildish-example/release-verification/
verify_rc_instructions: |
  Verify the RC on trusted hardware.
prepare_rc_runs_tests: false
release_branch_ci_required: true
atr:
  enabled: true
  base_url: https://release-test.apache.org
  committee: buildish
  product_line: buildish-example
  source_artifact_paths:
    - "**/*-src.tar.gz"
  binary_artifact_paths:
    - "**/*.zip"
  strict_checking: false
  license_check_mode: both
```

Field meanings:

- `component_id`: stable component identifier used in manifests and default output paths
- `source_artifact_prefix`: root directory prefix for reproducible source archives
- `asf_dist_dev_base`: ASF SVN `dist/dev` base URL for the component
- `asf_dist_release_base`: ASF SVN `dist/release` base URL for the component
- `moving_tags_enabled`: whether version-derived moving aliases are enabled
- `latest_tag_enabled`: whether `latest` may be derived for supported targets
- `secondary_targets`: convenience target families such as `github-action`, `github-release`,
  `github-release-assets`, `dockerhub`, or `pypi`
- `final_tag_mode`: final tag policy such as `rc-source-commit` or
  `detached-materialization-commit`
  - `rc-source-commit` means the RC and final tags point at the plain source commit
  - `detached-materialization-commit` means the RC and final tags point at a detached commit derived
    from the source commit, while the source release itself is still built from the source commit
- `vote_release_name`: human-readable name used in mail subjects and release titles
- `incubator_vote_enabled`: whether the incubator vote-mail block is emitted
- `release_summary_include_final_tag_mode`: whether summaries explicitly repeat the final tag mode
- `release_verification_guide_url`: authoritative verification-guide URL inserted into RC vote
  email templates
- `verify_rc_instructions`: authoritative RC verification text for humans
- `prepare_rc_runs_tests`: whether `Prepare RC` runs tests itself
- `release_branch_ci_required`: whether the component requires CI on `release/*` branches
- `atr`: optional ATR integration policy block
  - `enabled`: whether ATR publication and ATR check-reporting commands are enabled for this component
  - `base_url`: ATR base URL, usually `https://release-test.apache.org`
  - `committee`: ATR committee key used for release ownership and policy context
  - `product_line`: current buildish-to-ATR project key used by the official `atr` client wrapper
  - `source_artifact_paths`: planned ATR source-classification patterns
  - `binary_artifact_paths`: planned ATR binary-classification patterns
  - `strict_checking`: whether ATR hard failures should block later release progression when an ATR
    reporting step is used as a gate
  - `license_check_mode`: ATR source license-check mode, one of `both`, `lightweight`, or `rat`

ATR credentials are intentionally not stored in `release-config.yaml`.

For the current `publish-atr-candidate` and `report-atr-checks` commands:

- install the official `atr` client first
- provide `BUILDISH_ATR_ASF_UID` and `BUILDISH_ATR_PAT` in the environment
- or use the shorter aliases `ATR_ASF_UID` and `ATR_PAT`

The PAT is user-specific and should come from the ATR Tokens page, not from repository config.

## Output contract

### Exit status

- `0` means success
- non-zero means failure

The CLI currently normalizes handled command failures to exit code `1`.

### Stdout

Commands that write manifests print the manifest path to stdout.

Commands that exist only as gates or human-output steps may print nothing on success.

### Manifest files

Most commands emit a UTF-8 JSON object manifest.

Default location:

```text
<cwd>/<component-id>-<action>.json
```

Override:

```text
$MANIFEST_PATH
```

Stable manifest conventions:

- `component` is the component identifier
- `action` is the command/action name
- `version` is present when the command operates on an exact release version

Additional keys are command-specific. Additive keys may be introduced in minor releases.

### GitHub Summary

Commands that emit human-facing workflow information append Markdown to `$GITHUB_STEP_SUMMARY`.
That variable is required.

Summaries are intended for:

- vote-mail templates
- vote-result templates
- ANNOUNCE templates
- checksum and signature material
- resolved release state
- GitHub release metadata
- artifact upload lists

## Command groups

### Branch management

- `create-release-branch <release_line> <source_ref>`

### RC preparation and staging

- `verify-source-ref-checks <version> [source_sha]`
- `prepare-rc <version> [source_sha]`
- `cleanup-dev-svn-rcs <version>`
- `create-source-artifact <version> [source_sha]`
- `build-source-rc [--rc-tag <tag>] <version> [source_sha]`
- `materialize-rc-git-content [--rc-tag <tag>] --materialized-path <path>... [--materialized-ref-name <ref>] --run-command <shell> <version> [source_sha]`
- `create-rc-materialization-tag [--rc-tag <tag>] [--target-commit <sha>] <version> [source_sha]`
- `record-artifact --kind <kind> --artifact-id <id> --uri <uri> ...`
- `sync-draft-github-release [--rc-tag <tag>] <version> [source_sha]`
- `finalize-rc-vote-materials [--secondary-artifact-manifest <path>]... [--rc-tag <tag>] <version> [source_sha]`
- `publish-atr-candidate [--wait-for-checks] [--check-timeout-seconds <seconds>] [--check-interval-ms <ms>] [--rc-tag <tag>] <version> [source_sha]`
- `report-atr-checks [--revision <number>] [--verbose-atr-output] [--rc-tag <tag>] <version> [source_sha]`

### Final release materialization

- `release-version <version>`
- `publish-source-release-svn [--selected-rc-tag <tag>] <version>`
- `prune-older-line-releases <version>`
- `create-final-tag [--selected-rc-tag <tag>] <version>`
- `update-moving-tags <version>`
- `update-moving-image-aliases <version>`
- `publish-dockerhub-moving-tags <version> <source_image>`
- `attach-github-release-assets [--sign] [--checksum sha256|sha512]... <version> <assets...>`
- `finalize-draft-github-release [--selected-rc-tag <tag>] <version>`

### Human verification support

- `verify-rc [--component-config <path>] [--repro-override-file <path>] <rc_vote_manifest_url> <keys_url>`
- `inspect-repro <report_json>`

## Selected command guarantees

### `verify-rc`

- verifies one explicit signed `rc-vote-manifest.json` plus its staged source artifact and declared secondary artifacts
- requires two positional inputs:
  - the exact `rc_vote_manifest_url`
  - the explicit `keys_url` expected by the signed manifest
- writes a machine-readable JSON report and a Markdown report
- writes a combined transcript and low-level command log
- in `--mode full`, runs configured local reproducibility checks and writes a curated inspection bundle suitable for `inspect-repro`
- supports `--repro-override-file <path>` for explicit human local rebuild overrides
- treats any run with `--repro-override-file` as non-canonical and records:
  - `recipe_source=local-override`
  - the applied `override_fields`
- CI and release workflow runs should not use `--repro-override-file`; that flag exists for human local investigation when the canonical repo-maintained recipe is too narrow for one machine

Example canonical verification run:

```text
buildish-release-tooling verify-rc \
  --component-config release-config.yaml \
  https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
  https://downloads.apache.org/incubator/buildish/KEYS
```

Example non-canonical local override run:

```text
buildish-release-tooling verify-rc \
  --component-config release-config.yaml \
  --repro-override-file ~/tmp/repro-overrides.yaml \
  https://dist.apache.org/repos/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
  https://downloads.apache.org/incubator/buildish/KEYS
```

Example override file:

```yaml
verify_rc:
  profile_overrides:
    bootstrap-zip:
      build:
        command: ["./buildish-release-tooling/rebuild-bootstrap-local.sh"]

    pypi-wheel:
      build:
        working_dir: "python-package"
        env:
          PIP_NO_BUILD_ISOLATION: "1"
```

### `inspect-repro`

- reads one saved `verify-rc` JSON report plus its inspection bundle
- explains failed reproducibility checks without rerunning remote verification
- surfaces the selected `profile_id`, `recipe_source`, `override_fields`, retained evidence files, and kind-specific drift details

### `prepare-rc`

- resolves the release branch, next RC number, and authoritative source commit for one version
- writes the full JSON manifest to `MANIFEST_PATH`
- appends `rc_tag` and `resolved_source_ref` to `GITHUB_OUTPUT` when that file path is present

### `create-source-artifact`

- builds from Git using a fixed mtime and reproducible gzip settings
- creates a source tarball rooted at `source_artifact_prefix-<version>-incubating-src/`
- emits the SHA512 line in the summary

### `build-source-rc`

- creates the reproducible source artifact
- writes `.sha512`
- creates a detached ASCII-armored signature
- stages the artifact set into ASF SVN `dist/dev`
- accepts `--rc-tag` so later reruns in one `Prepare RC` workflow stay bound to the same RC
- does not by itself define where the RC Git tag must point; that remains component policy

### `materialize-rc-git-content`

- valid only for components whose `final_tag_mode` is `detached-materialization-commit`
- resolves the same authoritative RC source commit as the rest of the `Prepare RC` flow
- creates an isolated detached worktree from that source commit
- runs one caller-provided shell command in that detached worktree after the workflow has already
  prepared any project-specific toolchain state
- accepts repeatable repository-relative file or directory `--materialized-path` inputs and
  force-stages them so git-ignored payloads such as `dist/` can be committed without entering
  normal branch history
- creates one detached materialization commit and emits its exact commit SHA
- pushes that detached commit to a temporary remote ref so later workflow jobs can tag it before
  the temporary anchor ref is deleted
- accepts `--materialized-ref-name` as an override, but generates a default temporary remote ref
  name when one is not provided
- appends `materialized_commit_sha` and `materialized_ref_name` to `GITHUB_OUTPUT` when that file
  path is present

### `create-rc-materialization-tag`

- creates the RC tag for the resolved version
- tags the resolved source commit by default
- requires `--target-commit` for components that use detached materialization commits
- accepts `--rc-tag` so the tag-creation step can reuse the RC number resolved earlier in the workflow
- can optionally clean up one temporary remote anchor ref after the RC tag has been created
- fails if the RC tag already exists, even when it already points at the same commit
- this prevents concurrent same-version `Prepare RC` runs from silently sharing one RC tag

### `record-artifact`

- writes one typed secondary-artifact manifest fragment for later RC finalization
- currently supports `--kind generic-file`, `--kind maven-repository`,
  `--kind oci-image`, `--kind python-distribution`, and `--kind npm-package`
- for `generic-file`, computes the SHA512 digest from `--file` when one is supplied, or validates
  an explicit `--sha512` when both are provided
- when `--git-commit-sha` is supplied and `--artifact-origin` is omitted, records
  `artifact_origin: source-commit`
- for `npm-package`, can derive the canonical tarball URI from `--registry-url`,
  `--package-name`, and `--package-version`, or derive those registry fields from a canonical
  npm tarball `--uri`; it records integrity material derived from `--file` or validated from
  `--integrity`, `--sha256`, or `--sha512`
- for `maven-repository`, recursively snapshots the repository rooted at `--base-url` and writes a
  detached inventory file into the registration bundle
- for `maven-repository`, defaults `--base-url` to
  `https://repository.apache.org/content/repositories/<staging-repository-id>/` when omitted
- for `maven-repository`, defaults remote discovery and digest fetching to 16 workers and allows
  overriding that with `--inventory-workers`
- writes one registration bundle rooted at
  `build/release-artifacts/<component>/secondary-artifacts/<artifact-id>/` by default
- prints the fragment path on stdout so shell steps can pass it directly to later commands
- appends `artifact_id`, `artifact_kind`, `artifact_manifest_path`, and `artifact_bundle_dir`
  to `GITHUB_OUTPUT` when that file path is present
- is intended to be paired with GitHub workflow artifacts for cross-job handoff: producer jobs
  upload the bundle, and the finalization job downloads it before calling
  `finalize-rc-vote-materials --secondary-artifact-manifest ...`

### `finalize-rc-vote-materials`

- requires the RC tag and draft GitHub Release to already exist
- builds `rc-vote-manifest.json` from resolved live Git/SVN/GitHub state
- accepts `--secondary-artifact-manifest` inputs for typed secondary-artifact fragments, including
  manifests produced earlier by `record-artifact`
- stages detached secondary-artifact inventory files referenced by those fragments and rewrites
  their final authoritative URIs into the signed RC vote manifest
- accepts `--rc-tag` so reruns keep using the already-selected RC
- writes `.sha512`
- creates a detached ASCII-armored signature for the manifest
- stages the manifest set into ASF SVN `dist/dev`
- mirrors the manifest set to the draft GitHub Release
- emits the project RC vote email template alongside the machine-readable manifest
- emits a later-use IPMC vote-request template for podlings, with human-fill thread placeholders

### `publish-atr-candidate`

- requires ATR integration to be enabled in the component config
- wraps the official `atr` client instead of speaking the unstable ATR API directly
- downloads the staged RC source-release files and the staged authoritative RC vote-manifest files
- creates or reuses the ATR draft release for the configured product line and version
- uploads the candidate files into ATR
- can optionally wait for ATR's initial checks and include a status snapshot in the summary and manifest

### `report-atr-checks`

- fetches ATR check status for the latest ATR revision by default, or for one exact `--revision`
- records ATR counts and status output in the emitted summary and manifest
- stays advisory when `atr.strict_checking` is `false`
- fails the command when ATR reports hard failures or exceptions and `atr.strict_checking` is `true`

### `release-version`

- resolves the selected RC tag from the exact-version draft GitHub Release
- derives the specific release line from the exact version
- reads previously published versions from ASF SVN `dist/release`
- computes same-line pruning and moving-tag plans
- assumes the final exact tag should reuse the released RC commit, whether that RC commit is the
  plain source commit or a detached materialization commit
- emits a project vote-result email template with human-fill vote-count placeholders
- should hand off `selected_rc_tag` to later `Release version` jobs in the same workflow

### `create-final-tag`

- creates the immutable exact final Git tag for the version
- targets the same commit as the selected RC tag
- accepts `--selected-rc-tag` so later jobs can fail if the draft GitHub Release drifts to a newer RC
- prefers GitHub API tag creation when the repository slug is available
- treats an already-existing final tag on the same target commit as a successful no-op

### `update-moving-tags`

- currently supports Git tag-backed aliases such as GitHub Action `v1` / `v1.2`
- requires the immutable exact final tag to already exist
- applies the documented no-backward-move policy before mutating any alias
- updates an existing alias only when the new version is newer within that alias's scope
- treats an alias that already points at the intended final release as a successful no-op

### `attach-github-release-assets`

- locates the existing GitHub Release by exact final tag
- uploads one or more files through `gh release upload`
- uses replace semantics through `--clobber`
- may additionally generate detached `*.asc` signatures
- may additionally generate `*.sha512` and `*.sha256` sidecars
- rejects duplicate upload basenames before invoking GitHub

GitHub release assets are convenience artifacts only. They are not the authoritative ASF release.

### `publish-dockerhub-moving-tags`

- derives moving Docker Hub aliases such as `1`, `1.2`, and optionally `latest`
- requires an already-pushed exact source image reference
- authenticates with `DOCKERHUB_USER` and `DOCKERHUB_TOKEN`
- uses `docker buildx imagetools create --prefer-index=false` so one command path can alias both
  normal single-platform images and multi-platform images already present in the registry
- publishes only the derived aliases; it does not build or push the exact image itself

### `finalize-draft-github-release`

- removes draft-only RC vote-manifest assets when present
- accepts `--selected-rc-tag` so the final publication step can fail if the draft GitHub Release
  drifted to a different RC after `release-version` resolved it
- publishes the draft GitHub Release for the final tag
- treats an already-published final release as a successful no-op
- emits the final ANNOUNCE email template with a human-fill placeholder for release-specific text

## External tool requirements

Depending on the command, the runtime expects these tools on `PATH`:

- `git`
- `svn`
- `gh`
- `gpg`
- `gzip`

Integration tests also use `svnadmin`.

## Logging and secret handling

Subprocess commands such as `git`, `svn`, `gh`, and `gpg` are logged with arguments for workflow
debuggability.

The documented secret-bearing values are redacted from command logs.

## Non-contract details

The following are intentionally not public API:

- Python module names and function names
- internal helper behavior that is not surfaced through the CLI
- undocumented environment-variable fallbacks for positional arguments
- exact Markdown wording in summaries, except where a workflow explicitly consumes it as human text
