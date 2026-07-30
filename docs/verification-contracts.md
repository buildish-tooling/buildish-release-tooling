---
title: Verification Report and Bundle Contract
description: "Supported machine-readable contract for verify-rc reports, inspection bundles, and inspect-repro JSON output."
weight: 110
---

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

# Verification Report and Bundle Contract

This page defines the supported machine-readable contract for:

- `verify-rc` JSON reports
- curated `verify-rc` inspection bundles
- `inspect-repro --json` output

The current supported schema version for all three is `1`.

## Compatibility policy

- `schema_version: "1"` in `verify-rc` reports is a supported contract.
- `inspection_bundle.bundle_schema_version: "1"` plus the bundle manifest
  `inspection-bundle.json` is a supported contract.
- `schema_version: "1"` in `inspect-repro --json` output is a supported contract.
- Future incompatible changes must use a new explicit schema version rather than silently mutating
  the existing structure.
- `inspect-repro` remains backward-tolerant for older pre-contract reports that only recorded
  `inspection_bundle.relative_path_from_report`.

## `verify-rc` report JSON

Top-level required structure:

```json
{
  "schema_version": "1",
  "report_type": "verify-rc",
  "manifest_url": "...",
  "keys_url": "...",
  "verdict": "verified|failed|warning",
  "work_dir": "...",
  "manifest_verification": { "...": "..." },
  "source_artifact_verification": { "...": "..." },
  "reproducibility_execution": { "...": "..." },
  "secondary_artifact_verifications": []
}
```

Top-level fields currently emitted:

- `schema_version`
- `report_type`
- `component_id`
- `version`
- `rc_tag`
- `source_commit_sha`
- `source_date_epoch`
- `source_repository_url`
- `manifest_url`
- `keys_url`
- `verdict`
- `work_dir`
- `failures`
- `manifest_verification`
- `source_artifact_verification`
- `reproducibility_execution`
- `inspection_bundle`
- `secondary_artifact_verifications`

Important nested structures:

- `manifest_verification` records manifest checksum, signature, KEYS, and trust-root results.
- `source_artifact_verification` records staged source-artifact verification and, when attempted,
  structured source reproducibility details.
- `secondary_artifact_verifications` contains one typed verification record per declared secondary
  artifact.
- `reproducibility_execution` records whether build-based checks were attempted and how they were
  executed.
- `inspection_bundle` records the bundle directory relative to the report plus the supported bundle
  schema version and manifest path.

### Structured reproducibility report shape

When local reproducibility checks are attempted, the supported reproducibility contract is:

- `canonical_recipe`
- `effective_execution`
- `override`

Those sections are emitted for secondary artifacts and, where applicable, for source-artifact
reproducibility.

Environment reporting intentionally records variable names only, never values. The supported fields
are:

- `canonical_recipe.build.env_keys`
- `effective_execution.build.injected_environment_keys`
- `override.build.env_keys`

That contract is deliberate so reports and bundles do not leak secrets or machine-local
credentials.

### Current comparison-mode matrix

Schema version `1` currently supports this reproducibility comparison-mode matrix:

- `source-artifact`: `exact-bytes`
- `generic-file`: `exact-bytes`
- `generic-file-with-openpgp`: `exact-bytes`
- `python-distribution`: `exact-bytes`
- `npm-package`: `exact-bytes`
- `maven-repository`: `repository-tree`
- `oci-image`: `platform-digest` or `provenance-only`

That matrix is part of the current contract. New modes or incompatible remapping of existing
artifact kinds to different modes require an explicit schema or configuration-contract change, not
silent expansion.

## Inspection bundle

When `verify-rc` attempts reproducibility checks, it may emit a curated inspection bundle next to
the report.

The report points to that bundle through:

```json
{
  "inspection_bundle": {
    "relative_path_from_report": "...",
    "bundle_schema_version": "1",
    "manifest_relative_path": "inspection-bundle.json"
  }
}
```

The bundle manifest shape is:

```json
{
  "schema_version": "1",
  "bundle_type": "verify-rc-inspection",
  "report_type": "verify-rc",
  "report_schema_version": "1",
  "component_id": "...",
  "version": "...",
  "rc_tag": "...",
  "artifacts": [
    {
      "artifact_id": "...",
      "kind": "...",
      "metadata_path": "..."
    }
  ]
}
```

Bundle semantics:

- paths recorded in the report are relative to the bundle root so the bundle remains relocatable
- each `artifacts[*].metadata_path` points to one typed per-artifact metadata document
- retained evidence files are referenced from those metadata documents, not discovered implicitly

## `inspect-repro --json`

`inspect-repro --json` emits its own supported machine-readable payload:

```json
{
  "schema_version": "1",
  "report_type": "inspect-repro",
  "verify_rc_report_schema_version": "1",
  "bundle_schema_version": "1",
  "verify_rc_verdict": "verified|failed|warning",
  "build_checks_attempted": true,
  "report_json_path": "...",
  "inspection_bundle_path": "...",
  "summary": { "...": "..." },
  "targets": []
}
```

Top-level fields currently emitted:

- `schema_version`
- `report_type`
- `verify_rc_report_schema_version`
- `bundle_schema_version`
- `component_id`
- `rc_tag`
- `verify_rc_verdict`
- `build_checks_attempted`
- `report_json_path`
- `inspection_bundle_path`
- `selected_artifact_ids`
- `selected_failure_classes`
- `summary_only`
- `summary`
- `targets`

The `summary` block contains grouped counts for:

- total reproducibility failures
- source-artifact failures
- secondary-artifact failures
- failure kinds
- failure classes
- failure groups

Each `targets[*]` entry identifies one selected reproducibility failure with:

- `artifact_id`
- `kind`
- `failure_class`
- `failure_group`
- `profile_id`
- `comparison_mode`
- `recipe_source`
- `execution_backend`
- `build_command`
- `build_working_directory`
- `injected_environment_keys`
- `evidence_labels`
- `evidence`
- `override_fields`

Human `inspect-repro` transcript behavior in schema version `1` also supports:

- `--artifact-id <id>` target filtering
- `--failure-class <class>` failure-class filtering
- `--summary-only` grouped-summary mode
- `--compact` grouped-summary plus compact per-target headers without deep analyzer output

## Artifact-kind stability rules

New artifact kinds may extend:

- `secondary_artifact_verifications[*].kind`
- bundle `artifacts[*].kind`
- typed per-kind verification and metadata records

They must not silently change:

- top-level report or bundle schema version semantics
- existing field meanings
- the structured reproducibility sections

If a new artifact kind needs incompatible report or bundle layout changes, that requires a new
schema version.
