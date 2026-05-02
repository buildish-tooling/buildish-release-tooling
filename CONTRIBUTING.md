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

# Contributing to Apache Buildish

Thank you for considering a contribution to Apache Buildish.

## Before opening a pull request

- Check whether an existing issue or pull request already covers the change.
- For larger changes, start a short design discussion on a GitHub issue before investing heavily in implementation.
- Keep pull requests focused; split unrelated work into separate changes.

## Pull request expectations

- Base pull requests on `main`.
- Describe the motivation and the change clearly.
- Add or update tests and documentation when applicable.
- Keep commit messages and pull request text readable for future project history.

## Modeling and JSON handling

- Buildish-owned persisted or boundary data should use pydantic models.
- Internal structured helper state should use dataclasses or typed partial-reader models.
- Raw `dict[str, Any]` payloads should stay isolated to explicit external or tolerant-input boundaries.

This keeps manifest, report, and verifier code easier to reason about and makes typos less likely to turn into runtime bugs.

## Verification contract changes

The verifier now has supported machine-readable contracts:

- `verify-rc` report JSON schema version `1`
- inspection-bundle schema version `1`
- `inspect-repro --json` schema version `1`

When changing those contracts:

- additive fields within schema version `1` are fine when existing meanings stay intact
- incompatible field-shape or field-meaning changes require a new explicit schema version
- do not silently repurpose existing fields
- update `docs/verification-contracts.md` in the same change
- update golden-shape tests for the affected report or bundle outputs

Verification output must also keep this invariant:

- environment variable names may be reported
- environment variable values must not be reported in reports, bundles, transcripts, or
  `inspect-repro` JSON output

## Security issues

Do **not** open a public issue for a suspected security vulnerability. Instead, report it to [security@apache.org](mailto:security@apache.org).
