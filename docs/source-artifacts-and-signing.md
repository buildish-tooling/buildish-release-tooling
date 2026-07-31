---
title: Source Artifacts And Signing
description: "Choose platform-generated source snapshots or build and sign an explicit source archive."
weight: 40
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

# Source Artifacts And Signing

Source publication is a component choice. The core lifecycle does not require a separately built
source archive.

## Platform-generated source snapshot

```yaml
source:
  selection: explicit-ref-or-default-branch
  default_branch: main
  snapshot:
    mode: platform-generated
  checks:
    run_selected_ref_tests: false
    require_release_branch_ci: true
artifacts:
  produced: []
  checksums: []
```

This mode relies on the hosting platform's snapshot of an immutable tag. Promotion records
`same-source-revision` evidence when candidate and final tags resolve to the same exact commit.

`mode: none` is also available when a release intentionally exposes no source snapshot.

## Built source archive

```yaml
source:
  selection: explicit-ref
  snapshot:
    mode: built-asset
    filename_template: "{component}-{version}-src.tar.gz"
    archive_root_template: "{component}-{version}"
  checks:
    run_selected_ref_tests: true
    require_release_branch_ci: false
artifacts:
  produced:
    - source-archive
  checksums:
    - sha256
    - sha512
```

The templates may use `{component}` and `{version}`. No foundation-specific suffix is added by the
core. A project that needs a special filename selects it explicitly in its own config.

Components with built artifacts add component-owned build and verification jobs to their workflow.
Same-run files should move through workflow artifacts with digest validation. Candidate promotion
downloads the durable candidate assets and requires byte-identical digest evidence before uploading
them to the final release.

## OpenPGP signing

Add signing under `artifacts`:

```yaml
artifacts:
  produced:
    - source-archive
  checksums:
    - sha512
  signing:
    kind: openpgp
    private_key_env: PROJECT_RELEASE_PRIVATE_KEY
    passphrase_env: PROJECT_RELEASE_KEY_PASSPHRASE
    expected_fingerprint: 0123456789ABCDEF0123456789ABCDEF01234567
    signature_format: detached-ascii-armored
```

The values of `private_key_env` and `passphrase_env` are environment-variable names, not secrets.
Map those variables to the component's GitHub secrets in the job that signs.

For an unprotected private key, omit `passphrase_env`:

```yaml
signing:
  kind: openpgp
  private_key_env: PROJECT_RELEASE_PRIVATE_KEY
  expected_fingerprint: 0123456789ABCDEF0123456789ABCDEF01234567
```

The signer imports exactly one primary secret key into an isolated temporary GnuPG home. When
configured, the full fingerprint must match. A protected-key passphrase is supplied through GnuPG
loopback input rather than command arguments. Signing subprocesses receive a constructed environment
with the configured key and passphrase variables removed, and errors are sanitized against secret
values.

`expected_fingerprint` is optional in the schema but recommended for a production signing identity.

## Responsibility boundary

The component remains responsible for:

- provisioning and rotating its signing key and optional passphrase;
- selecting GitHub Environment and secret access policy;
- ensuring only the intended signing job receives those values;
- publishing or otherwise establishing the public trust path for the signing key.

The CLI is responsible for isolated import, configured fingerprint enforcement, secret-safe signing
invocation, detached signature creation, and failure without replacing an existing valid signature
when signing does not complete.
