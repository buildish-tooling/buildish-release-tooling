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

# Released documentation snapshots

This branch has independent history from `main`. Each version directory contains
`docs/` copied from its exact `vX.Y.Z` Git tag. `provider-snapshot.json` records
those tags and resolved source commits for Site Pipeline.

## Curated publication state

- **0.1.3 — published:** first completed candidate-to-promotion publication with
  the final release manifest and durable PyPI verification evidence.
- **0.1.2 — hidden from the documentation website:** GitHub/PyPI publication
  occurred, but promotion could not attach its final manifest and evidence after
  the GitHub Release became immutable. Retained as an incomplete historical record.
- **0.1.1 — hidden from the documentation website:** tagged release attempt;
  no final GitHub Release currently exists. Retained as a historical snapshot.

These inventory states control documentation publication intent. They do not
retract, delete, or modify packages, tags, or GitHub Releases. Only 0.1.3 should be
selected as latest stable documentation. Provider records link to publication runs
for context. Hidden versions remain available here for inspection.

## Maintenance

Use `tools/versioned-docs/` from the source checkout. Incremental import discovers
new stable tags; review publication state before committing a new inventory.
Both incremental import and full rebuild preserve curated records. Keep hidden or
withdrawn entries instead of deleting them, so imports do not rediscover them as
new releases. Full rebuild replaces selected docs with their tagged originals.

The website must consume this inventory and docs from the same branch commit.
Component-owned snapshot paths and optional local docs checkout behavior require
the corresponding Site Pipeline feature before website integration.
