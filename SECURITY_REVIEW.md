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

# Security Review

Reviewed repository state:

- Commit: `ba75417b6f1341e392fd8c0307828adfe9085c08`
- Review time: `2026-04-26T13:08:19Z`
- Scope: `src/`, `.github/workflows/`, `buildish-release-tooling/`
- Process note: this review intentionally replaced the prior `SECURITY_REVIEW.md` without reading it

## Executive Summary

I found one high-severity integrity issue and two lower-severity trust-boundary issues.

| Severity | Finding |
| --- | --- |
| High | Draft GitHub release creation can create the final version tag before the vote passes |
| Medium | RC vote-manifest finalization signs mutable staging sidecars instead of hashing the staged artifact bytes |
| Low | Production trust roots and artifact URIs are accepted from raw config strings with `file://` and plain `http://` support |

## Findings

### 1. High: Draft GitHub release creation can create the final version tag before the vote passes

Affected code:

- [src/apache_buildish_release_tooling/commands.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/commands.py:1190)
- [src/apache_buildish_release_tooling/github_releases.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/github_releases.py:166)
- [.github/workflows/releasey-20-prepare-rc.yml](/home/snazy/devel/apache/buildish/buildish-release-tooling/.github/workflows/releasey-20-prepare-rc.yml:189)
- [.github/workflows/releasey-30-release-version.yml](/home/snazy/devel/apache/buildish/buildish-release-tooling/.github/workflows/releasey-30-release-version.yml:111)

`run_sync_draft_github_release()` creates a draft release on `state.final_tag` and passes `state.resolved_source_ref` as `target_commitish`. That happens during `Releasey Prepare RC`, before the later `create-final-tag` job in `Releasey Release Version`.

GitHub's release-creation API uses `target_commitish` when the requested tag does not already exist. In practice, that means the prepare-RC workflow can create `vX.Y.Z` early, before the ASF vote passes.

Impact:

- The workflow can materialize the final tag before approval, which breaks the intended "final tag only after a passed vote" invariant.
- The later `create-final-tag` step will silently accept a pre-existing same-target tag via `_create_or_reuse_annotated_tag()`, so this early tag creation is not corrected.
- For detached-materialization components, the early auto-created tag would point at the source commit, not the later materialized commit, creating either a wrong tag target or a later failure.

Recommendation:

- Do not create the draft GitHub release on the final tag before release finalization.
- Use the RC tag as the draft release tag, or use some other metadata placeholder that cannot create the final release marker.
- Alternatively, explicitly verify the final tag does not exist before draft-release creation and fail if GitHub would auto-create it.

### 2. Medium: RC vote-manifest finalization signs mutable staging sidecars instead of hashing the staged artifact bytes

Affected code:

- [src/apache_buildish_release_tooling/commands.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/commands.py:1937)

`run_finalize_rc_vote_materials()` reads the staged source checksum from `apache-...tar.gz.sha512` and the staged signature text from `apache-...tar.gz.asc`, then signs a new authoritative `rc-vote-manifest.json`. It does not recompute the staged tarball's SHA-512 from the tarball bytes before signing the manifest.

Relevant lines:

- `source_artifact_sha512 = read_uri_text(f"{source_artifact_url}.sha512").strip().split()[0]`
- `source_signature_text = read_uri_text(f"{source_artifact_url}.asc").strip()`

Impact:

- If the staged source tarball or its sidecars are modified after `build-source-rc` but before `finalize-rc-vote-materials`, the signed vote manifest can bless the modified staging contents.
- The later `publish-source-release-svn` step does recompute the staged tarball checksum, but by then the vote manifest has already become the signed authoritative record used during the vote.

Recommendation:

- Recompute the staged tarball SHA-512 from `source_artifact_url` before constructing the manifest.
- Compare the recomputed digest to the staged `.sha512` sidecar and fail on mismatch.
- Optionally verify that the staged `.asc` is a valid detached signature for the staged tarball before signing the vote manifest.

### 3. Low: Production trust roots and artifact URIs are accepted from raw config strings with `file://` and plain `http://` support

Affected code:

- [src/apache_buildish_release_tooling/config.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/config.py:26)
- [src/apache_buildish_release_tooling/models.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/models.py:25)
- [src/apache_buildish_release_tooling/rc_vote_manifest.py](/home/snazy/devel/apache/buildish/buildish-release-tooling/src/apache_buildish_release_tooling/rc_vote_manifest.py:116)

`ComponentConfig` accepts raw `asf_dist_dev_base` and `asf_dist_release_base` strings without scheme or domain validation. `trust_root_metadata()` then derives a `KEYS` URI from those values, and `read_uri_bytes()` will read:

- local files via `file://`
- plain HTTP via `http://`
- HTTPS via `https://`

Impact:

- A modified component config on the executed ref can make the signed RC vote manifest bless a non-ASF `KEYS` location.
- Plain `http://` is accepted, so a production trust root can be downgraded from authenticated transport to cleartext transport.
- `file://` is useful for the harness, but leaving it enabled in production release paths expands the blast radius of config mistakes and malicious config changes.

Recommendation:

- Add explicit production validation for release-target URIs.
- Allow `file://` only under an explicit harness or test mode.
- Restrict production trust roots and release endpoints to expected schemes and domains such as `https://dist.apache.org/`, `https://downloads.apache.org/`, and GitHub endpoints used for mirrored assets.

## Positive Notes

- GitHub and SVN passwords are no longer passed on subprocess argv.
- Final SVN publication now revalidates the staged RC directory against the mirrored RC vote manifest.
- The `act` harness no longer copies ambient `GITHUB_TOKEN` or `GH_TOKEN` into its generated secret file.
