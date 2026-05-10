# Copyright 2026 The Apache Software Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Signed bootstrap-script helpers for the Phase 1b verify-rc UX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from apache_buildish_release_tooling.release.gpg_signing import detached_ascii_sign
from apache_buildish_release_tooling.release.source_artifact import sha512, write_sha512_file

VERIFY_RC_BOOTSTRAP_SCRIPT_NAME = "verify-rc-bootstrap.sh"


@dataclass(frozen=True)
class VerifyRcBootstrapArtifacts:
    """Generated bootstrap script plus its detached signature and checksum."""

    script_path: Path
    script_sha512: str
    script_sha512_path: Path
    script_signature_path: Path
    invoker_snippet: str


def build_verify_rc_bootstrap_artifacts(
    *,
    output_dir: Path,
    manifest_url: str,
    keys_url: str,
    gpg_home: Path,
) -> VerifyRcBootstrapArtifacts:
    """Write, checksum, sign, and describe the verify-rc bootstrap script."""

    output_dir.mkdir(parents=True, exist_ok=True)
    script_path = output_dir / VERIFY_RC_BOOTSTRAP_SCRIPT_NAME
    script_path.write_text(render_verify_rc_bootstrap_script(), encoding="utf-8")
    script_path.chmod(0o755)
    script_sha512 = sha512(script_path)
    script_sha512_path = write_sha512_file(script_path, script_sha512)
    script_signature_path = script_path.with_name(f"{script_path.name}.asc")
    detached_ascii_sign(gpg_home, script_path, script_signature_path)
    return VerifyRcBootstrapArtifacts(
        script_path=script_path,
        script_sha512=script_sha512,
        script_sha512_path=script_sha512_path,
        script_signature_path=script_signature_path,
        invoker_snippet=render_verify_rc_bootstrap_invoker(
            manifest_url=manifest_url,
            keys_url=keys_url,
        ),
    )


def render_verify_rc_bootstrap_script() -> str:
    """Render the generic reviewed bootstrap script shipped with each RC."""

    return dedent(
        """\
        #!/bin/sh
        set -eu

        usage() {
          printf 'usage: %s <rc-vote-manifest-url> <keys-url> [verify-rc args...]\\n' "$0" >&2
          exit 2
        }

        [ "$#" -ge 2 ] || usage

        manifest_url=$1
        keys_url=$2
        shift 2

        for tool in awk curl git gpg mktemp; do
          command -v "$tool" >/dev/null 2>&1 || {
            printf 'missing required tool: %s\\n' "$tool" >&2
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
              printf '%s\\n' "$candidate"
              return 0
            fi
          done
          printf 'python >= 3.11 required; tried python3.15, python3.14, python3.13, python3.12, python3.11, python3, python\\n' >&2
          return 1
        }

        python_bin=$(select_python)

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

        tooling_metadata=$(
          "$python_bin" - rc-vote-manifest.json "$keys_url" <<'PY'
        import json
        import sys
        from pathlib import Path

        manifest_path, expected_keys_url = sys.argv[1:3]
        if Path(manifest_path).stat().st_size > 25 * 1024 * 1024:
            raise SystemExit(f"manifest file is unexpectedly large: {manifest_path}")
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        manifest_keys_url = data["trust_roots"]["asf_keys"]["uri"]
        if manifest_keys_url != expected_keys_url:
            raise SystemExit(
                f"manifest KEYS URL mismatch: {manifest_keys_url!r} != {expected_keys_url!r}"
            )

        tooling = data["provenance"]["tooling"]
        repository_url = tooling.get("repository_url")
        if not isinstance(repository_url, str) or not repository_url:
            raise SystemExit("manifest provenance.tooling.repository_url is required")

        commit_sha = tooling.get("git_commit_sha")
        if not isinstance(commit_sha, str) or len(commit_sha) != 40:
            raise SystemExit("manifest provenance.tooling.git_commit_sha must be a full commit SHA")

        print(repository_url)
        print(commit_sha)
        PY
        )

        tooling_repo_url=$(printf '%s\\n' "$tooling_metadata" | awk 'NR==1 { print; exit }')
        tooling_commit=$(printf '%s\\n' "$tooling_metadata" | awk 'NR==2 { print; exit }')

        tooling_dir=$work_dir/buildish-release-tooling
        git clone --quiet "$tooling_repo_url" "$tooling_dir"
        git -C "$tooling_dir" checkout --quiet --detach "$tooling_commit"

        PYTHONPATH=$tooling_dir/src
        export PYTHONPATH
        exec "$python_bin" -m apache_buildish_release_tooling.release verify-rc \\
          --work-dir "$work_dir/verify-rc" \\
          "$manifest_url" \\
          "$keys_url" \\
          "$@"
        """
    )


def render_verify_rc_bootstrap_invoker(*, manifest_url: str, keys_url: str) -> str:
    """Render the inspectable POSIX invoker snippet for vote emails and drafts."""

    escaped_manifest_url = _shell_single_quote(manifest_url)
    escaped_keys_url = _shell_single_quote(keys_url)
    return dedent(
        f"""\
        /bin/sh -eu -c '
        manifest_url=$1
        keys_url=$2
        bootstrap_base_url=${{manifest_url%/*}}
        temp_dir=$(mktemp -d "${{TMPDIR:-/tmp}}/verify-rc.XXXXXX")
        cleanup() {{ rm -rf "$temp_dir"; }}
        trap cleanup EXIT HUP INT TERM
        cd "$temp_dir"

        curl -fsSLO "$bootstrap_base_url/{VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}"
        curl -fsSLO "$bootstrap_base_url/{VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}.sha512"
        curl -fsSLO "$bootstrap_base_url/{VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}.asc"
        curl -fsSL "$keys_url" -o KEYS

        if command -v sha512sum >/dev/null 2>&1; then
          sha512sum -c {VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}.sha512
        else
          shasum -a 512 -c {VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}.sha512
        fi

        GNUPGHOME=$temp_dir/gnupg
        export GNUPGHOME
        mkdir "$GNUPGHOME"
        chmod 700 "$GNUPGHOME"
        gpg --batch --quiet --import KEYS >/dev/null 2>&1
        gpg --batch --quiet --verify {VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}.asc {VERIFY_RC_BOOTSTRAP_SCRIPT_NAME} >/dev/null 2>&1

        chmod +x {VERIFY_RC_BOOTSTRAP_SCRIPT_NAME}
        exec ./{VERIFY_RC_BOOTSTRAP_SCRIPT_NAME} "$manifest_url" "$keys_url"
        ' sh {escaped_manifest_url} {escaped_keys_url}"""
    )


def _shell_single_quote(value: str) -> str:
    """Quote one string for safe single-quoted POSIX shell use."""

    return "'" + value.replace("'", "'\"'\"'") + "'"
