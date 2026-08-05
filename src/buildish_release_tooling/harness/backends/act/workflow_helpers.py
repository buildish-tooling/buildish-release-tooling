# Copyright 2026 The Buildish Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Workflow rewrite and generated shim helpers for the harness act backend."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import yaml

from buildish_release_tooling.harness.config import (
    ResolvedReleaseHarnessConfig,
    ResolvedRepositoryBinding,
)
from buildish_release_tooling.harness.models import (
    HarnessScenario,
    validate_harness_identifier,
)
from buildish_release_tooling.harness.runtime import HarnessWorkspace
from buildish_release_tooling.release.manifests import ReleaseManifestV1
from buildish_release_tooling.shared.parsing import (
    DEFAULT_MANIFEST_PARSE_MAX_BYTES,
    read_pydantic_json_file_bounded,
)
from buildish_release_tooling.harness.uv_shim import (
    render_uv_shim_script,
    uv_shim_config,
)
from buildish_release_tooling.harness.yaml_types import (
    YamlMapping,
    require_yaml_mapping,
)


def _bootstrap_step() -> YamlMapping:
    """Return the injected step that exports harness paths through `GITHUB_ENV`."""

    return {
        "name": "Harness bootstrap environment",
        "shell": "bash",
        "run": (
            'mkdir -p "$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses"\n'
            "{\n"
            '  printf \'PATH=%s/.buildish-release-harness/shims:%s\\n\' "$GITHUB_WORKSPACE" "$PATH"\n'
            "  printf 'BUILDISH_HARNESS_STATE_FILE=%s/.buildish-release-harness/shim-state.json\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_REAL_PATH=%s\\n' \"$PATH\"\n"
            "  printf 'BUILDISH_HARNESS_BASH_ENV_FILE=%s/.buildish-release-harness/bash-env.sh\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_SUMMARIES_DIR=%s/.buildish-release-harness/summaries\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_TOOLING_SOURCE_DIR=%s/.buildish-release-harness/repo-sources/buildish-tooling__buildish-release-tooling\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_ALLOW_NON_PRODUCTION_RELEASE_TARGETS=true\\n'\n"
            '  if [[ -n "${PYTHONPATH:-}" ]]; then\n'
            '    printf \'PYTHONPATH=%s/.buildish-release-harness/repo-sources/buildish-tooling__buildish-release-tooling/src:%s\\n\' "$GITHUB_WORKSPACE" "$PYTHONPATH"\n'
            "  else\n"
            "    printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/buildish-tooling__buildish-release-tooling/src\\n' \"$GITHUB_WORKSPACE\"\n"
            "  fi\n"
            '} >> "$GITHUB_ENV"\n'
            'gpg_key_file="$GITHUB_WORKSPACE/.buildish-release-harness/gpg-fixture/private.asc"\n'
            'if [[ -f "$gpg_key_file" ]]; then\n'
            "  {\n"
            "    printf 'BUILDISH_GPG_PRIVATE_KEY<<__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            '    cat "$gpg_key_file"\n'
            "    printf '__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            '  } >> "$GITHUB_ENV"\n'
            "fi\n"
        ),
    }


def _rewrite_step(
    *,
    job_id: str,
    step_payload: YamlMapping,
    step_index: int,
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_references: dict[str, str],
    real_cli_commands: set[str],
    generated_gpg_fixture: bool,
) -> YamlMapping:
    """Rewrite one workflow step for local harness execution."""

    uses = step_payload.get("uses")
    if (
        isinstance(uses, str)
        and uses.startswith("astral-sh/setup-uv@")
        and not real_cli_commands
    ):
        rewritten: YamlMapping = {
            key: value
            for key, value in step_payload.items()
            if key not in {"uses", "with"}
        }
        rewritten["uses"] = generated_action_references["setup-uv-noop"]
        return rewritten
    if isinstance(uses, str) and uses.startswith("actions/checkout@"):
        rewritten_checkout = _rewrite_checkout_step(
            step_payload,
            bindings,
            generated_action_references["local-checkout"],
        )
        if rewritten_checkout is not None:
            return rewritten_checkout
    if isinstance(uses, str) and uses.startswith("actions/upload-artifact@"):
        rewritten = dict(step_payload)
        rewritten["uses"] = generated_action_references["local-upload-artifact"]
        return rewritten
    if isinstance(uses, str) and uses.startswith("actions/download-artifact@"):
        rewritten = dict(step_payload)
        rewritten["uses"] = generated_action_references["local-download-artifact"]
        return rewritten
    if isinstance(uses, str) and uses.startswith("pypa/gh-action-pypi-publish@"):
        rewritten = dict(step_payload)
        rewritten["uses"] = generated_action_references["local-pypi-publish"]
        return rewritten
    if "run" not in step_payload:
        return dict(step_payload)
    step_id = _step_identifier(step_payload, step_index)
    rewritten = dict(step_payload)
    raw_run = rewritten.get("run")
    if isinstance(raw_run, str):
        rewritten_run = _rewrite_pypi_commands(raw_run)
        if generated_gpg_fixture:
            rewritten_run = re.sub(
                r'^\s*--expected-signing-fingerprint "\$EXPECTED_SIGNING_FINGERPRINT" \\\n',
                "",
                rewritten_run,
                flags=re.MULTILINE,
            )
        rewritten["run"] = rewritten_run
    env = _optional_step_mapping(
        rewritten.get("env"),
        source=f"workflow step {step_id} env",
    )
    if generated_gpg_fixture:
        env.pop("BUILDISH_GPG_PRIVATE_KEY", None)
        env.pop("BUILDISH_GPG_PASSPHRASE", None)
    env["BUILDISH_HARNESS_JOB_ID"] = job_id
    env["BUILDISH_HARNESS_STEP_ID"] = step_id
    rewritten["env"] = env
    return rewritten


def _rewrite_checkout_step(
    step_payload: YamlMapping,
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_reference: str,
) -> YamlMapping | None:
    """Rewrite one `actions/checkout` step to the generated local composite action."""

    with_payload = _optional_step_mapping(
        step_payload.get("with"),
        source="workflow actions/checkout with",
    )
    repository_id = str(
        with_payload.get("repository", bindings.self_repository.repository_id)
    )
    source_binding: ResolvedRepositoryBinding | None = None
    mode: str | None = None
    if "repository" not in with_payload:
        if bindings.self_repository.local_checkout_mode == "when_repository_omitted":
            source_binding = bindings.self_repository
            mode = "local-git-clone"
    else:
        source_binding = bindings.repository_overrides.get(repository_id)
        if (
            source_binding is not None
            and source_binding.local_checkout_mode == "always"
        ):
            mode = "local-source-tree"
    if source_binding is None or mode is None:
        return None
    rewritten: YamlMapping = {
        key: value for key, value in step_payload.items() if key not in {"uses", "with"}
    }
    rewritten["uses"] = generated_action_reference
    rewritten["with"] = {
        "source_path": f".buildish-release-harness/repo-sources/{_repository_slug(repository_id)}",
        "path": str(with_payload.get("path", ".")),
        "ref": str(with_payload.get("ref", "")),
        "mode": mode,
    }
    return rewritten


def _generated_action_references() -> dict[str, str]:
    """Return stable `uses:` references for generated harness actions from the repo root."""

    return {
        "local-checkout": "./.buildish-release-harness/actions/local-checkout",
        "local-download-artifact": "./.buildish-release-harness/actions/local-download-artifact",
        "local-upload-artifact": "./.buildish-release-harness/actions/local-upload-artifact",
        "local-pypi-publish": "./.buildish-release-harness/actions/local-pypi-publish",
        "setup-uv-noop": "./.buildish-release-harness/actions/setup-uv-noop",
    }


def _rewrite_pypi_commands(script: str) -> str:
    """Route package-index reads and provenance generation to harness-local fixtures."""

    integrity_base_url = "https://integrity.buildish-release-harness.invalid/integrity"
    repository_argument = (
        "--repository-api-url "
        '"file://$GITHUB_WORKSPACE/.buildish-release-harness/pypi-index/api"'
    )
    project_url_argument = (
        "--project-url-template "
        "'https://packages.buildish-release-harness.invalid/project/{project}/{version}/'"
    )
    rewritten = re.sub(
        r"--repository-api-url\s+\S+",
        repository_argument,
        script,
    )
    rewritten = re.sub(
        r"--project-url-template\s+\S+",
        project_url_argument,
        rewritten,
    )
    rewritten = re.sub(
        r"https://(?:test\.)?pypi\.org/integrity",
        integrity_base_url,
        rewritten,
    )
    command_marker = (
        "bash buildish-release-tooling/release-tooling.sh verify-pypi-publication \\\n"
    )
    if command_marker in rewritten and repository_argument not in rewritten:
        rewritten = rewritten.replace(
            command_marker,
            (
                f"{command_marker}  {repository_argument} \\\n"
                f"  {project_url_argument} \\\n"
            ),
        )
    return rewritten.replace(
        "bash buildish-release-tooling/release-tooling.sh verify-pypi-attestations",
        ".buildish-release-harness/tools/verify-pypi-attestations.sh",
    )


def _validate_retained_release_manifest_artifacts(
    workspace: HarnessWorkspace,
    *,
    require_promoted_manifest: bool = False,
) -> None:
    """Validate retained promoted manifests and their service-isolated evidence."""

    artifact_root = workspace.harness_dir / "workflow-artifacts"
    artifact_dirs = sorted(artifact_root.glob("promoted-release-manifest-*"))
    if require_promoted_manifest and not artifact_dirs:
        raise ValueError(
            "successful promotion must retain a promoted release manifest artifact"
        )
    for artifact_dir in artifact_dirs:
        manifest_path = artifact_dir / "release-manifest-v1.json"
        manifest = read_pydantic_json_file_bounded(
            ReleaseManifestV1,
            manifest_path,
            max_bytes=DEFAULT_MANIFEST_PARSE_MAX_BYTES,
        )
        serialized = manifest_path.read_text(encoding="utf-8")
        if "pypi.org" in serialized or "test.pypi.org" in serialized:
            raise ValueError(
                "retained harness release manifest references a production PyPI service"
            )
        synthetic_publication_urls = [
            publication.uri
            for publication in manifest.secondary_publications
            if publication.target_kind == "pypi"
        ]
        if synthetic_publication_urls and any(
            not (urlparse(url).hostname or "").endswith(".invalid")
            for url in synthetic_publication_urls
        ):
            raise ValueError(
                "retained harness PyPI publication must use an explicit .invalid service host"
            )
        attestation_results = [
            result
            for result in manifest.verification_results
            if result.kind == "pypi-publish-attestation"
        ]
        if attestation_results and any(
            urlparse(result.uri).hostname != "github.com"
            or "/releases/download/" not in urlparse(result.uri).path
            or not (
                urlparse(result.claims.get("integrity_base_url", "")).hostname or ""
            ).endswith(".invalid")
            for result in attestation_results
        ):
            raise ValueError(
                "retained harness PyPI evidence must bind a .invalid source to a GitHub Release asset"
            )


def _step_identifier(step_payload: YamlMapping, step_index: int) -> str:
    """Return a stable identifier for one workflow step."""

    raw_identifier = step_payload.get("id")
    if isinstance(raw_identifier, str) and raw_identifier:
        return validate_harness_identifier(
            raw_identifier, field_name="workflow step id"
        )
    raw_name = step_payload.get("name")
    if isinstance(raw_name, str) and raw_name:
        normalized = re.sub(r"[^A-Za-z0-9]+", "-", raw_name).strip("-").lower()
        if normalized:
            return normalized
    return f"step-{step_index}"


def _job_status_step(job_id: str) -> YamlMapping:
    """Return the injected terminal step that records the job outcome."""

    return {
        "name": "Harness record job status",
        "if": "${{ always() }}",
        "shell": "bash",
        "env": {
            "BUILDISH_HARNESS_JOB_STATUS": "${{ job.status }}",
        },
        "run": (
            "printf '%s\\n' \"$BUILDISH_HARNESS_JOB_STATUS\" > "
            f'"$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses/{job_id}.status"\n'
        ),
    }


def _optional_step_mapping(raw_payload: object, *, source: str) -> YamlMapping:
    """Return an optional workflow step mapping or an empty mapping."""

    if raw_payload is None:
        return {}
    return require_yaml_mapping(raw_payload, source=source)


def _write_setup_uv_noop_action(workspace: HarnessWorkspace) -> None:
    """Write the generated no-op composite action used to replace `setup-uv`."""

    action_dir = workspace.actions_dir / "setup-uv-noop"
    action_dir.mkdir(parents=True, exist_ok=True)
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Buildish harness setup-uv noop",
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": "printf 'buildish-release-harness: setup-uv no-op\\n'",
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_local_checkout_action(workspace: HarnessWorkspace) -> None:
    """Write the generated composite action that materializes local checkout overrides."""

    action_dir = workspace.actions_dir / "local-checkout"
    action_dir.mkdir(parents=True, exist_ok=True)
    script_path = action_dir / "local-checkout.sh"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'source_path="${INPUT_SOURCE_PATH:?}"',
                'mode="${INPUT_MODE:?}"',
                'target_path="${INPUT_PATH:-.}"',
                'ref="${INPUT_REF:-}"',
                'if [[ "$source_path" != /* ]]; then',
                '  source_path="$GITHUB_WORKSPACE/$source_path"',
                "fi",
                'if [[ "$target_path" == "." ]]; then',
                "  exit 0",
                "fi",
                'destination="$GITHUB_WORKSPACE/$target_path"',
                'rm -rf "$destination"',
                'mkdir -p "$(dirname "$destination")"',
                'case "$mode" in',
                "  local-git-clone)",
                '    git clone --local "$source_path" "$destination"',
                '    if [[ -n "$ref" ]]; then',
                '      git -C "$destination" checkout "$ref"',
                "    fi",
                "    ;;",
                "  local-source-tree)",
                '    mkdir -p "$destination"',
                '    cp -a "$source_path"/. "$destination"/',
                '    rm -rf "$destination/.git"',
                "    ;;",
                "  *)",
                '    printf "unsupported harness checkout mode: %s\\n" "$mode" >&2',
                "    exit 2",
                "    ;;",
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Buildish harness local checkout",
                "inputs": {
                    "source_path": {"required": True},
                    "path": {"required": False},
                    "ref": {"required": False},
                    "mode": {"required": True},
                },
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": 'bash "$GITHUB_ACTION_PATH/local-checkout.sh"',
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_local_artifact_actions(workspace: HarnessWorkspace) -> None:
    """Write deterministic local substitutes for same-run workflow artifacts."""

    _write_local_artifact_action(
        workspace,
        action_name="local-upload-artifact",
        script=(
            'name="${INPUT_NAME:?}"\n'
            'source_path="${INPUT_PATH:?}"\n'
            'overwrite="${INPUT_OVERWRITE:-false}"\n'
            '[[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || '
            "{ printf 'invalid artifact name: %s\\n' \"$name\" >&2; exit 2; }\n"
            'store="$GITHUB_WORKSPACE/.buildish-release-harness/workflow-artifacts/$name"\n'
            'if [[ -e "$store" ]]; then\n'
            '  if [[ "$overwrite" == "true" ]]; then\n'
            '    rm -rf "$store"\n'
            "  else\n"
            "    printf 'workflow artifact already exists: %s\\n' \"$name\" >&2\n"
            "    exit 2\n"
            "  fi\n"
            "fi\n"
            '[[ -e "$source_path" ]] || '
            "{ printf 'workflow artifact source does not exist: %s\\n' \"$source_path\" >&2; exit 2; }\n"
            'mkdir -p "$store"\n'
            'if [[ -d "$source_path" ]]; then\n'
            '  cp -a "$source_path"/. "$store"/\n'
            "else\n"
            '  cp -a "$source_path" "$store"/\n'
            "fi\n"
        ),
    )
    _write_local_artifact_action(
        workspace,
        action_name="local-download-artifact",
        script=(
            'name="${INPUT_NAME:?}"\n'
            'target_path="${INPUT_PATH:-.}"\n'
            '[[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || '
            "{ printf 'invalid artifact name: %s\\n' \"$name\" >&2; exit 2; }\n"
            'store="$GITHUB_WORKSPACE/.buildish-release-harness/workflow-artifacts/$name"\n'
            '[[ -d "$store" ]] || '
            "{ printf 'workflow artifact does not exist: %s\\n' \"$name\" >&2; exit 2; }\n"
            'mkdir -p "$target_path"\n'
            'cp -a "$store"/. "$target_path"/\n'
        ),
    )


def _write_local_pypi_publish_action(workspace: HarnessWorkspace) -> None:
    """Write a local substitute for Trusted Publisher package uploads."""

    action_dir = workspace.actions_dir / "local-pypi-publish"
    action_dir.mkdir(parents=True, exist_ok=True)
    script_path = action_dir / "publish.py"
    script_path.write_text(
        """from __future__ import annotations

import email
import hashlib
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

packages_dir = Path(os.environ["INPUT_PACKAGES-DIR"])
wheel_paths = sorted(packages_dir.glob("*.whl"))
distribution_paths = sorted(
    path for path in packages_dir.iterdir()
    if path.is_file() and path.name.endswith((".whl", ".tar.gz"))
)
if len(wheel_paths) != 1 or len(distribution_paths) != 2:
    raise SystemExit("harness package publication requires exactly one wheel and one sdist")
with zipfile.ZipFile(wheel_paths[0]) as wheel:
    metadata_names = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        raise SystemExit("harness wheel must contain exactly one METADATA file")
    metadata = email.message_from_bytes(wheel.read(metadata_names[0]))
project_name = metadata["Name"]
version = metadata["Version"]
if not project_name or not version:
    raise SystemExit("harness wheel metadata lacks project name or version")
normalized_name = re.sub(r"[-_.]+", "-", project_name).lower()
workspace = Path(os.environ["GITHUB_WORKSPACE"])
index_root = workspace / ".buildish-release-harness" / "pypi-index"
file_root = index_root / "files" / normalized_name / version
file_root.mkdir(parents=True, exist_ok=True)
entries = []
for source in distribution_paths:
    destination = file_root / source.name
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        raise SystemExit(f"conflicting harness package-index file: {source.name}")
    shutil.copyfile(source, destination)
    payload = destination.read_bytes()
    entries.append(
        {
            "filename": source.name,
            "digests": {"sha256": hashlib.sha256(payload).hexdigest()},
            "size": len(payload),
            "url": f"https://files.pythonhosted.invalid/{normalized_name}/{version}/{source.name}",
        }
    )
endpoint = index_root / "api" / normalized_name / version / "json"
endpoint.parent.mkdir(parents=True, exist_ok=True)
endpoint.write_text(
    json.dumps(
        {"info": {"name": project_name, "version": version}, "urls": entries},
        indent=2,
        sort_keys=True,
    )
    + "\\n",
    encoding="utf-8",
)
""",
        encoding="utf-8",
    )
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": "Buildish harness local Python package publish",
                "inputs": {
                    "packages-dir": {"required": True},
                    "repository-url": {"required": False},
                    "skip-existing": {"required": False},
                },
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": 'python3 "$GITHUB_ACTION_PATH/publish.py"',
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_local_package_attestation_verifier(workspace: HarnessWorkspace) -> None:
    """Write deterministic package provenance for service-isolated composition tests."""

    tool_dir = workspace.harness_dir / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    script_path = tool_dir / "verify-pypi-attestations.sh"
    script_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
provenance_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provenance-dir)
      provenance_dir="$2"
      shift 2
      ;;
    --attempts|--retry-delay|--total-timeout|--integrity-api-url)
      shift 2
      ;;
    *)
      break
      ;;
  esac
done
version="${1:?missing version}"
shift
shim_python="python3"
if [[ -n "${GITHUB_WORKSPACE:-}" && -x "$GITHUB_WORKSPACE/.venv/bin/python" ]]; then
  shim_python="$GITHUB_WORKSPACE/.venv/bin/python"
fi
"$shim_python" - "$version" "$provenance_dir" "$MANIFEST_PATH" "$@" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

from buildish_release_tooling.release.config import load_release_config
from buildish_release_tooling.release.publications.pypi.config import PyPiPublicationConfig
from buildish_release_tooling.release.publications.pypi.distributions import normalized_pypi_version

version, provenance_dir_text, manifest_path_text, *distributions = sys.argv[1:]
pypi_version = normalized_pypi_version(version)
integrity_base_url = "https://integrity.buildish-release-harness.invalid/integrity"
workspace = Path(os.environ["GITHUB_WORKSPACE"])
config_path = Path(
    os.environ.get(
        "BUILDISH_COMPONENT_CONFIG_PATH",
        workspace / "buildish-release-tooling" / "release-config.yaml",
    )
)
config = load_release_config(config_path)
targets = [
    target
    for target in config.publication.secondary
    if isinstance(target, PyPiPublicationConfig)
]
if len(targets) != 1:
    raise SystemExit("harness attestation verification requires one configured PyPI target")
target = targets[0]
component = config.component.id
project = target.project_name
repository = target.trusted_publisher.repository
workflow = target.trusted_publisher.workflow
environment = target.trusted_publisher.environment
provenance_dir = Path(provenance_dir_text)
provenance_dir.mkdir(parents=True, exist_ok=True)
files = []
for distribution_text in distributions:
    distribution = Path(distribution_text)
    distribution_sha256 = hashlib.sha256(distribution.read_bytes()).hexdigest()
    source_provenance_url = f"{integrity_base_url.rstrip('/')}/{project}/{pypi_version}/{distribution.name}/provenance"
    evidence_path = provenance_dir / (
        "buildish-verification-evidence--"
        f"{distribution.name}.publish-attestations.json"
    )
    evidence_path.write_text(
        json.dumps(
            {
                "kind": "pypi-publish-attestation-evidence",
                "schema_version": "1",
                "publisher": {
                    "kind": "GitHub",
                    "repository": repository,
                    "workflow": workflow,
                    "environment": environment,
                },
                "distribution_filename": distribution.name,
                "distribution_sha256": distribution_sha256,
                "source_provenance_url": source_provenance_url,
                "attestations": [{"harness": "synthetic-pypi-publish-attestation"}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\\n",
        encoding="utf-8",
    )
    files.append(
        {
            "filename": distribution.name,
            "distribution_sha256": distribution_sha256,
            "evidence_filename": evidence_path.name,
            "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "evidence_size_bytes": evidence_path.stat().st_size,
            "source_provenance_url": source_provenance_url,
            "publish_attestation_count": 1,
        }
    )
Path(manifest_path_text).write_text(
    json.dumps(
        {
            "schema_version": "1",
            "kind": "pypi-attestation-verification",
            "component": component,
            "action": "verify-pypi-attestations",
            "project_name": project,
            "version": version,
            "integrity_base_url": integrity_base_url.rstrip("/"),
            "publisher": {
                "kind": "GitHub",
                "repository": repository,
                "workflow": workflow,
                "environment": environment,
            },
            "files": sorted(files, key=lambda item: item["filename"]),
        },
        indent=2,
        sort_keys=True,
    )
    + "\\n",
    encoding="utf-8",
)
PY
""",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _write_local_artifact_action(
    workspace: HarnessWorkspace,
    *,
    action_name: str,
    script: str,
) -> None:
    """Write one local workflow-artifact composite action."""

    action_dir = workspace.actions_dir / action_name
    action_dir.mkdir(parents=True, exist_ok=True)
    script_path = action_dir / "run.sh"
    script_path.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n" + script,
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)
    (action_dir / "action.yml").write_text(
        yaml.safe_dump(
            {
                "name": f"Buildish harness {action_name}",
                "inputs": {
                    "name": {"required": True},
                    "path": {"required": True},
                    "retention-days": {"required": False},
                    "if-no-files-found": {"required": False},
                    "overwrite": {"required": False},
                },
                "runs": {
                    "using": "composite",
                    "steps": [
                        {
                            "shell": "bash",
                            "run": 'bash "$GITHUB_ACTION_PATH/run.sh"',
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_bash_shim(workspace: HarnessWorkspace) -> None:
    """Write the `bash` shim that redirects step summaries and enables `BASH_ENV` hooks."""

    script_path = workspace.shims_dir / "bash"
    script_path.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                "set -euo pipefail",
                'real_path="${BUILDISH_HARNESS_REAL_PATH:-/usr/bin:/bin}"',
                'real_bash="$(PATH="$real_path" command -v bash || true)"',
                'if [[ -z "$real_bash" ]]; then',
                '  printf "buildish-release-harness: could not locate real bash\\n" >&2',
                "  exit 127",
                "fi",
                'original_summary="${GITHUB_STEP_SUMMARY:-}"',
                'capture_summary=""',
                'if [[ -n "${BUILDISH_HARNESS_SUMMARIES_DIR:-}" && -n "${BUILDISH_HARNESS_JOB_ID:-}" && -n "${BUILDISH_HARNESS_STEP_ID:-}" ]]; then',
                '  capture_summary="$BUILDISH_HARNESS_SUMMARIES_DIR/${BUILDISH_HARNESS_JOB_ID}__${BUILDISH_HARNESS_STEP_ID}.md"',
                '  mkdir -p "$(dirname "$capture_summary")"',
                '  : > "$capture_summary"',
                '  export BUILDISH_ORIGINAL_GITHUB_STEP_SUMMARY="$original_summary"',
                '  export GITHUB_STEP_SUMMARY="$capture_summary"',
                "fi",
                'if [[ -n "${BUILDISH_HARNESS_BASH_ENV_FILE:-}" ]]; then',
                '  export BASH_ENV="$BUILDISH_HARNESS_BASH_ENV_FILE"',
                "fi",
                "set +e",
                '"$real_bash" "$@"',
                'status="$?"',
                "set -e",
                'if [[ -n "$capture_summary" && -n "$original_summary" && "$capture_summary" != "$original_summary" ]]; then',
                '  cat "$capture_summary" > "$original_summary"',
                "fi",
                'exit "$status"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _write_generic_tool_shims(
    workspace: HarnessWorkspace, scenario: HarnessScenario
) -> None:
    """Write container-safe executable shims for all intercepted non-shell tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"gh", "docker", "java", "javac"})
    for tool in tools:
        validate_harness_identifier(tool, field_name="tool behavior name")
        script_path = workspace.shims_dir / tool
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    'shim_python="python3"',
                    (
                        'if [[ -n "${GITHUB_WORKSPACE:-}" '
                        '&& -x "$GITHUB_WORKSPACE/.venv/bin/python" ]]; then'
                    ),
                    '  shim_python="$GITHUB_WORKSPACE/.venv/bin/python"',
                    "fi",
                    (
                        'exec "$shim_python" -m '
                        "buildish_release_tooling.harness.shim_entrypoint "
                        f'{json.dumps(tool)} "$@"'
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script_path.chmod(script_path.stat().st_mode | 0o111)


def _render_uv_shim_script(real_cli_commands: list[str]) -> str:
    """Return the generated `uv` shim script for one act workspace."""

    return render_uv_shim_script(
        uv_shim_config(
            shim_python_executable="python3",
            real_cli_commands=real_cli_commands,
            passthrough_python_install=True,
        )
    )


def _write_uv_shim(workspace: HarnessWorkspace, real_cli_commands: list[str]) -> None:
    """Write the `uv` shim used by the rewritten workflows."""

    script_path = workspace.shims_dir / "uv"
    script_path.write_text(
        _render_uv_shim_script(real_cli_commands),
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | 0o111)


def _repository_slug(repository_id: str) -> str:
    """Return a filesystem-safe repository slug used under `.buildish-release-harness/repo-sources`."""

    return repository_id.replace("/", "__")
