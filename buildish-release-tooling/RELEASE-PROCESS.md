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

# Release Tooling Release Process

Buildish Release Tooling publishes itself through TestPyPI rehearsal, a retained signed GitHub
candidate, independent verification, and exact promotion to GitHub and PyPI.

Use the maintained operator guides:

- [First self-release](../docs/first-self-release.md): deployment audit, exact source preparation,
  dispatch commands, evidence review, and first-publication acceptance checks.
- [Follow-up self-releases](../docs/follow-up-releases.md): version and legal preparation, recurring
  release steps, and interrupted-publication recovery.
- [Self-release deployment](../docs/self-release.md): workflow architecture, repository settings,
  signing inputs, and exact Trusted Publisher identities.

Approval selects one exact candidate tag and candidate-manifest SHA-256. Promotion reuses that
candidate's distribution bytes. A release is complete only after both publication channels verify
and the final release manifest and durable attestation evidence are attached.
