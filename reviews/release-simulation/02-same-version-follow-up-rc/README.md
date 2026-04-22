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

# Scenario 02: Follow-Up RC For The Same Exact Version

## Assumptions

- Exact version: `1.2.3`
- Existing tags: `v1.2.3-rc0`, `v1.2.3-rc1`
- Existing staged RC directories: `1.2.3-rc0/`, `1.2.3-rc1/`
- The release branch head has moved and a new RC is intended

## Workflow Path

- `Releasey Prepare RC`

## Job And CLI Trace

1. `verify-source-ref-checks`
2. `resolve-state`
   - `resolve_prepare_rc_state()` allocates the next matching RC number from Git tags.
   - resolved `rc_tag=v1.2.3-rc2`
3. `cleanup-dev-svn-rcs`
   - deletes all `1.2.3-rcN/` directories in ASF SVN dev dist
4. `build-source-rc`
   - `build-source-rc --rc-tag v1.2.3-rc2 1.2.3`
   - rebuilds and restages the RC into `.../1.2.3-rc2/`
5. `create-rc-tag`
   - `create-rc-materialization-tag --rc-tag v1.2.3-rc2 1.2.3`
   - creates `v1.2.3-rc2`
6. `sync-draft-github-release`
   - `sync-draft-github-release --rc-tag v1.2.3-rc2 1.2.3`
   - deletes any lower-RC draft release for `v1.2.3`
   - fails if a higher-RC draft release already exists
7. `finalize-rc-vote-materials`
   - `finalize-rc-vote-materials --rc-tag v1.2.3-rc2 1.2.3`

## Logical Outcome

- A sequential follow-up RC for the same exact version now works.
- The new RC gets a fresh tag and a fresh ASF SVN dev staging directory.
- Later jobs in the same workflow stay pinned to the same RC number because they consume the
  `resolve-state` output rather than recomputing RC state.

## Findings

- No remaining shared-tooling correctness bug was found for the sequential follow-up RC case.
- If two `prepare-rc` runs for the same exact version still race, the RC tag creation step is now
  fail-fast rather than silently reusing the same RC tag.
