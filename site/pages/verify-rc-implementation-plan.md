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
- keep the verifier read-only: it may download artifacts, build locally, and write reports to a temp/work directory, but it must not push, tag, publish, or mutate Git state
- require the KEYS URL as an explicit verifier input; only use manifest or local config KEYS URLs as cross-check material
- separate required authenticity and integrity checks from optional or project-graded reproducibility checks
- support common secondary artifact families with built-in typed verifiers, and use project-local build recipes only as a controlled extension point
- do not execute shell commands from the remote manifest; project-specific commands must come from local project config

Related planning:

- [ATR Integration Assessment](atr-integration-assessment.md)

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

## Proposed CLI Contract

Recommended public CLI:

```text
buildish-release-tooling verify-rc <rc-vote-manifest-url> <keys-url>
```

Recommended optional flags:

- `--work-dir <path>`: keep downloads, local builds, and reports in a caller-chosen directory
- `--report-json <path>`: write machine-readable verification report
- `--report-md <path>`: write human-readable verification report
- `--mode <integrity-only|full>`: remote verification only, or remote plus local reproducibility checks

I would keep the public contract minimal and avoid adding many user-facing flags in the first implementation.

The command must work without write-capable GitHub permissions. It should not require a token for normal public ASF artifacts.

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
    reproducibility:
      mode: exact-bytes

  secondary_profiles:
    maven-staging:
      kind: maven-repository
      build:
        command:
          ["./mvnw", "-Prelease", "deploy", "-DaltDeploymentRepository=local::default::file:${WORK_DIR}/m2repo"]
        repository_dir: "${WORK_DIR}/m2repo"
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
- add optional `inventory` subdocuments for large artifact collections such as Maven repositories or image sets
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

This keeps the main signed manifest authoritative without forcing it to inline thousands of repository entries. However, inventories should be optional, not mandatory, for artifact families that are already self-describing on the remote side.

## Secondary Artifact Registration Contract

The current design needs an explicit contract for how RC preparation workflows tell release-tooling about staged secondary artifacts.

This does not have to be one command per ecosystem, but there must be a typed handoff mechanism.

Recommended first design:

- keep `finalize-rc-vote-materials --secondary-artifact-manifests ...`
- add helper commands that emit typed JSON manifest fragments
- have RC preparation workflows invoke those helper commands after staging each secondary target

Possible helpers:

- `record-maven-staging-repository`
- `record-python-distribution`
- `record-oci-image`
- `record-npm-package`
- `record-generic-file`

Each helper should write a small JSON payload that can later be merged into the signed `rc-vote-manifest`.

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

The same pattern applies to other ecosystems:

- OCI: registry, repository, digest, optional platform digests
- npm: registry URL, package name, version
- PyPI or TestPyPI: index URL, project name, version, filenames

This keeps RC preparation and RC verification connected by a typed, reviewable contract instead of ad hoc free-form notes.

## Verification Pipeline

### Phase A. Verify the signed RC vote-manifest

Required behavior:

- fetch manifest and sidecars over `https://` by default
- allow `file://` or plain `http://` only in explicit test mode for harness scenarios
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

### Phase D. Rebuild and compare secondary artifacts locally

This phase is project- and artifact-kind-specific.

It should use local project config recipes, not manifest-supplied commands.

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
- `full`: additionally run configured local rebuild and reproducibility checks

The verifier should let a user opt out of reproducibility checks by choosing `integrity-only`. The report must state that this was not a full reproducibility run.
Project config may additionally declare that `full` is the expected vote path for that project, even though the verifier still allows an explicit `integrity-only` run.

## GitHub Workflow Shape

Recommended workflow contract:

- `permissions: contents: read`
- input: `rc_vote_manifest_url`
- input: `keys_url`
- checkout the project repository
- optionally present a signed bootstrap one-liner in the workflow summary or RC email
- run `buildish-release-tooling verify-rc <url> <keys-url>`
- write:
  - markdown summary
  - JSON report
  - optional downloaded inputs and normalized comparison outputs as workflow artifacts

The workflow should not require:

- write-capable GitHub permissions
- publish tokens
- mutation of tags, releases, branches, or SVN state

## Developer Machine Shape

Recommended expectations:

- supported on Linux and macOS
- uses temp directories by default
- uses isolated GPG home or `gpgv`
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

Each artifact should get a verdict record with:

- artifact ID or filename
- artifact kind
- remote locator
- authenticity result
- integrity result
- reproducibility result
- evidence, such as digest values, signature key IDs, or attestation identities

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
  secondary/
    __init__.py
    generic_file.py
    maven_repository.py
    python_distribution.py
    oci_image.py
    npm_package.py
```

This keeps verification as a sibling of `release`, not a subdomain inside it. The current `verify-rc` stub in command code should become a thin dispatcher into this verification package.

## Phased Implementation Plan

### Phase 1. Bootstrap and source verification

- change CLI input to `rc_vote_manifest_url`
- require explicit `keys_url` argument
- add `asf_keys_url` to config
- make manifest generation record explicit KEYS URL instead of deriving it
- implement manifest verification
- implement source artifact verification
- implement signed bootstrap script generation
- emit JSON and markdown reports

This is the minimum useful and secure implementation.

### Phase 2. Generic secondary file verification

- add typed `generic-file` and `generic-file-with-openpgp`
- add typed secondary-artifact registration helper commands
- support GitHub Release asset mirrors
- support collection inventories referenced from the main manifest

This covers many convenience artifacts quickly.

### Phase 3. Maven repository verifier

- consume Nexus staging repository IDs and base URLs from typed registration fragments
- implement remote repository verification
- implement local repository comparison

This is probably the highest-value first ecosystem-specific secondary verifier.

### Phase 4. Python distribution verifier

- implement `python-distribution`
- support PyPI or TestPyPI file resolution and digest checks
- support PyPI attestations where present
- implement local rebuild comparison

### Phase 5. OCI and npm verifiers

- implement `oci-image`
- implement `npm-package`
- keep local reproducibility advisory first

### Phase 6. Reproducibility hardening

- add canonical comparison helpers
- allow per-artifact policy upgrades from advisory to required
- add more exact-match coverage over time

## Recommended Near-Term Decisions

I would make these decisions now:

1. `verify-rc` should be manifest-URL driven, not version-driven.
2. The KEYS URL should be a mandatory verifier argument.
3. `asf_keys_url` should be explicit project config and manifest cross-check material, not the bootstrap source of trust.
4. The manifest should remain data-only.
5. Project-specific commands should live in local config.
6. Authenticity and integrity are required.
7. Reproducibility is graded per artifact family.
8. Maven repository verification should be the first secondary-artifact family after generic files.
9. Phase 1 UX should use a signed bootstrap script rather than `uv` or local Python packaging setup.

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
