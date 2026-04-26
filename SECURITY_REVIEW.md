# Security Review Report

Date: 2026-04-26

Scope: manual review of the repository in its current working tree, focused on release-time trust boundaries, credential handling, filesystem writes, subprocess execution, and harness behavior. I did not perform internet-facing testing or dependency CVE triage.

## Executive Summary

I found 4 issues:

- High: path traversal and out-of-directory writes when `source_sha` is supplied with an unvalidated `version`
- Medium: GitHub and SVN credentials are passed in child-process arguments
- Medium: final release publication trusts mutable SVN staging contents by filename only
- Low: the harness persists secrets and command output to workspace files with minimal containment

## Findings

### 1. High: explicit `source_sha` mode skips version validation and enables path traversal

Affected code:

- `src/apache_buildish_release_tooling/prepare_rc_state.py:56-86`
- `src/apache_buildish_release_tooling/commands.py:886-888`
- `src/apache_buildish_release_tooling/commands.py:921-934`

Details:

- `resolve_prepare_rc_state()` validates the version only when it has to derive a release branch.
- When `source_sha` is provided, the code takes the caller-supplied `version` verbatim and uses it to build:
  - `source_artifact_name`
  - `staging_url`
  - tag names and other release identifiers
- `run_create_source_artifact()` and `run_build_source_rc()` then join that derived filename onto `build/release-artifacts/<component>/`.

Impact:

- A crafted `version` containing slashes and `..` segments can escape the intended artifact directory and write files elsewhere on the runner filesystem with the workflow's privileges.
- `build-source-rc` also creates `.sha512` and `.asc` sidecars for the escaped path.
- The same unsanitized value also contaminates the derived SVN staging URL.

Concrete example:

```text
version = "/../../../../tmp/poc"
source_artifact_name = "prefix-/../../../../tmp/poc-incubating-src.tar.gz"
resolved output path = <repo>/tmp/poc-incubating-src.tar.gz
```

That behavior was reproducible by resolving the joined `Path` locally; the escape does not depend on any unusual filesystem semantics.

Recommendation:

- Enforce semantic-version validation in `resolve_prepare_rc_state()` regardless of whether `source_sha` is supplied.
- Treat `version` as structured data, not as a filesystem fragment.
- Reject `/`, `\\`, `..`, and any non-semantic-version input before deriving filenames, URLs, or tags.

### 2. Medium: release credentials are exposed in child-process argv

Affected code:

- `src/apache_buildish_release_tooling/asf_svn.py:52-69`
- `src/apache_buildish_release_tooling/commands.py:265-290`

Details:

- SVN credentials are passed as `svn --username <user> --password <password> ...`.
- GitHub tokens are embedded directly into the remote URL as `https://x-access-token:<token>@github.com/...` before `git push`.
- The project redacts these values in its own command logs, but that does not protect against OS-level exposure through:
  - `/proc/<pid>/cmdline`
  - process monitors
  - crash dumps
  - host audit tooling

Impact:

- On self-hosted or shared runners, another local process can recover the GitHub token or SVN password while the command is running.
- This is especially relevant because the tool is designed for privileged release workflows.

Recommendation:

- Stop placing secrets in argv.
- For Git, use a credential helper, `GIT_ASKPASS`, or another non-argv authentication path.
- For SVN, use an authentication mechanism that keeps the secret out of the process command line and any persisted cache should be isolated and permission-restricted.

### 3. Medium: final release publication trusts mutable SVN staging contents by filename only

Affected code:

- `src/apache_buildish_release_tooling/commands.py:1135-1164`
- Related integrity material is produced earlier in `src/apache_buildish_release_tooling/commands.py:1732-1783`

Details:

- `finalize-rc-vote-materials` creates a signed manifest and records the staged source artifact checksum.
- `publish-source-release-svn` later checks only that the staged RC directory contains the expected filenames, then copies the entire directory from `dist/dev` to `dist/release`.
- It does not verify that:
  - the staged tarball still matches the checksum recorded in the authoritative RC vote manifest
  - the staged artifact still corresponds to the selected RC tag
  - no unexpected extra files were introduced into the staging directory

Impact:

- If the mutable `dist/dev` staging area is altered after voting but before publication, the tool can publish tampered content.
- An attacker with temporary write access to staging does not need to compromise the release workflow itself if the publish step never revalidates the staged bytes.

Recommendation:

- Before promotion, fetch and verify the authoritative `rc-vote-manifest.json` from staging.
- Recompute the staged artifact checksum and require an exact match with the manifest.
- Reject unexpected files unless they are explicitly allowed by policy.

### 4. Low: the harness persists secrets and raw command output in workspace files

Affected code:

- `src/apache_buildish_release_tooling/harness/act_backend.py:421-432`
- `src/apache_buildish_release_tooling/harness/runtime.py:463-491`
- `src/apache_buildish_release_tooling/harness/shim_entrypoint.py:445-475`

Details:

- The `act` backend writes scenario secrets, and host `GITHUB_TOKEN` / `GH_TOKEN` when present, to `.buildish-release-harness/act.secrets`.
- Step stdout/stderr is appended verbatim to workspace log files.
- The shim trace can also persist selected environment variables into `command-trace.jsonl`.

Impact:

- Secrets can remain on disk after a harness run and may be exposed if the workspace is archived, shared, or inspected by other local users.
- This is more of a local containment issue than a remote vulnerability, but it is easy to trigger accidentally.

Recommendation:

- Write secret files with restrictive permissions (`0600` or equivalent).
- Avoid importing host GitHub tokens into harness state unless explicitly requested.
- Document that harness workspaces contain sensitive material and should be deleted after use.
- Consider redacting captured stdout/stderr and environment snapshots when they include known secret names.

## Suggested Remediation Order

1. Fix the `version` validation gap in `resolve_prepare_rc_state()`.
2. Remove GitHub and SVN secrets from subprocess argv.
3. Bind `publish-source-release-svn` to the previously signed RC vote manifest.
4. Tighten harness secret storage and logging behavior.
