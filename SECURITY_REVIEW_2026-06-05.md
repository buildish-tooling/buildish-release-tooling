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

# Security Review - 2026-06-05

Reviewed repository state:

- Commit: remediation commit containing this review
- Review time: `2026-06-05T14:30:00+02:00`
- Scope: `src/`, `.github/workflows/`, `buildish-release-tooling/`, root security docs, and the draft threat model in `docs/threat-model.md`
- Method: source inspection focused on release-integrity boundaries, credential handling, GitHub Actions workflow controls, and previously reported security-review themes
- Worktree note: this review was performed with uncommitted documentation changes present, including `docs/threat-model.md`

## Executive Summary

I found one lower-severity workflow-control hardening issue.

| Severity | Finding |
| --- | --- |
| Low | GitHub write jobs are not directly gated by GitHub Environment approval |

I also confirmed that several issues from the older `SECURITY_REVIEW.md` appear to have been addressed in the current tree:

- Draft GitHub Releases are now created on the RC tag rather than the final tag.
- Production ASF dist base URLs are now validated against expected HTTPS ASF prefixes unless non-production mode is explicitly enabled.
- RC vote-manifest finalization now recomputes the staged source artifact hash before signing the vote manifest.
- Final publication now verifies the RC vote manifest checksum and detached signature before trusting manifest contents.
- Manual Prepare RC and Release Version workflows now serialize by repository and exact version with non-canceling concurrency groups.

## Findings

### 1. Low: GitHub write jobs are not directly gated by GitHub Environment approval

Affected workflows:

- `.github/workflows/releasey-20-prepare-rc.yml:158`
- `.github/workflows/releasey-20-prepare-rc.yml:193`
- `.github/workflows/releasey-30-release-version.yml:111`
- `.github/workflows/releasey-30-release-version.yml:147`

The checked-in workflows already use `environment: draft-release-secrets` on jobs that read SVN or GPG environment secrets. However, several jobs with `permissions: contents: write` do not declare an environment directly:

- `create-rc-tag`
- `sync-draft-github-release`
- `create-final-tag`
- `finalize-draft-github-release`

These jobs are usually sequenced after an environment-gated job, so this is not a direct bypass of the current SVN/GPG secret gate. It is still a control gap if the intended policy is that GitHub Environment approval should gate every release mutation, not only jobs that consume environment-scoped secrets.

Impact:

- GitHub tag and release mutations use the repository `github.token`, not an environment-scoped secret, so they can run without their own environment approval once their dependency graph is satisfied.
- Rerun behavior can make this distinction matter: a write job can be rerun without re-approving the environment if that specific job has no environment.
- Projects that consume this release tooling and move GitHub write authentication into environment-protected PATs will also need to remember to add `environment:` to those jobs, or those secrets will not be exposed.

Recommendation:

- If the intended release policy is approval before all release mutations, add the relevant release environment to all GitHub-write jobs, not only SVN/GPG-secret jobs.
- Consider using separate environments with clearer names, for example `rc-staging-release-secrets` and `final-release-publication`, if RC preparation and final publication require different approvers.
- Document that the local `act` harness does not validate GitHub Environment protection semantics, so this control must be reviewed in workflow YAML and on GitHub itself.

## Positive Notes

- GitHub and SVN credentials are not passed as plain command-line password arguments. SVN passwords are sent through stdin, and GitHub push credentials use a short-lived askpass helper.
- Command logging redacts documented secret-bearing environment values.
- Host-direct reproducibility rebuilds scrub common CI, cloud, package-manager, GitHub, GPG, SVN, and SSH credential variables before executing candidate build commands.
- Verifier-facing structured input parsing and archive inspection paths use explicit size and entry-count bounds in the reviewed code paths.
- Production `asf_dist_dev_base` and `asf_dist_release_base` values now require expected ASF HTTPS prefixes unless explicit non-production mode is enabled.
- The harness no longer copies ambient host `GITHUB_TOKEN` or `GH_TOKEN` values into generated `act` secrets; scenario secrets must be declared explicitly.

## Suggested Follow-Up Tests

- Workflow lint or unit test asserting that every release job with `permissions.contents: write` declares an approved release environment when the project policy requires environment-gated release mutation.
