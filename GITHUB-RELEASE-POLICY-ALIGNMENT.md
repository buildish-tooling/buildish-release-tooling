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

# GitHub Release Policy Alignment Plan

This note is an implementation handoff for aligning Buildish GitHub release behavior with current ASF guidance for both:

- top-level ASF projects
- Apache Incubator podlings

It is written so another agent can pick it up and implement the changes directly.

## Why this exists

Recent Incubator discussion and current ASF guidance make the practical requirements clear:

- GitHub Releases are not the authoritative ASF release channel.
- ASF `downloads.apache.org` / `dist/release` remains authoritative.
- GitHub Releases may be used as a convenience channel.
- Incubating projects must show the incubating disclaimer clearly on GitHub release pages.
- RCs, snapshots, and nightlies must not appear as normal public releases; if public on GitHub, they need to be marked as pre-releases.

Relevant policy and discussion:

- Incubator distribution guide:
  - <https://incubator.apache.org/guides/distribution.html>
- Infra release distribution policy:
  - <https://infra.apache.org/release-distribution.html>
- Mailing-list thread:
  - <https://www.mail-archive.com/general%40incubator.apache.org/msg86357.html>
  - <https://www.mail-archive.com/general%40incubator.apache.org/msg86363.html>
  - <https://www.mail-archive.com/general%40incubator.apache.org/msg86373.html>
  - <https://www.mail-archive.com/general%40incubator.apache.org/msg86359.html>

## Current state in this repo

These parts are already directionally correct:

- RC GitHub releases are created as drafts, not immediately published.
- Draft bodies already say the GitHub release is convenience metadata only.
- Final publication workflow promotes ASF dist first, then finalizes the GitHub release.
- User docs already say GitHub release assets are not authoritative ASF releases.

Relevant code:

- draft body creation:
  - [src/apache_buildish_release_tooling/release/commands/release_publication.py](src/apache_buildish_release_tooling/release/commands/release_publication.py)
  - [src/apache_buildish_release_tooling/release/commands/vote_materials.py](src/apache_buildish_release_tooling/release/commands/vote_materials.py)
- draft create/update:
  - [src/apache_buildish_release_tooling/release/github_release_selection.py](src/apache_buildish_release_tooling/release/github_release_selection.py)
- final publication:
  - [src/apache_buildish_release_tooling/release/commands/release_publication.py](src/apache_buildish_release_tooling/release/commands/release_publication.py)
- workflow orchestration:
  - [.github/workflows/releasey-20-prepare-rc.yml](.github/workflows/releasey-20-prepare-rc.yml)
  - [.github/workflows/releasey-30-release-version.yml](.github/workflows/releasey-30-release-version.yml)

## Current gaps

### 1. No incubating disclaimer on GitHub release pages

`incubator_vote_enabled` exists, but today it is used for vote/mail behavior, not for GitHub release title/body generation.

That is insufficient for podlings.

### 2. Final published GitHub release still looks like a draft placeholder

Current draft body text is reused too far into the flow. The final public GitHub release should not say "Draft GitHub Release placeholder".

### 3. No explicit public pre-release mode

The code hardcodes `prerelease: False` for:

- draft create/update
- final publication

That is acceptable for non-public drafts, but not enough if this tool ever supports public RC/nightly/snapshot GitHub releases.

### 4. No explicit handling for historical pre-ASF GitHub releases

That matters for migrated incubating projects that already had GitHub releases before entering the ASF.

## Target behavior

## Top-level ASF projects

For top-level projects:

- GitHub Releases may be used as convenience release pages and convenience asset mirrors.
- Final public GitHub release pages must clearly state that ASF downloads are authoritative.
- RC draft GitHub releases should remain drafts by default.
- Draft release text must never imply the GitHub release is itself the authoritative ASF release.

## Incubating projects

For podlings:

- Any public GitHub release page must include the incubating disclaimer clearly.
- Any public RC/nightly/snapshot GitHub release page must be marked as `prerelease=true`.
- Final public incubating releases may exist as convenience pages only if they:
  - include the incubating disclaimer
  - clearly point to authoritative ASF release artifacts
  - do not present GitHub as the authoritative release channel

## Recommended implementation model

Keep the current draft-based RC flow. Do not switch RC handling to public pre-releases by default.

Instead:

1. RC GitHub releases remain drafts.
2. Final public GitHub releases get a dedicated final-release body.
3. Podling-specific disclaimer injection is driven by config.
4. Pre-release support is added as a capability for future public RC/nightly/snapshot flows.

That gives correct current behavior without inventing a new distribution model.

## Concrete implementation tasks

### Task A: Introduce explicit GitHub release text rendering

Add dedicated helpers for GitHub release page content, instead of embedding strings in command modules.

Suggested new module:

- `src/apache_buildish_release_tooling/release/github_release_text.py`

Suggested functions:

- `render_draft_github_release_name(...)`
- `render_draft_github_release_body(...)`
- `render_final_github_release_name(...)`
- `render_final_github_release_body(...)`
- `incubator_disclaimer_block(...)`
- `authoritative_release_links_block(...)`

Rationale:

- centralizes policy wording
- avoids drift between draft/final behavior
- makes test coverage straightforward

### Task B: Distinguish draft and final public GitHub release bodies

Current draft copy is suitable only for draft state.

Required final body properties:

- must not say "draft placeholder"
- must identify GitHub as convenience metadata / convenience assets only
- must link to authoritative ASF release location
- should link to KEYS and signatures/checksums where relevant
- for podlings, must include incubating disclaimer

The final release body should be rendered during `finalize-draft-github-release`, not inherited unchanged from the draft body.

### Task C: Make title rendering policy-aware

Current `_release_name()` returns:

- `"{vote_release_name} {version}"`

That is too generic.

At minimum:

- final public podling release titles should include `-incubating` in the displayed version or otherwise clearly reflect incubating status
- draft titles may remain simple, but should still be consistent with the chosen policy

Do not guess. Make this explicit in one renderer.

### Task D: Use `incubator_vote_enabled` for GitHub release content too

Current behavior:

- used for email/vote content

Required behavior:

- also controls incubator-specific GitHub release disclaimers and title/body labeling

If the existing field name becomes awkward, add a new config flag only if really needed. Prefer reusing the existing flag if semantics stay coherent.

### Task E: Add an explicit pre-release policy knob for future public RC/nightly/snapshot GitHub releases

This is not mainly for the current draft RC path. It is forward-looking.

Suggested config shape:

- `github_release_rc_visibility: "draft" | "public-prerelease"`
- default: `"draft"`

Behavior:

- `draft`: current behavior, non-public RC GitHub release
- `public-prerelease`: if ever used, requires `prerelease=true`

Do not change current default workflow behavior.

### Task F: Add a documented path for historical pre-ASF releases

This is likely not an automated core flow, but the project should have a supported way to represent this.

Minimum acceptable outcome:

- document operational guidance for migrated projects:
  - old GitHub releases should be labeled as pre-ASF or otherwise clearly described
- optionally add a helper command later

This can be docs-only if code support is not needed immediately.

### Task G: Tighten docs

Update:

- `docs/_index.md`
- `docs/reference/`
- any release workflow docs that mention GitHub release publication

Document separately:

- top-level ASF behavior
- incubating project behavior
- RC draft behavior
- future/public pre-release behavior if configured

The docs should say clearly:

- GitHub Releases are convenience only
- authoritative artifacts are on ASF infrastructure
- incubating disclaimer is required for podlings

## Acceptance criteria

### Top-level project acceptance

For a non-incubating component:

- `sync-draft-github-release` creates/updates a draft release with draft-specific text
- `finalize-draft-github-release` rewrites to final public text before publishing
- final public page says GitHub is convenience only and points to ASF authoritative release location

### Incubating project acceptance

For `incubator_vote_enabled=true`:

- draft GitHub release body includes incubating disclaimer
- final public GitHub release body includes incubating disclaimer
- visible release naming/body text reflects incubating status clearly

### RC/public pre-release acceptance

If future config enables a public RC/nightly/snapshot GitHub release mode:

- the GitHub release must be published with `prerelease=true`
- generated docs must say this mode is for unreleased materials only

### Non-regression acceptance

- existing draft-based RC workflow remains the default
- final publication still occurs only after ASF source release promotion
- existing command manifests and docs remain coherent after field changes

## Required test coverage

Add or update tests for:

### Unit tests

- dedicated release text rendering:
  - top-level draft
  - top-level final
  - incubating draft
  - incubating final
- optional future public pre-release mode rendering / flags

### Command tests

- `sync-draft-github-release` emits draft body text with expected fields
- `finalize-draft-github-release` emits final body text, not draft text
- incubating project config adds disclaimer in both places

### Workflow/contract tests

- docs/examples/reference output stay aligned
- command manifests remain valid if any new config field is added

## Suggested implementation order

1. Add `github_release_text.py`.
2. Refactor draft body generation to use it.
3. Refactor final publication to render a dedicated final body.
4. Make name rendering policy-aware.
5. Add incubator disclaimer injection.
6. Add tests.
7. Update docs.
8. Only then consider adding future public pre-release config.

## Things to avoid

- Do not make GitHub Releases look authoritative.
- Do not publish RC GitHub releases publicly by default.
- Do not hide incubating status in GitHub titles/body text.
- Do not spread policy text across multiple command modules again.

## Minimal acceptable patch

If the follow-up work must be scoped narrowly, the minimum acceptable compliance improvement is:

1. add incubating disclaimer to GitHub release bodies when `incubator_vote_enabled=true`
2. make final public GitHub release body distinct from the draft body
3. keep explicit "convenience only" language and authoritative ASF links in final public body

That would address the main issue raised by the thread without redesigning the workflow.
