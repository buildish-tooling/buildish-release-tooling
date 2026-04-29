---
title: "Verify RC Implementation Plan"
description: "Design proposal for a read-only verifier driven by the signed RC vote manifest."
---

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

# Verify RC Implementation Plan

## Summary

This document proposes a concrete design for `verify-rc`.

The main recommendations are:

- make the signed `rc-vote-manifest.json` the authoritative inventory for what must be verified
- switch the public `verify-rc` command from `version`-based input to `rc-vote-manifest` URL input
- keep the verifier non-publishing and non-Git-mutating: it may download artifacts, build locally, and write reports to a temp/work directory, but it must not push, tag, publish, or mutate Git state
- default to `integrity-only`; treat `full` as explicit untrusted-code execution with isolation requirements
- require the KEYS URL as an explicit verifier input; only use manifest or local config KEYS URLs as cross-check material
- separate required authenticity and integrity checks from optional or project-graded reproducibility checks
- support common secondary artifact families with built-in typed verifiers, and use project-local build recipes only as a controlled extension point
- do not execute shell commands from the remote manifest; project-specific commands must come from local project config

Related planning:

- [ATR Integration Assessment](atr-integration-assessment.md)

## Current Status

Implemented already:

- the release-side typed `record-artifact` contract
- merge of typed secondary-artifact fragments into `finalize-rc-vote-materials`
- built-in release-side registration kinds for `generic-file`, `maven-repository`, `python-distribution`, `oci-image`, and `npm-package`

Still remaining:

- the verifier-side `verify-rc` engine itself
- generic secondary-artifact verification
- ecosystem-specific verifier support for Maven, Python, OCI, and npm
- bootstrap UX and a stronger long-term verifier bootstrap story

This document now tracks that remaining verifier-side work.

## Goals

- run in GitHub Actions with `contents: read` permissions only
- run on Linux and macOS developer machines
- work for Buildish projects and also for arbitrary ASF projects that adopt the manifest and config contract
- verify the main source artifact for authenticity and integrity
- verify secondary artifacts listed in the RC vote-manifest for authenticity and integrity
- support local rebuild and comparison where projects are ready for it
- degrade gracefully when exact bit-for-bit reproducibility is not yet achievable

## Non-Goals

- replacing human release review with a fully automatic vote
- making every ecosystem perfectly reproducible in the first implementation
- inventing a single universal verification method for all secondary artifact ecosystems
- executing arbitrary instructions from a remote manifest URL

## Key Design Decisions

### 1. The public input should be the RC vote-manifest URL

The public command should move from:

```text
buildish-release-tooling verify-rc <version>
```

to:

```text
buildish-release-tooling verify-rc <rc-vote-manifest-url> <keys-url>
```

Reasons:

- `version` is not enough to identify the exact RC state to verify
- the signed manifest already names the source artifact, checksums, signatures, provenance, and secondary artifacts
- the command becomes more generic across ASF projects and staging layouts

The current GitHub workflow should therefore also move from a `version` input to an `rc_vote_manifest_url` input.

### 2. KEYS must be an explicit verifier argument

The user concern about KEYS bootstrap is valid.

If the verifier learns the KEYS URL only from an unverified manifest, that is not a secure bootstrap. A tampered manifest could point to an attacker-controlled KEYS file and carry a matching attacker signature.

The same caution also applies to a potentially tampered local checkout. A KEYS URL learned only from `release-config.yaml` is useful as a consistency signal, but not as the bootstrap root of trust.

Recommended steady state:

- add `asf_keys_url` to `release-config.yaml`
- include that same explicit URL in the signed manifest for traceability
- require the caller to pass the KEYS URL explicitly to `verify-rc`
- if local config is present, require it to match the CLI KEYS URL
- require the signed manifest KEYS URL to match the CLI KEYS URL too

This gives the best balance:

- the bootstrap trust root is explicit and visible to the verifier
- the manifest remains descriptive, but not authoritative for trust bootstrap
- local config remains useful for cross-checking and project documentation

So the safer public contract is:

```text
buildish-release-tooling verify-rc <rc-vote-manifest-url> <keys-url>
```

### 3. Required verification and reproducibility should be separate concepts

The verifier should produce two verdict classes.

Required:

- the manifest is authentic and intact
- the source artifact is authentic and intact
- the manifest's declared `rc_tag` resolves to the same Git commit as the declared `source_commit_sha`
- each declared secondary artifact is authentic and intact according to its artifact kind

Advisory or project-graded:

- exact bit-for-bit reproducibility
- canonical content reproducibility
- provenance-only rebuild evidence when byte-identical output is not yet realistic

This is important for real-world ASF projects. Otherwise `verify-rc` will either be too weak to matter or too strict to adopt.

## Trust Model

The recommended trust chain is:

1. Obtain the manifest URL out of band.
2. Obtain the KEYS URL out of band and pass it explicitly to the verifier.
3. Download:
   - `rc-vote-manifest.json`
   - `rc-vote-manifest.json.sha512`
   - `rc-vote-manifest.json.asc`
   - `KEYS`
4. Verify:
   - the manifest checksum sidecar matches the manifest bytes
   - the manifest detached signature verifies against the KEYS file
   - the KEYS URL declared in the signed manifest matches the CLI KEYS URL
   - the manifest carries an explicit `rc_tag`
   - the manifest `rc_tag` resolves to the same Git commit as the manifest `source_commit_sha`
   - when a local project checkout is present, `release-config.yaml` matches the CLI KEYS URL too
5. Parse the now-trusted manifest.
6. Verify the source artifact.
7. Verify all secondary artifacts.
8. Optionally rebuild and compare artifacts locally.

Important security rule:

- the remote manifest is data, not instructions

That means:

- it may declare artifact identities, digests, signatures, provenance, and artifact kinds
- it must not carry shell commands that the verifier executes

If project-specific build commands are needed, they must come from local, version-controlled project config.

## Security Assessment

This section records the residual security concerns.

### Open Issue. The bootstrap trust chain is still too weak

Phase 1b may keep the commit-pinned bootstrap path as an explicitly accepted risk, but it should not be treated as the long-term secure end state.

The current bootstrap example verifies the manifest, extracts a tooling commit SHA from it, and then clones `buildish-release-tooling` from GitHub at that commit. That is better than following a floating branch, but it is still too weak to serve as the main executable trust anchor.

The core concern is authorization, not just transport integrity:

- a project signing key compromise would let an attacker sign a bootstrap script that executes arbitrary shell before the typed verifier logic runs
- a bare GitHub clone plus commit SHA does not give a strong, durable verification story for the verifier itself
- the plan does not yet require a separately signed verifier artifact, signed source snapshot, or digest-pinned tooling bundle

Recommended direction:

- keep the phase-1 bootstrap path only as an explicitly documented temporary risk
- solve this early by shipping a verifier distribution whose exact bytes are authenticated independently of the project RC, for example a signed tooling source snapshot or verifier artifact with a digest recorded in the signed manifest
- if Git remains in the trust path, bind to more than a repository URL plus commit SHA and define how the verifier's own authenticity is checked
- treat the manual, non-executing verification path as the normative baseline, with the bootstrap script treated as convenience only

## Proposed CLI Contract

Recommended public CLI:

```text
buildish-release-tooling verify-rc <rc-vote-manifest-url> <keys-url>
```

Companion inspection CLI:

```text
buildish-release-tooling inspect-repro <report-json>
```

Recommended optional flags:

- `--work-dir <path>`: keep downloads, local builds, and reports in a caller-chosen directory
- `--report-json <path>`: write machine-readable verification report; when omitted, auto-name it as `verify-rc-report-<component_id>-<version>-<rc_id>-<timestamp>.json`
- `--report-md <path>`: write human-readable verification report; when omitted, auto-name it from the same base identifier as the JSON report
- `--mode <integrity-only|full|auto>`: remote verification only, always run local reproducibility checks, or prompt locally after remote checks pass
- `--build-network <offline|online|prompt>`: choose rebuild network policy explicitly or ask interactively on local TTYs
- `--keep-work-dir`: keep the verifier work directory after completion
- `--no-keep-work-dir`: purge an auto-created work directory after completion
- `--inspection-bundle <path>`: write a curated reproducibility-inspection bundle alongside the main report
- `--max-download-bytes <n>`: override the default total download budget
- `--max-artifacts <n>`: override the default artifact-count budget
- `--max-expanded-bytes <n>`: override the default archive expansion budget
- `--timeout-seconds <n>`: override the default subprocess timeout budget

Security recommendation:

- use `auto` as the interactive local default so remote checks complete before prompting about candidate-code execution
- default non-interactive or CI runs to `integrity-only`
- reserve explicit `full` for callers that want no prompt before candidate-code execution

I would keep the public contract minimal and avoid adding many user-facing flags in the first implementation.

The command must work without write-capable GitHub permissions. It should not require a token for normal public ASF artifacts.

## Rebuild Execution Safety Model

`integrity-only` should remain the safe non-interactive default. On ordinary developer machines with an interactive TTY, the default UX should be `auto`: complete remote authenticity and integrity checks first, then prompt before any candidate build code is executed.

`full` is different in kind, not just in runtime:

- it executes candidate-controlled build code
- it may invoke transitive build plugins and package-manager tooling
- it must therefore be treated as untrusted-code execution

Required design rules for `full` mode:

- run rebuilds from a temp work directory, not from the user's normal working tree
- source the rebuild input from the verified source artifact or from a temp copy derived from trusted local project material
- start build subprocesses from a scrubbed environment allowlist
- set `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `GNUPGHOME`, and `TMPDIR` to temp locations under the verifier work directory
- do not forward ambient credentials or agents such as `SSH_AUTH_SOCK`, Git credential helpers, cloud credentials, `~/.m2/settings.xml`, `~/.npmrc`, or custom package-index tokens
- complete manifest, source-artifact, and remote secondary-artifact verification before any local rebuild step
- require an explicit rebuild network policy of `offline`, `online`, or interactive `prompt`
- if the caller chooses `offline`, disable network access for rebuild execution and fail rather than silently relaxing that policy
- if the caller chooses `online`, record that decision in the verification report because it is a security-relevant allowance

Interactive local behavior:

- if `--mode auto` is in effect on an interactive TTY, prompt after remote checks pass and before any untrusted-code execution begins
- if the user agrees to continue and no explicit `--build-network` policy was supplied, ask whether rebuild should be `offline-only` or `network-allowed`
- if the selected project-local rebuild recipe requires network access and the user chose `offline-only`, fail clearly instead of silently switching to `network-allowed`

Deployment guidance:

- on shared CI, `full` should run only inside a dedicated container or ephemeral VM with no injected secrets
- a GitHub-hosted ephemeral runner may serve as that isolation boundary when the workflow uses only minimal read permissions, injects no secrets, and does not rely on persistent shared state
- on developer machines, `full` should be treated as a disposable-environment workflow, not the default host workflow

Reporting requirement:

- the verification report should record whether rebuild execution was offline or online
- the report should record whether any explicit unsafe allowances were used
- the report should record whether execution and network-policy decisions were made via explicit flags or interactive confirmation

Inspection boundary:

- `verify-rc` should stop at verdicts, evidence capture, and report generation
- deeper diagnosis of reproducibility mismatches should live in the separate `inspect-repro` command
- `inspect-repro` should be strictly read-only and should analyze saved artifacts and metadata without executing candidate code

## Operational Budgets

The verifier should enforce sane default operational budgets that work for most ASF release candidates, while still allowing unusually large legitimate candidates to be verified with explicit operator overrides.

Budget policy:

- defaults should come from verifier policy, not from the remote manifest
- CLI overrides should exist for local operators and CI maintainers
- the report should record both the effective budget values and any overrides used

Suggested first-phase budgets:

- maximum manifest bytes
- maximum detached inventory bytes
- maximum artifact count
- maximum total download bytes
- maximum expanded bytes for archive normalization or comparison
- maximum subprocess runtime per verification step
- maximum parallel fetch count

Failure behavior:

- if a budget is exceeded, fail with an actionable message that names the exceeded budget and the override knob
- do not auto-relax limits based on manifest content

## Bootstrapping UX

The verifier should not require users to understand `uv`, create a `venv`, or install the repo as a Python package.

The first practical UX should therefore be a signed bootstrap script, not a Python packaging workflow.

Recommended shape:

- RC preparation generates a small `verify-rc-bootstrap.sh`
- the script is staged in ASF `dist/dev` and mirrored to the draft GitHub Release
- the script is a verification convenience artifact, not part of the final released payload
- the script has a detached signature and checksum sidecar
- the vote email and draft release description carry an inspectable one-liner that:
  - downloads the bootstrap script and its sidecars
  - verifies checksum and signature against the explicit KEYS URL
  - only then executes the script

Design constraints for the bootstrap script:

- keep it small and auditable
- keep it generic enough that experienced developers can review it once and recognize future instances
- have it pass the explicit manifest URL and explicit KEYS URL into the actual verifier
- allow it to clone `buildish-release-tooling` at the fixed tooling commit recorded in trusted manifest provenance, or download that exact source snapshot
- never skip signature verification before execution
- preflight the minimum supported `python3` version and fail early with a clear message if the local interpreter is too old

This is not cryptographically stronger than GPG verification itself. It is a UX layer around the same trust model. The benefit is that users do not have to perform the individual GPG steps manually.

A future self-contained verifier artifact may still be useful, but it is not required for the first usable design.

### Example Invoker One-Liner

The example below is written for POSIX `sh`, not for Bash-specific syntax. That means it should also work under `dash`, assuming `curl`, `python3`, `gpg`, `awk`, and `mktemp` are present.

```sh
/bin/sh -eu -c '
manifest_url=$1
keys_url=$2
bootstrap_base_url=${manifest_url%/*}
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/verify-rc.XXXXXX")
cleanup() { rm -rf "$temp_dir"; }
trap cleanup EXIT HUP INT TERM
cd "$temp_dir"

curl -fsSLO "$bootstrap_base_url/verify-rc-bootstrap.sh"
curl -fsSLO "$bootstrap_base_url/verify-rc-bootstrap.sh.sha512"
curl -fsSLO "$bootstrap_base_url/verify-rc-bootstrap.sh.asc"
curl -fsSL "$keys_url" -o KEYS

if command -v sha512sum >/dev/null 2>&1; then
  sha512sum -c verify-rc-bootstrap.sh.sha512
else
  shasum -a 512 -c verify-rc-bootstrap.sh.sha512
fi

GNUPGHOME=$temp_dir/gnupg
export GNUPGHOME
mkdir "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
gpg --batch --quiet --import KEYS >/dev/null 2>&1
gpg --batch --quiet --verify verify-rc-bootstrap.sh.asc verify-rc-bootstrap.sh >/dev/null 2>&1

chmod +x verify-rc-bootstrap.sh
exec ./verify-rc-bootstrap.sh "$manifest_url" "$keys_url"
' sh "$RC_VOTE_MANIFEST_URL" "$KEYS_URL"
```

Notes:

- the invoker is intentionally small enough to be inspectable in an RC vote email or draft release description
- it verifies both the SHA-512 sidecar and the detached OpenPGP signature before execution
- it expects the bootstrapper and its sidecars to live next to the RC vote-manifest
- it uses `sha512sum -c` on Linux and `shasum -a 512 -c` on macOS against the downloaded checksum file

### Example `verify-rc-bootstrap.sh`

The bootstrap script below is still only an example, but it illustrates the intended contract:

- verify the signed manifest first
- cross-check the manifest KEYS URL against the caller-provided KEYS URL
- resolve the pinned `buildish-release-tooling` commit from trusted manifest provenance
- run the verifier from that exact tooling commit

```sh
#!/bin/sh
set -eu

usage() {
  printf 'usage: %s <rc-vote-manifest-url> <keys-url> [verify-rc args...]\n' "$0" >&2
  exit 2
}

[ "$#" -ge 2 ] || usage

manifest_url=$1
keys_url=$2
shift 2

for tool in curl git gpg mktemp; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'missing required tool: %s\n' "$tool" >&2
    exit 1
  }
done

select_python() {
  for candidate in python3.15 python3.14 python3.13 python3.12 python3.11 python3 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf 'python >= 3.11 required; tried python3.15, python3.14, python3.13, python3.12, python3.11, python3, python\n' >&2
  return 1
}

python_bin=$(select_python)

TOOLING_REPO_URL=https://github.com/apache/buildish-release-tooling

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/verify-rc-bootstrap.XXXXXX")
cleanup() { rm -rf "$work_dir"; }
trap cleanup EXIT HUP INT TERM
cd "$work_dir"

curl -fsSL "$manifest_url" -o rc-vote-manifest.json
curl -fsSL "$manifest_url.sha512" -o rc-vote-manifest.json.sha512
curl -fsSL "$manifest_url.asc" -o rc-vote-manifest.json.asc
curl -fsSL "$keys_url" -o KEYS

if command -v sha512sum >/dev/null 2>&1; then
  sha512sum -c rc-vote-manifest.json.sha512
else
  shasum -a 512 -c rc-vote-manifest.json.sha512
fi

GNUPGHOME=$work_dir/gnupg
export GNUPGHOME
mkdir "$GNUPGHOME"
chmod 700 "$GNUPGHOME"
gpg --batch --quiet --import KEYS >/dev/null 2>&1
gpg --batch --quiet --verify rc-vote-manifest.json.asc rc-vote-manifest.json >/dev/null 2>&1

tooling_commit=$(
  "$python_bin" - rc-vote-manifest.json "$keys_url" "$TOOLING_REPO_URL" <<'PY'
import json
import sys
from pathlib import Path

manifest_path, expected_keys_url, expected_tooling_repo = sys.argv[1:4]
data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

manifest_keys_url = data["trust_roots"]["asf_keys"]["uri"]
if manifest_keys_url != expected_keys_url:
    raise SystemExit(
        f"manifest KEYS URL mismatch: {manifest_keys_url!r} != {expected_keys_url!r}"
    )

tooling = data["provenance"]["tooling"]
repo_url = tooling.get("repository_url")
if repo_url and repo_url != expected_tooling_repo:
    raise SystemExit(
        f"unexpected tooling repository: {repo_url!r} != {expected_tooling_repo!r}"
    )

print(tooling["git_commit_sha"])
PY
)

tooling_dir=$work_dir/buildish-release-tooling
git clone --quiet "$TOOLING_REPO_URL" "$tooling_dir"
git -C "$tooling_dir" checkout --quiet --detach "$tooling_commit"

PYTHONPATH=$tooling_dir/src
export PYTHONPATH
exec "$python_bin" -m apache_buildish_release_tooling.verification \
  "$manifest_url" "$keys_url" "$@"
```

This example intentionally keeps the bootstrap logic outside the manifest itself. The manifest stays data-only; the bootstrapper is the reviewed, versioned execution layer.

## Proposed Config Changes

Add this field to `release-config.yaml`:

```yaml
asf_keys_url: https://downloads.apache.org/.../KEYS
```

This field is a required cross-check and documentation point. It must not replace the explicit KEYS URL argument used for verifier bootstrap.

Add a structured verification section for local rebuild recipes and artifact-family policies:

```yaml
verify_rc:
  source:
    build:
      command: ["./mvnw", "-Prelease", "package"]
      output_glob: "target/apache-example-*.tar.gz"
      network: offline-required
    reproducibility:
      mode: exact-bytes

  secondary_profiles:
    maven-staging:
      kind: maven-repository
      build:
        command:
          ["./mvnw", "-Prelease", "deploy", "-DaltDeploymentRepository=local::default::file:${WORK_DIR}/m2repo"]
        repository_dir: "${WORK_DIR}/m2repo"
        network: offline-required
      comparison:
        mode: repository-tree
        require_signatures: true

    pypi-wheel:
      kind: python-distribution
      build:
        command: ["python", "-m", "build"]
        output_glob: "dist/*"
      comparison:
        mode: exact-bytes
```

The exact schema can evolve, but the key design point is:

- project-specific commands live in local config
- the remote manifest only references typed artifacts and typed verification expectations

## Proposed Manifest Changes

The current manifest shape is already close to usable. I would evolve it rather than replace it.

Recommended additions:

- keep `trust_roots.asf_keys.uri`, but source it from explicit config instead of deriving it from release base URLs
- add typed `kind` fields to secondary artifacts
- add stable `artifact_id` fields so multiple artifacts of the same `kind` are unambiguous
- add `expected_signer_fingerprints` for source artifacts and signed secondary artifacts when a release wants to pin one signer or one signer set
- add `inventory` subdocuments for large or mutable artifact collections such as Maven repositories or image sets
- add optional `reproducibility` expectations per artifact or artifact collection

Hard requirements:

- every source artifact entry must include a checksum
- every source artifact entry must include a detached signature

For small artifacts, inline entries are fine:

```json
{
  "artifact_id": "wheel-linux",
  "kind": "python-distribution",
  "role": "wheel",
  "filename": "example-1.2.3-py3-none-any.whl",
  "uri": "https://test.pypi.org/...",
  "checksums": {
    "sha256": {
      "value": "..."
    }
  },
  "authenticity": {
    "scheme": "pypi-attestation",
    "repository": "apache/example"
  }
}
```

For large collections, the main manifest may reference a typed inventory file whose digest is embedded in the signed main manifest:

```json
{
  "kind": "maven-repository",
  "uri": "https://repository.apache.org/content/repositories/orgapacheexample-1234/",
  "inventory": {
    "uri": "https://.../maven-repository-inventory.json",
    "sha512": "..."
  }
}
```

This keeps the main signed manifest authoritative without forcing it to inline thousands of repository entries. For mutable or large remote collections such as staged Maven repositories, the inventory should be treated as the stable verification snapshot, not as an optional convenience.

## Secondary Artifact Registration Contract

The current design needs an explicit contract for how RC preparation workflows tell release-tooling about staged secondary artifacts.

That contract is now implemented in the `release` CLI through one public `record-artifact` command.

The current built-in registration kinds are:

- `generic-file`
- `maven-repository`
- `python-distribution`
- `oci-image`
- `npm-package`

The remaining work described elsewhere in this document is verifier-side `verify-rc` support for these kinds and future extensions such as `generic-file-with-openpgp`.

The verifier-relevant handoff contract is:

- each producer job should run `record-artifact` after staging its secondary artifact
- each producer job should write a small artifact-registration bundle to disk
- that bundle should contain the typed JSON fragment and any detached inventory files produced for that artifact kind
- `record-artifact` should print the fragment path and append `artifact_manifest_path` plus `artifact_bundle_dir` to `GITHUB_OUTPUT` so the current job can hand those paths to upload steps without extra path guessing
- producer jobs should upload those bundles as workflow artifacts
- the final `finalize-rc-vote-materials` job should download all artifact-registration bundles and pass their manifest fragment paths via `--secondary-artifact-manifests ...`
- use GitHub step or job outputs only for small scalar coordination data such as artifact bundle names, counts, or boolean presence flags, not for the manifest fragments themselves

Example GitHub workflow steps for all currently implemented kinds:

These examples are intentionally in one place. A real project would usually use only the subset that matches its release shape.

The `generic-file`, `python-distribution`, and `npm-package` examples assume the artifact bytes already exist locally. The `maven-repository` example assumes the Nexus staging repository already exists. The `oci-image` example assumes the image has already been pushed and can be inspected remotely.

These steps can live in one producer job or be split across several producer jobs. The handoff pattern into finalization stays the same either way.

TODO: add a `--prepare-rc-manifest <path>` input here so producer steps that already have recorded RC state can default source-linked fields such as `--git-commit-sha` without guessing from local `HEAD`.

```yaml
steps:
  - id: record_bootstrap_zip
    name: Record bootstrap asset (generic-file)
    env:
      RC_TAG: ${{ needs.prepare-rc.outputs.rc_tag }}
      SOURCE_SHA: ${{ needs.prepare-rc.outputs.resolved_source_ref }}
    run: |
      buildish-release-tooling record-artifact \
        --component-config buildish-release-tooling/release-config.yaml \
        --kind generic-file \
        --artifact-id bootstrap-zip \
        --role bootstrap-convenience-archive \
        --file dist/buildish-example-bootstrap.zip \
        --uri "https://github.com/apache/buildish-example/releases/download/${RC_TAG}/buildish-example-bootstrap.zip" \
        --sha512-uri "https://github.com/apache/buildish-example/releases/download/${RC_TAG}/buildish-example-bootstrap.zip.sha512" \
        --git-commit-sha "${SOURCE_SHA}"

  - name: Upload bootstrap registration bundle
    uses: actions/upload-artifact@v4
    with:
      name: secondary-artifact-bootstrap-zip
      path: ${{ steps.record_bootstrap_zip.outputs.artifact_bundle_dir }}
      if-no-files-found: error

  - id: record_maven_staging
    name: Record Maven staging repository (maven-repository)
    env:
      NEXUS_REPOSITORY_ID: ${{ steps.publish_nexus.outputs.staging_repository_id }}
    run: |
      buildish-release-tooling record-artifact \
        --component-config buildish-release-tooling/release-config.yaml \
        --kind maven-repository \
        --artifact-id maven-staging-main \
        --role maven-staging \
        --staging-repository-id "${NEXUS_REPOSITORY_ID}"

  - name: Upload Maven registration bundle
    uses: actions/upload-artifact@v4
    with:
      name: secondary-artifact-maven-staging-main
      path: ${{ steps.record_maven_staging.outputs.artifact_bundle_dir }}
      if-no-files-found: error

  - id: record_pypi_wheel
    name: Record Python wheel (python-distribution)
    env:
      VERSION: ${{ needs.prepare-rc.outputs.version }}
      SOURCE_SHA: ${{ needs.prepare-rc.outputs.resolved_source_ref }}
    run: |
      buildish-release-tooling record-artifact \
        --component-config buildish-release-tooling/release-config.yaml \
        --kind python-distribution \
        --artifact-id pypi-wheel \
        --role wheel \
        --file "dist/buildish_example-${VERSION}-py3-none-any.whl" \
        --uri "https://test.pypi.org/packages/buildish_example-${VERSION}-py3-none-any.whl" \
        --index-url "https://test.pypi.org/simple/" \
        --package-name buildish-example \
        --package-version "${VERSION}" \
        --sha256-uri "https://test.pypi.org/packages/buildish_example-${VERSION}-py3-none-any.whl.sha256" \
        --attestation-repository "apache/buildish-example" \
        --git-commit-sha "${SOURCE_SHA}"

  - name: Upload Python registration bundle
    uses: actions/upload-artifact@v4
    with:
      name: secondary-artifact-pypi-wheel
      path: ${{ steps.record_pypi_wheel.outputs.artifact_bundle_dir }}
      if-no-files-found: error

  - id: record_oci_image
    name: Record container image (oci-image)
    env:
      RC_TAG: ${{ needs.prepare-rc.outputs.rc_tag }}
      SOURCE_SHA: ${{ needs.prepare-rc.outputs.resolved_source_ref }}
    run: |
      buildish-release-tooling record-artifact \
        --component-config buildish-release-tooling/release-config.yaml \
        --kind oci-image \
        --artifact-id ghcr-main-image \
        --role container-image \
        --image-ref "ghcr.io/apache/buildish-example:${RC_TAG}" \
        --git-commit-sha "${SOURCE_SHA}"

  - name: Upload OCI registration bundle
    uses: actions/upload-artifact@v4
    with:
      name: secondary-artifact-ghcr-main-image
      path: ${{ steps.record_oci_image.outputs.artifact_bundle_dir }}
      if-no-files-found: error

  - id: record_npm_package
    name: Record npm package (npm-package)
    env:
      VERSION: ${{ needs.prepare-rc.outputs.version }}
      SOURCE_SHA: ${{ needs.prepare-rc.outputs.resolved_source_ref }}
    run: |
      buildish-release-tooling record-artifact \
        --component-config buildish-release-tooling/release-config.yaml \
        --kind npm-package \
        --artifact-id npm-package-main \
        --role npm-package \
        --file "dist/apache-buildish-example-${VERSION}.tgz" \
        --registry-url "https://registry.npmjs.org/" \
        --package-name "@apache/buildish-example" \
        --package-version "${VERSION}" \
        --attestation-repository "apache/buildish-example" \
        --git-commit-sha "${SOURCE_SHA}"

  - name: Upload npm registration bundle
    uses: actions/upload-artifact@v4
    with:
      name: secondary-artifact-npm-package-main
      path: ${{ steps.record_npm_package.outputs.artifact_bundle_dir }}
      if-no-files-found: error
```

Example finalization job:

The `needs` list here is illustrative. In a real workflow, include whichever producer jobs emitted `secondary-artifact-*` bundles.

```yaml
jobs:
  finalize-rc-vote-materials:
    runs-on: ubuntu-latest
    needs:
      - prepare-rc
      - record-secondary-artifacts
      - build-source-rc
      - create-rc-tag
      - sync-draft-github-release
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Download artifact-registration bundles
        uses: actions/download-artifact@v4
        with:
          pattern: secondary-artifact-*
          path: build/secondary-artifact-bundles
          merge-multiple: false

      - name: Finalize RC vote materials
        env:
          RC_TAG: ${{ needs.prepare-rc.outputs.rc_tag }}
          VERSION: ${{ needs.prepare-rc.outputs.version }}
        run: |
          mapfile -t manifests < <(
            find build/secondary-artifact-bundles -name artifact-manifest.json -print | sort
          )
          manifest_args=()
          for manifest in "${manifests[@]}"; do
            manifest_args+=(--secondary-artifact-manifest "$manifest")
          done

          buildish-release-tooling finalize-rc-vote-materials \
            --component-config buildish-release-tooling/release-config.yaml \
            "${manifest_args[@]}" \
            --rc-tag "${RC_TAG}" \
            "${VERSION}"
```

This is a better fit than step outputs because the handoff may need to carry multiple JSON files and detached inventories across several jobs before finalization.

At verifier time, the important contract is the typed fragment shape that ends up in the signed `rc-vote-manifest`, not the exact release-side CLI flags used to produce it.

For Nexus specifically, the fragment must carry the staging repository ID and base URL, for example:

```json
{
  "secondary_artifacts": [
    {
      "artifact_id": "maven-staging-main",
      "kind": "maven-repository",
      "role": "maven-staging",
      "staging_repository_id": "orgapacheexample-1234",
      "base_url": "https://repository.apache.org/content/repositories/orgapacheexample-1234/"
    }
  ]
}
```

The same pattern applies to the other currently implemented ecosystems:

- OCI: registry, repository, digest, optional platform digests
- npm: registry URL, package name, version, integrity, and optional provenance repository
- PyPI or TestPyPI: index URL, project name, version, filenames, and optional attestation repository

For a Nexus staging repository, the `maven-repository` kind handler should also enumerate the staged repository, write an inventory of paths and digests, and have the signed main manifest bind to that inventory digest. `verify-rc` should fetch the inventory, verify that its digest matches the main manifest, and then verify the live repository contents against that fixed snapshot.

This keeps RC preparation and RC verification connected by a typed, reviewable contract instead of ad hoc free-form notes.

## Verification Pipeline

### Phase A. Verify the signed RC vote-manifest

Required behavior:

- fetch manifest and sidecars over `https://` by default
- allow `file://` or plain `http://` only in explicit test mode for harness scenarios
- in production mode, restrict manifest, KEYS, bootstrap, and source-artifact origins to an allowlist of expected hosts
- in production mode, apply artifact-family origin allowlists with sane defaults:
  - ASF dist/SVN and GitHub release or mirror hosts for manifest, bootstrap, KEYS, and source-artifact inputs
  - `repository.apache.org` for Maven staging repositories
  - `pypi.org`, `test.pypi.org`, and `files.pythonhosted.org` for Python distribution verification
  - `registry.npmjs.org` for npm package verification
  - explicit public OCI registry hosts allowed by verifier policy for OCI verification
- treat redirects as part of origin policy and fail if the final target escapes the allowlist
- verify manifest checksum sidecar
- verify manifest signature against KEYS using an isolated ephemeral keyring
- fail closed on any mismatch

Implementation note:

- prefer `gpgv` with a temporary keyring when available
- otherwise use `gpg --homedir <tempdir>` to avoid touching user state

### Phase B. Verify the main source artifact

Required checks:

- download the staged source artifact
- recompute the declared digest
- compare the digest to the value embedded in the signed manifest
- if a checksum sidecar exists, verify it matches the recomputed digest too
- verify the detached signature against the KEYS file
- require the manifest to carry an explicit `rc_tag`
- verify that the manifest `rc_tag` resolves to the same Git commit as `source_commit_sha`
- verify that the staged source artifact matches the declared `source_commit_sha`
- if `expected_signer_fingerprints` is declared, require the source artifact signature to resolve to one of those fingerprints

Optional local rebuild:

- run the project-local source build recipe
- compare the locally built source archive to the staged source archive

Recommended default:

- exact byte match should be required for the main ASF source release artifact

That is the strongest and most portable artifact to make reproducible.

### Phase C. Verify secondary artifacts remotely

Each secondary artifact kind should define:

- how the remote artifact is located
- what the integrity proof is
- what the authenticity proof is
- whether the artifact is individually listed or part of a collection inventory

This phase should not require local rebuild yet. It should establish:

- the remote artifact bytes or registry object match the signed manifest
- the ecosystem-specific authenticity mechanism is valid
- when a collection inventory is present, the live remote state matches that fixed inventory
- when `expected_signer_fingerprints` is declared, signed artifacts in that family match the declared signer set

### Phase D. Rebuild and compare secondary artifacts locally

This phase is project- and artifact-kind-specific.

It should use local project config recipes, not manifest-supplied commands.
It must treat the rebuild as untrusted-code execution and apply the execution safety model above.

Comparison modes should be explicit:

- `exact-bytes`
- `zip-normalized`
- `canonical-archive`
- `repository-tree`
- `platform-digest`
- `content-only`
- `provenance-only`

`provenance-only` means:

- the local build completed
- the expected artifact kind was produced
- exact or canonical comparison is not yet claimed

## Default Cryptographic Policy

Phase 1a should define a tool-wide minimum policy instead of treating "GPG accepted it" as the whole answer.

Recommended phase-1a defaults:

- manifest and source-artifact checksum sidecars should use SHA-512
- secondary ecosystems may use their native strong integrity material, but the verifier should not accept digests below a SHA-256-strength floor
- detached signature verification should record full signer fingerprint, key algorithm, key size, and key status information
- hard fail on invalid signatures, missing required signatures, revoked signing keys, or integrity material below the minimum accepted floor
- report legacy-but-still-valid constructions as warnings first, with a distinct policy verdict separate from basic signature-validity reporting

Extensibility:

- project config may tighten the policy for a repository or artifact family
- project config should not weaken the tool-wide minimum acceptance floor silently

## Secondary Artifact Strategy

I do not think the right answer is "just let projects put arbitrary shell commands in the manifest".

That would create four problems:

- security risk on developer machines
- portability problems across Linux and macOS
- hard-to-review verification logic
- weak reuse across ASF projects

I recommend a hybrid model instead.

Built-in verifier kinds:

- `generic-file`
- `generic-file-with-openpgp`
- `github-release-mirror`
- `maven-repository`
- `python-distribution`
- `oci-image`
- `npm-package`

Project-local recipes:

- describe how to rebuild local outputs for one verifier kind
- live in `release-config.yaml`
- are optional for projects that only want remote authenticity and integrity verification

This gives the tool reusable primitives while still allowing project-specific local build steps.

One more recommendation:

- artifacts that public voters are expected to verify should have public staged locators
- draft GitHub Release assets should be treated as optional mirrors or maintainer conveniences, not as the only verification endpoint
- the manifest may contain any number of artifacts of the same `kind`, distinguished by `artifact_id`

## Artifact Family Recommendations

### Generic file and mirror artifacts

Use this for:

- GitHub Release asset mirrors
- standalone ZIPs or tarballs
- generated convenience archives

Recommended checks:

- recompute digest
- compare with signed manifest
- if `.asc` exists, verify against KEYS
- if this is only a mirror, compare it to the authoritative artifact declared elsewhere

### Maven and Nexus repositories

This is a strong first-class target to support.

The Maven repository layout is standardized, including checksum and optional `.asc` sidecars. Local and remote repositories use the same layout, which is ideal for verification.

Recommended representation:

- one `maven-repository` secondary target in the main manifest
- include the Nexus staging repository ID and base URL in that target
- do not require a publisher-generated inventory in phase 1

Remote verification:

- enumerate the staged repository directly
- verify `.asc` sidecars for artifacts that require signatures
- verify checksums and required metadata files

Local comparison:

- build into a local file-based Maven repository
- compare selected repository paths and digests
- allow policy to ignore non-release metadata if needed

This is better than trying to compare a live Nexus UI or API view directly.

Recommended reproducibility default for Maven repository artifacts:

- use `content-only` by default for ZIP-like artifacts such as JARs
- allow stricter per-path or regex-based overrides to `zip-normalized` or `exact-bytes`

Implementation note:

- always check exact digest equality first
- only unpack or normalize ZIP-like artifacts when exact bytes differ and the policy allows a weaker equivalence mode

### PyPI or TestPyPI distributions

This should also be a first-class target.

PyPI and TestPyPI expose distribution metadata and hashes through the simple and JSON APIs. PyPI also exposes attestations through the Integrity API.

Recommended checks:

- resolve the published file via the simple or JSON API
- verify the file digest against the signed manifest
- if a detached `.asc` exists, verify it
- when attestation data exists, verify it against the expected repository identity

Local comparison:

- rebuild via `python -m build`
- compare wheels and sdists using `exact-bytes` where possible
- allow `canonical-archive` if a project is not yet fully wheel-reproducible

### OCI container images

Container images deserve a dedicated verifier kind, but not necessarily in the first implementation milestone.

Recommended tooling direction:

- prefer daemonless tools such as `crane` or `oras` for registry access
- use `cosign` for signature or attestation verification where projects publish Sigstore metadata

Recommended remote checks:

- verify the published digest matches the signed manifest
- for multi-platform images, record and verify either:
  - the manifest-list digest plus platform digests, or
  - one declared per-platform digest per artifact entry
- verify `cosign` signatures or attestations against expected issuer and identity when present

Local comparison:

- compare platform-specific image digests, OCI layouts, or manifest plus layer digests
- do not assume Docker daemon access

Recommendation:

- support OCI verification after Maven and PyPI
- make local reproducibility initially advisory

### npm packages

npm is another good first-class verifier kind, but it should come after Maven and PyPI.

The npm registry provides:

- tarball integrity material via `dist.integrity`
- registry signatures
- provenance attestations that `npm audit signatures` can verify

Recommended remote checks:

- fetch the package metadata from the registry
- verify the tarball digest or integrity value against the signed manifest
- verify registry signatures
- when provenance exists, verify the expected repository and workflow identity

Local comparison:

- rebuild with `npm pack`
- compare the produced tarball or canonical unpacked contents

Recommendation:

- treat npm provenance as a strong authenticity signal when available
- keep exact reproducibility advisory until a given project opts in

## Reproducibility Model

I recommend three reproducibility levels.

Level 1: remote-only

- authenticity and integrity verified
- no local rebuild comparison claimed

Level 2: buildable and canonically comparable

- local rebuild succeeds
- a declared canonical comparison passes
- exact bytes may still differ for known, declared reasons

Level 3: exact reproducibility

- local rebuild succeeds
- staged and local artifacts are byte-identical

Per-artifact policy should decide whether failure is:

- fatal
- warning
- not attempted

My recommendation:

- source tarball: target Level 3
- Maven repo artifacts: start at Level 2 with `content-only` defaults for ZIP-like artifacts, then move selected artifacts to `zip-normalized` or Level 3
- PyPI wheels and sdists: start at Level 2 or 3 depending on project
- OCI images: start at Level 1 or 2
- npm packages: start at Level 2

This accommodates cases like Quarkus-generated bytecode without weakening the required authenticity and integrity baseline.

Verifier modes:

- `integrity-only`: verify manifest, source artifact, and remote secondary artifacts only
- `full`: additionally run configured local rebuild and reproducibility checks without prompting
- `auto`: on an interactive TTY, run remote checks first and then prompt before any local rebuild or other untrusted-code execution

The verifier should let a user opt out of reproducibility checks by choosing `integrity-only`. The report must state that this was not a full reproducibility run.
On an interactive TTY, `auto` should be the default local usability mode. On non-interactive shells and CI, the verifier should not prompt and should behave like `integrity-only` unless `full` was explicitly selected.
Project config may additionally declare that `full` is the expected vote path for that project, even though the verifier still allows an explicit `integrity-only` run.

## Reproducibility Inspection Model

I recommend a two-stage design:

- `verify-rc` determines the verification and reproducibility verdicts
- `inspect-repro` performs deeper post-failure investigation later, using the saved report and evidence bundle

Responsibilities of `verify-rc`:

- compare artifacts according to the selected reproducibility policy
- classify the failure at a useful high level
- write a machine-readable report that contains all information needed for later inspection
- save a curated inspection bundle rather than forcing later tooling to depend on the entire raw work directory

Responsibilities of `inspect-repro`:

- read `report.json` and the associated inspection bundle
- summarize failure classes first
- run archive-aware or file-aware analyzers against the saved evidence
- optionally invoke deeper external tools such as `diffoscope` when installed and requested
- write a second-layer inspection report without changing the original verification verdict

Inspection-bundle contract:

- the durable contract should be `report.json` plus a curated inspection bundle, not an implicit dependency on the entire work directory
- paths recorded in the report should be relative to the inspection-bundle root so the bundle remains relocatable after download
- the bundle should contain only the evidence needed for later diagnosis, not every transient build artifact by default
- when `--inspection-bundle` is omitted, auto-name the bundle from the same base identifier as the report, for example `verify-rc-inspection-<component_id>-<version>-<rc_id>-<timestamp>/`

Suggested bundle contents for a reproducibility failure:

- failing artifact-pair metadata
- relative paths to retained RC and local artifacts when they are preserved
- normalized file manifests or archive entry listings
- archive metadata dumps
- built-in mismatch summaries
- optional extracted subsets or per-path evidence for problematic members

Suggested first analyzers for `inspect-repro`:

- `diff`
- `tar` with reproducibility-oriented listing options
- `zipinfo`
- `zipcmp`
- optional `diffoscope` when available

Interactive local behavior:

- if `verify-rc` finds reproducibility issues on an interactive TTY, it may offer to launch `inspect-repro` immediately against the just-written report and evidence bundle
- if the user declines, the saved report and bundle should still be sufficient to run `inspect-repro` later without rerunning verification

## GitHub Workflow Shape

Recommended workflow contract:

- `permissions: contents: read`
- input: `rc_vote_manifest_url`
- input: `keys_url`
- checkout the project repository
- when using `actions/checkout`, set `persist-credentials: false`
- prefer `integrity-only` on shared CI unless rebuilds run in a separate isolated environment with no ambient secrets
- if `full` is enabled on CI, run the rebuild step in a dedicated container or ephemeral VM with no injected secrets beyond what is strictly required for public artifact fetches
- a GitHub-hosted ephemeral runner may satisfy that requirement when the workflow keeps `permissions: contents: read`, injects no additional secrets, and does not rely on persistent shared state or shared caches
- CI runs should stay non-interactive: if rebuild execution or rebuild network policy is needed, specify them explicitly rather than relying on prompts
- for RC preparation flows with multiple producer jobs, pass secondary-artifact registration bundles through workflow artifacts and let `finalize-rc-vote-materials` merge them
- use outputs only for small scalar state such as `rc_tag` or bundle names, not for full artifact-registration JSON payloads or inventory files
- optionally present a signed bootstrap one-liner in the workflow summary or RC email
- run `buildish-release-tooling verify-rc <url> <keys-url>`
- write:
  - markdown summary
  - JSON report
  - reproducibility inspection bundle when reproducibility checks were attempted
  - optional downloaded inputs and normalized comparison outputs as workflow artifacts

If reproducibility issues are found in CI:

- upload the `report.json` plus inspection bundle as workflow artifacts
- let humans download those artifacts and run `buildish-release-tooling inspect-repro <report-json>` later on a local machine or a fresh CI rerun

The workflow should not require:

- write-capable GitHub permissions
- publish tokens
- mutation of tags, releases, branches, or SVN state

## Developer Machine Shape

Recommended expectations:

- supported on Linux and macOS
- if no `--work-dir` is supplied, create a temp work directory automatically and print its path early
- uses isolated GPG home or `gpgv`
- treat `full` mode as untrusted-code execution and run it in an isolated environment with no ambient secrets
- use a scrubbed environment for rebuild subprocesses and relocate `HOME`-like directories into the temp work area
- if running on an interactive TTY with no explicit `--mode`, use `auto` and prompt before any local rebuild step
- if rebuild execution is approved interactively and no explicit `--build-network` was supplied, ask whether rebuild should be `offline-only` or `network-allowed`
- if the work directory was auto-created and neither `--keep-work-dir` nor `--no-keep-work-dir` was supplied, ask at the end whether to keep or purge it
- if the run fails and the work directory was auto-created, keep it by default unless the caller explicitly requested purge
- if reproducibility issues are found on an interactive TTY, the user may be offered an immediate handoff into `inspect-repro`
- checks for required external tools and fails with actionable messages
- preflights tools needed for the selected verification mode before doing expensive work

Base dependencies:

- Python
- GnuPG

### Minimum Python Version

The bootstrap script should check the local Python version before doing expensive work such as cloning the tooling repository.

Current reality:

- the main `buildish-release-tooling` package currently requires Python `>=3.11`
- if the verifier continues to execute code directly from that package, the bootstrap path must also require Python `>=3.11`

Adoption tradeoff:

- Python `3.11` is a much safer baseline across current macOS systems and common Linux LTS distributions than Python `3.13`
- if broader verifier adoption still needs an even lower operational burden, a future self-contained verifier artifact may still be worth considering

Recommendation:

- phase 1 bootstrapper: preflight and clearly enforce the actual verifier minimum
- longer term: try to keep `apache_buildish_release_tooling.verification` compatible with a lower Python baseline than the rest of release-tooling, if that can be done without distorting the codebase

Optional per-verifier dependencies:

- Maven or Gradle
- Node and npm
- `crane` or `oras`
- `cosign`

These should be activated only when the selected manifest actually contains artifacts of that kind.

Tool policy:

- missing tool for a required check in the selected mode: hard fail
- missing tool for an advisory check outside the selected mode: do not fail

## Proposed Reporting

The verifier should emit:

- a machine-readable JSON report
- a human-readable markdown report
- a non-zero exit code on required-check failure

When reproducibility checks are attempted, `verify-rc` should also emit a curated inspection bundle suitable for later use by `inspect-repro`.

Default naming:

- if `--report-json` is omitted, write a default filename such as `verify-rc-report-<component_id>-<version>-<rc_id>-<timestamp>.json`
- if `--report-md` is omitted, derive its filename from the same identifier
- if `--inspection-bundle` is omitted, derive its directory name from the same identifier
- if the user explicitly supplies a path for any of these outputs, honor that path exactly

Each artifact should get a verdict record with:

- artifact ID or filename
- artifact kind
- remote locator
- authenticity result
- integrity result
- reproducibility result
- evidence, such as digest values, full signer fingerprints, signer algorithm or key-size metadata, or attestation identities
- effective safety policy data, such as whether origin allowlists, execution isolation, resource-budget overrides, or cryptographic warnings affected the run

The machine-readable report should also record run-level metadata such as:

- `component_id`
- `version`
- `rc_id` or equivalent RC label when known
- `manifest_url`
- `keys_url`
- `started_at`
- `finished_at`
- `mode`
- `build_network_policy`
- `report_format_version`

For reproducibility failures, the machine-readable report should also record:

- the compared artifact pair or collection entry
- the comparison mode attempted
- the high-level failure class
- relative paths into the inspection bundle for retained evidence files
- whether optional deep-analysis tools were available or used

The report should be sufficient for later inspection tooling to work without rerunning verification, assuming the inspection bundle is still present.

This makes the tool useful both for humans and for CI.

## Suggested Python Module Layout

One reasonable internal layout would be:

```text
release/
  ...
verification/
  __init__.py
  __main__.py
  cli.py
  driver.py
  reports.py
  trust.py
  manifest_bootstrap.py
  source_artifact.py
  artifact_models.py
  inspect_repro.py
  inspection_bundle.py
  secondary/
    __init__.py
    generic_file.py
    maven_repository.py
    python_distribution.py
    oci_image.py
    npm_package.py
  inspection/
    __init__.py
    analyzers.py
    archive_metadata.py
    diffoscope_runner.py
```

This keeps verification as a sibling of `release`, not a subdomain inside it. The current `verify-rc` stub in command code should become a thin dispatcher into this verification package.

## Phased Implementation Plan

The typed secondary-artifact registration layer described above is already implemented in the `release` CLI. The phases below focus on remaining verifier-side `verify-rc` work and follow-on verifier kinds.

### Phase 1a. Core verify-rc MVP

- change CLI contract to `verify-rc <rc-vote-manifest-url> <keys-url>`
- require explicit `keys_url` argument
- add `asf_keys_url` to config
- make manifest generation record explicit KEYS URL instead of deriving it
- implement manifest verification
- require the manifest to carry `rc_tag` explicitly
- fail closed unless `rc_tag` resolves to the same Git commit as `source_commit_sha`
- implement source artifact verification
- verify that the staged source artifact matches the declared `source_commit_sha`
- emit JSON and markdown reports
- define the minimum cryptographic policy and signer reporting

This is the minimum useful verifier implementation.

### Phase 1b. Bootstrap UX

- implement signed bootstrap script generation
- stage the bootstrap script and sidecars in ASF `dist/dev` and mirror them to the draft GitHub Release
- wire the invoker snippets into vote-email and draft-release templates
- document clearly that the bootstrap script is a convenience layer, not the verifier trust anchor

This phase helps adoption, but it should not be described as secure-by-default for ordinary developer machines until the open bootstrap trust-chain issue in this document is addressed.

### Phase 2. Generic secondary file verification

- consume typed registration fragments already emitted by `record-artifact`
- add verifier-side `generic-file` and `generic-file-with-openpgp` support
- support GitHub Release asset mirrors
- support collection inventories referenced from the main manifest

This covers many convenience artifacts quickly.

### Phase 3. Maven repository verifier

- consume Nexus staging repository IDs and base URLs from typed registration fragments
- implement remote repository verification
- implement local repository comparison

This is probably the highest-value first ecosystem-specific secondary verifier.

### Phase 4. Python distribution verifier

- implement verifier-side `python-distribution` support
- support PyPI or TestPyPI file resolution and digest checks
- support PyPI attestations where present
- implement local rebuild comparison

### Phase 5. OCI and npm verifiers

- implement verifier-side `oci-image` support
- implement verifier-side `npm-package` support
- keep local reproducibility advisory first

### Phase 6. Reproducibility hardening

- add canonical comparison helpers
- allow per-artifact policy upgrades from advisory to required
- add more exact-match coverage over time
- TODO: add thorough verifier test coverage for missing-file, missing-sidecar, and zero-length-file cases across the source artifact and every secondary-artifact kind; verify that missing inputs are reported without aborting unrelated safe checks, and make the intended zero-byte policy explicit per kind
- add inspection-bundle generation and the `inspect-repro` command
- support optional deep analyzers such as `diffoscope` without making them required verifier dependencies

## Recommended Near-Term Decisions

I would make these decisions now:

1. `verify-rc` should be manifest-URL driven, not version-driven.
2. The KEYS URL should be a mandatory verifier argument.
3. `asf_keys_url` should be explicit project config and manifest cross-check material, not the bootstrap source of trust.
4. The manifest should remain data-only.
5. Project-specific commands should live in local config.
6. Authenticity and integrity are required.
7. On interactive local TTYs, `auto` should be the default; on non-interactive shells and CI, `integrity-only` should remain the default.
8. Reproducibility is graded per artifact family.
9. Large or mutable artifact collections should verify against a signed fixed inventory snapshot.
10. Production verification should use artifact-family origin allowlists with sane defaults and explicit test-mode escape hatches.
11. The verifier should enforce sane default resource budgets with explicit CLI override knobs.
12. Phase 1a should ship a tool-wide minimum cryptographic policy and detailed signer reporting.
13. Reproducibility investigation should be a separate `inspect-repro` capability fed by `verify-rc` reports and curated inspection bundles.
14. Maven repository verification should be the first secondary-artifact family after generic files.
15. Phase 1b UX may use a signed bootstrap script rather than `uv` or local Python packaging setup, but the bootstrap trust-chain issue remains open and should be solved early.

## Simulated `verify-rc` Output

These examples reflect the current CLI behavior.

- With `--progress on` and with `auto` on an interactive terminal, `verify-rc` emits a sectioned verification transcript to stderr.
- With `--color auto` on an interactive terminal, `verify-rc` colors the human stderr transcript; the examples below omit ANSI escapes for readability.
- `verify-rc` always writes a combined transcript and low-level command log file. By default that file is `<work-dir>/verify-rc.log`, or a caller may override it with `--log-path`.
- `--verbose` additionally mirrors the low-level command traces and captured subprocess output to stderr.
- `verify-rc` does not print report paths to stdout; humans get the transcript on stderr and automation should pass `--report-json` when it needs a deterministic machine-readable output path.
- On failure, `verify-rc` still writes the JSON report, Markdown report, and combined log file, then exits with status `1`.
- When the transcript is suppressed because `--progress` is off or `auto` resolves off, failures still surface a fallback stderr summary line.
- The trust gate still fails fast on manifest fetch, checksum, signature, or KEYS-binding problems.
- After the trust gate is established, `verify-rc` keeps going across the remaining safe verification surfaces and collects multiple issues into one failed report.
- That includes multiple issues within a single artifact when they are independently observable, such as source checksum plus sidecar plus signature plus reproducibility drift, or Maven repository checksum plus detached-signature drift.
- The examples below shorten absolute paths, digests, and fingerprints for readability.

### Successful local run

```console
$ buildish-release-tooling verify-rc \
    --component-config buildish-release-tooling/release-config.yaml \
    --allow-non-production-release-targets \
    --progress on \
    --work-dir build/verify-rc-demo \
    --log-path build/verify-rc-demo/verify.log \
    file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
    file:///tmp/dist/release/incubator/buildish/KEYS
Verify RC
=========
  Work directory: build/verify-rc-demo
  Manifest URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json
  KEYS URL: file:///tmp/dist/release/incubator/buildish/KEYS
  Transcript log: build/verify-rc-demo/verify.log

Vote Manifest
-------------
• Downloading signed RC vote manifest and sidecars
✓ Downloaded manifest, checksum sidecar, signature, and KEYS
✓ Verified manifest SHA512: 9f3d2e...
✓ Verified manifest signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
  Component: buildish-example
  Version: 1.2.3
  RC tag: v1.2.3-rc0
✓ Cross-checked KEYS URL against the signed manifest
✓ Cross-checked KEYS URL against component config

Source Artifact
---------------
  Source repository: file:///tmp/git/buildish-example.git
  Source commit: bbafdeb50db5ea832c7674b547d6c07feff46265
• Cloning source repository
✓ Cloned source repository
✓ Verified rc_tag binding: v1.2.3-rc0 -> bbafdeb50db5ea832c7674b547d6c07feff46265
  Artifact: apache-buildish-example-1.2.3-incubating-src.tar.gz
  Artifact URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/apache-buildish-example-1.2.3-incubating-src.tar.gz
• Downloading staged source artifact
✓ Downloaded staged source artifact
✓ Verified staged source SHA512: 4e6e7c...
✓ Verified source artifact SHA512 sidecar
✓ Verified source artifact signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
• Rebuilding source artifact from declared source commit
✓ Rebuilt source artifact SHA512: 4e6e7c...
✓ Verified staged source artifact matches the declared source commit

Secondary Artifacts
-------------------

Secondary Artifact 1/1: site-bundle
-----------------------------------
  Kind: generic-file-with-openpgp
  File: buildish-example-site-1.2.3.zip
  URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/buildish-example-site-1.2.3.zip
✓ Verified checksum: sha512:33bd2e...
✓ Verified checksum sidecar
✓ Verified signature: 8C3F...A91D

Outcome
-------
✓ Verified RC: buildish-example 1.2.3 (v1.2.3-rc0)
  Report JSON: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.json
  Report Markdown: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.md
  Transcript log: build/verify-rc-demo/verify.log

$ sed -n '1,80p' build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.md
```

~~~md
## Verify RC

### Technical details

| Field | Value |
| --- | --- |
| Component | `buildish-example` |
| Version | `1.2.3` |
| RC tag | `v1.2.3-rc0` |
| Source commit | `bbafdeb50db5ea832c7674b547d6c07feff46265` |
| Source repository URL | `file:///tmp/git/buildish-example.git` |
| Manifest URL | `file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json` |
| KEYS URL | `file:///tmp/dist/release/incubator/buildish/KEYS` |

### Manifest verification

- ✓ Signature verified: `8C3F...A91D`
- ✓ RC tag resolved from the signed manifest: `v1.2.3-rc0`

### Source artifact verification

- Source artifact: `apache-buildish-example-1.2.3-incubating-src.tar.gz`
- Source artifact URL: `file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/apache-buildish-example-1.2.3-incubating-src.tar.gz`
- SHA512: `4e6e7c...`
- ✓ Signature verified: `8C3F...A91D`
- ✓ Declared source commit: `bbafdeb50db5ea832c7674b547d6c07feff46265`

### Secondary artifact verification

#### `site-bundle`

- Kind: `generic-file-with-openpgp`
- File: `buildish-example-site-1.2.3.zip`
- URL: `file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/buildish-example-site-1.2.3.zip`
- Checksum observed: `sha512:33bd2e...`
- Checksum matched signed manifest: `True`
- Checksum sidecar verified: `True`
- Signature verified: `8C3F...A91D`

### Outcome

```text
Verified manifest authenticity, explicit KEYS binding, rc_tag-to-source_commit binding, the staged source artifact bytes, and all supported secondary artifacts declared in the signed manifest.
```
~~~

### Successful run with `--verbose`

```console
$ buildish-release-tooling verify-rc \
    --component-config buildish-release-tooling/release-config.yaml \
    --allow-non-production-release-targets \
    --progress on \
    --verbose \
    --work-dir build/verify-rc-demo \
    --log-path build/verify-rc-demo/verify.log \
    file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
    file:///tmp/dist/release/incubator/buildish/KEYS
Verify RC
=========
  Work directory: build/verify-rc-demo
  Manifest URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json
  KEYS URL: file:///tmp/dist/release/incubator/buildish/KEYS

Vote Manifest
-------------
• Downloading signed RC vote manifest and sidecars
+ gpg --batch --quiet --import build/verify-rc-demo/KEYS
✓ Downloaded manifest, checksum sidecar, signature, and KEYS
✓ Verified manifest SHA512: 9f3d2e...
+ gpg --batch --status-fd 1 --verify build/verify-rc-demo/rc-vote-manifest.json.asc build/verify-rc-demo/rc-vote-manifest.json
stdout | [GNUPG:] VALIDSIG 8C3F...A91D ...
✓ Verified manifest signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
...
+ git clone --quiet file:///tmp/git/buildish-example.git build/verify-rc-demo/source-repository
+ git -C build/verify-rc-demo/source-repository rev-parse --verify --quiet 'v1.2.3-rc0^{commit}'
...
```

### Failure: aggregated secondary-artifact mismatches

```console
$ buildish-release-tooling verify-rc \
    --component-config buildish-release-tooling/release-config.yaml \
    --allow-non-production-release-targets \
    --progress on \
    --work-dir build/verify-rc-demo \
    --log-path build/verify-rc-demo/verify.log \
    file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
    file:///tmp/dist/release/incubator/buildish/KEYS
Verify RC
=========
  Work directory: build/verify-rc-demo
  Manifest URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json
  KEYS URL: file:///tmp/dist/release/incubator/buildish/KEYS
  Transcript log: build/verify-rc-demo/verify.log

Vote Manifest
-------------
• Downloading signed RC vote manifest and sidecars
✓ Downloaded manifest, checksum sidecar, signature, and KEYS
✓ Verified manifest SHA512: 9f3d2e...
✓ Verified manifest signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
  Component: buildish-example
  Version: 1.2.3
  RC tag: v1.2.3-rc0
✓ Cross-checked KEYS URL against the signed manifest
✓ Cross-checked KEYS URL against component config

Source Artifact
---------------
  Source repository: file:///tmp/git/buildish-example.git
  Source commit: bbafdeb50db5ea832c7674b547d6c07feff46265
• Cloning source repository
✓ Cloned source repository
✓ Verified rc_tag binding: v1.2.3-rc0 -> bbafdeb50db5ea832c7674b547d6c07feff46265
  Artifact: apache-buildish-example-1.2.3-incubating-src.tar.gz
  Artifact URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/apache-buildish-example-1.2.3-incubating-src.tar.gz
• Downloading staged source artifact
✓ Downloaded staged source artifact
✓ Verified staged source SHA512: 4e6e7c...
✓ Verified source artifact SHA512 sidecar
✓ Verified source artifact signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
• Rebuilding source artifact from declared source commit
✓ Rebuilt source artifact SHA512: 4e6e7c...
✓ Verified staged source artifact matches the declared source commit

Secondary Artifacts
-------------------

Secondary Artifact 1/1: bootstrap-zip
-------------------------------------
  Kind: generic-file
✗ secondary artifact checksum does not match the signed manifest: bootstrap-zip 5f0c2b... != 33bd2e...

Secondary Artifact 2/2: pypi-wheel
----------------------------------
  Kind: python-distribution
✗ python-distribution file is not present in the declared simple index: file:///tmp/simple/example/ -> example-1.2.3-py3-none-any.whl

Outcome
-------
✗ Verification failed with 2 issue(s)
  Report JSON: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.json
  Report Markdown: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.md
  Transcript log: build/verify-rc-demo/verify.log

$ echo $?
1
```

### Failure: source artifact plus npm plus maven issues

This example reflects the current behavior precisely:

- `verify-rc` keeps going after the trust gate and continues through the remaining safe checks.
- The final JSON and Markdown reports contain all collected failures.
- One artifact may contribute multiple issues when the verifier can observe them independently.

```console
$ buildish-release-tooling verify-rc \
    --component-config buildish-release-tooling/release-config.yaml \
    --allow-non-production-release-targets \
    --progress on \
    --work-dir build/verify-rc-demo \
    --log-path build/verify-rc-demo/verify.log \
    file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json \
    file:///tmp/dist/release/incubator/buildish/KEYS
Verify RC
=========
  Work directory: build/verify-rc-demo
  Manifest URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/rc-vote-manifest.json
  KEYS URL: file:///tmp/dist/release/incubator/buildish/KEYS
  Transcript log: build/verify-rc-demo/verify.log

Vote Manifest
-------------
• Downloading signed RC vote manifest and sidecars
✓ Downloaded manifest, checksum sidecar, signature, and KEYS
✓ Verified manifest SHA512: 9f3d2e...
✓ Verified manifest signature: 8C3F...A91D (Release Manager <rm@example.invalid>)
  Component: buildish-example
  Version: 1.2.3
  RC tag: v1.2.3-rc0
✓ Cross-checked KEYS URL against the signed manifest
✓ Cross-checked KEYS URL against component config

Source Artifact
---------------
  Source repository: file:///tmp/git/buildish-example.git
  Source commit: bbafdeb50db5ea832c7674b547d6c07feff46265
• Cloning source repository
✓ Cloned source repository
✓ Verified rc_tag binding: v1.2.3-rc0 -> bbafdeb50db5ea832c7674b547d6c07feff46265
  Artifact: apache-buildish-example-1.2.3-incubating-src.tar.gz
  Artifact URL: file:///tmp/dist/dev/incubator/buildish/buildish-example/1.2.3-rc0/apache-buildish-example-1.2.3-incubating-src.tar.gz
• Downloading staged source artifact
✓ Downloaded staged source artifact
✗ staged source artifact checksum does not match the signed manifest: d1aa7c... != 4e6e7c...
✗ source artifact .sha512 sidecar does not match the downloaded bytes: 4e6e7c... != d1aa7c...
✗ command failed: gpg --batch --status-fd 1 --verify build/verify-rc-demo/apache-buildish-example-1.2.3-incubating-src.tar.gz.asc build/verify-rc-demo/apache-buildish-example-1.2.3-incubating-src.tar.gz: gpg: BAD signature from "Release Manager <rm@example.invalid>" [unknown]
• Rebuilding source artifact from declared source commit
✓ Rebuilt source artifact SHA512: 4e6e7c...
✗ staged source artifact does not match the declared source_commit_sha

Secondary Artifacts
-------------------

Secondary Artifact 1/2: maven-staging-main
------------------------------------------
  Kind: maven-repository
• Enumerating live repository from file:///tmp/orgapacheexample-1234/
• Checking live repository against signed inventory (42 entries)
• Verifying detached signatures present in the live repository
  Base URL: file:///tmp/orgapacheexample-1234/
  Inventory: maven-staging-main-inventory.json
✗ live maven repository paths do not match the signed inventory: missing=['org/example/app/1.0.0/app-1.0.0.jar.sha512'] unexpected=['org/example/app/1.0.0/README.txt']
✗ live maven repository file size does not match the signed inventory: org/example/app/1.0.0/app-1.0.0.jar 9132 != 8744
✗ live maven repository checksum does not match the signed inventory: org/example/app/1.0.0/app-1.0.0.jar deadbeef... != cafe1234...
✗ command failed: gpg --batch --status-fd 1 --verify build/verify-rc-demo/secondary-artifacts/01-maven-staging-main/signatures/org/example/app/1.0.0/app-1.0.0.jar.asc build/verify-rc-demo/secondary-artifacts/01-maven-staging-main/signatures/org/example/app/1.0.0/app-1.0.0.jar: gpg: BAD signature from "Release Manager <rm@example.invalid>" [unknown]

Secondary Artifact 2/2: npm-package-main
----------------------------------------
  Kind: npm-package
  Package: @apache/buildish-example 1.2.3
  Registry: file:///tmp/npm-registry/
  Tarball: file:///tmp/npm-dist/buildish-example-1.2.3.tgz
✓ Verified registry metadata: file:///tmp/npm-registry/@apache/buildish-example
✗ npm-package checksum does not match the signed manifest: npm-package-main 9abcde... != 123456...
✗ npm-package integrity does not match the downloaded tarball bytes: npm-package-main 9abcde... != 123456...

Outcome
-------
✗ Verification failed with 10 issue(s)
  Report JSON: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.json
  Report Markdown: build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.md
  Transcript log: build/verify-rc-demo/verify.log

$ sed -n '1,120p' build/verify-rc-demo/verify-rc-report-buildish-example-v1.2.3-rc0.md
```

~~~md
## Verify RC

### Outcome

- ✗ Verification failed with `10` issue(s).
- `source-artifact` / `staged source checksum`: staged source artifact checksum does not match the signed manifest: d1aa7c... != 4e6e7c...
- `source-artifact` / `source artifact checksum sidecar`: source artifact .sha512 sidecar does not match the downloaded bytes: 4e6e7c... != d1aa7c...
- `source-artifact` / `source artifact signature`: command failed: gpg --batch --status-fd 1 --verify build/verify-rc-demo/apache-buildish-example-1.2.3-incubating-src.tar.gz.asc build/verify-rc-demo/apache-buildish-example-1.2.3-incubating-src.tar.gz: gpg: BAD signature from "Release Manager <rm@example.invalid>" [unknown]
- `source-artifact` / `source artifact reproducibility`: staged source artifact does not match the declared source_commit_sha
- `secondary-artifact` / `maven-staging-main`: live maven repository paths do not match the signed inventory: missing=['org/example/app/1.0.0/app-1.0.0.jar.sha512'] unexpected=['org/example/app/1.0.0/README.txt']
- `secondary-artifact` / `maven-staging-main`: live maven repository file size does not match the signed inventory: org/example/app/1.0.0/app-1.0.0.jar 9132 != 8744
- `secondary-artifact` / `maven-staging-main`: live maven repository checksum does not match the signed inventory: org/example/app/1.0.0/app-1.0.0.jar deadbeef... != cafe1234...
- `secondary-artifact` / `maven-staging-main`: command failed: gpg --batch --status-fd 1 --verify build/verify-rc-demo/secondary-artifacts/01-maven-staging-main/signatures/org/example/app/1.0.0/app-1.0.0.jar.asc build/verify-rc-demo/secondary-artifacts/01-maven-staging-main/signatures/org/example/app/1.0.0/app-1.0.0.jar: gpg: BAD signature from "Release Manager <rm@example.invalid>" [unknown]
- `secondary-artifact` / `npm-package-main`: npm-package checksum does not match the signed manifest: npm-package-main 9abcde... != 123456...
- `secondary-artifact` / `npm-package-main`: npm-package integrity does not match the downloaded tarball bytes: npm-package-main 9abcde... != 123456...
~~~

## References

The artifact-family recommendations above were informed by the following primary sources:

- PyPI Index API: <https://docs.pypi.org/api/index-api/>
- PyPI attestations consumption: <https://docs.pypi.org/attestations/consuming-attestations/>
- Maven repository layout: <https://maven.apache.org/repository/layout.html>
- npm registry signatures: <https://docs.npmjs.com/about-registry-signatures/>
- npm provenance verification: <https://docs.npmjs.com/viewing-package-provenance/>
- npm audit signatures: <https://docs.npmjs.com/verifying-registry-signatures/>
- Docker image digests: <https://docs.docker.com/reference/cli/docker/image/pull/>
- Docker digest and multi-platform notes: <https://docs.docker.com/dhi/core-concepts/digests/>
- Sigstore cosign verification: <https://docs.sigstore.dev/cosign/verifying/verify/>
