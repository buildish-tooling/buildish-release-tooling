# Copyright 2026 The Apache Software Foundation
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

"""Workflow rewriting helpers for the `act` harness backend."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apache_buildish_release_tooling.harness.config import (
    ResolvedReleaseHarnessConfig,
    ResolvedRepositoryBinding,
)
from apache_buildish_release_tooling.harness.models import HarnessScenario
from apache_buildish_release_tooling.harness.runtime import HarnessWorkspace
from apache_buildish_release_tooling.harness.uv_shim import render_uv_shim_script, uv_shim_config


@dataclass(frozen=True)
class WorkflowJobDefinition:
    """Normalized job metadata extracted from one workflow YAML file."""

    id: str
    needs: list[str]


class _GithubActionsYamlLoader(yaml.SafeLoader):
    """YAML loader that keeps GitHub Actions keys like `on` as plain strings."""


class _GithubActionsYamlDumper(yaml.SafeDumper):
    """YAML dumper that renders multiline shell snippets as literal blocks."""


_GithubActionsYamlLoader.yaml_implicit_resolvers = copy.deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for _first_char, _resolvers in list(_GithubActionsYamlLoader.yaml_implicit_resolvers.items()):
    _GithubActionsYamlLoader.yaml_implicit_resolvers[_first_char] = [
        (tag, pattern) for tag, pattern in _resolvers if tag != "tag:yaml.org,2002:bool"
    ]
yaml.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
    Loader=_GithubActionsYamlLoader,
)


def _represent_workflow_string(
    dumper: _GithubActionsYamlDumper,
    value: str,
) -> yaml.nodes.ScalarNode:
    """Represent multiline workflow strings as literal blocks for readable `run:` scripts."""

    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_GithubActionsYamlDumper.add_representer(str, _represent_workflow_string)


def _load_github_actions_yaml(path: Path) -> dict[str, Any]:
    """Load GitHub Actions YAML without converting keys like `on` into booleans."""

    payload = yaml.load(  # noqa: S506
        path.read_text(encoding="utf-8"),
        Loader=_GithubActionsYamlLoader,  # noqa: S506
    )
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"workflow {path} must be a top-level mapping")
    return payload


def _load_job_definitions(workflow_path: Path) -> list[WorkflowJobDefinition]:
    """Load one workflow YAML file and extract the declared job graph."""

    payload = _load_github_actions_yaml(workflow_path)
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"workflow {workflow_path} does not define a jobs mapping")
    definitions: list[WorkflowJobDefinition] = []
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        definitions.append(
            WorkflowJobDefinition(
                id=str(job_id),
                needs=_normalize_needs(job_payload.get("needs")),
            )
        )
    return definitions


def _normalize_needs(raw_needs: Any) -> list[str]:
    """Normalize one workflow `needs` field into a flat string list."""

    if raw_needs is None:
        return []
    if isinstance(raw_needs, str):
        return [raw_needs]
    if isinstance(raw_needs, list):
        return [str(item) for item in raw_needs]
    raise ValueError(f"unsupported needs value: {raw_needs!r}")


def _topological_job_ids(job_definitions: list[WorkflowJobDefinition]) -> list[str]:
    """Return workflow job identifiers in dependency order."""

    pending = {definition.id: definition for definition in job_definitions}
    ordered: list[str] = []
    resolved: set[str] = set()
    while pending:
        progress_made = False
        for definition in job_definitions:
            if definition.id not in pending:
                continue
            if all(need in resolved for need in definition.needs):
                ordered.append(definition.id)
                resolved.add(definition.id)
                del pending[definition.id]
                progress_made = True
        if not progress_made:
            unresolved = ", ".join(sorted(pending))
            raise RuntimeError(f"cyclic or unresolved workflow jobs: {unresolved}")
    return ordered


def _rewrite_workflow(
    *,
    workspace: HarnessWorkspace,
    workflow_path: Path,
    scenario_env: dict[str, str],
    bindings: ResolvedReleaseHarnessConfig,
    real_cli_commands: set[str],
    generated_gpg_fixture: bool,
) -> Path:
    """Rewrite a workflow for deterministic local execution through `act`."""

    payload = _load_github_actions_yaml(workflow_path)
    payload.setdefault("env", {})
    if not isinstance(payload["env"], dict):
        raise ValueError(f"workflow {workflow_path} has a non-mapping env block")
    payload["env"] = {**payload["env"], **scenario_env}
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"workflow {workflow_path} does not define a jobs mapping")
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        original_steps = list(job_payload.get("steps") or [])
        rewritten_steps: list[dict[str, Any]] = [_bootstrap_step()]
        generated_action_references = _generated_action_references()
        for index, step_payload in enumerate(original_steps, start=1):
            if not isinstance(step_payload, dict):
                raise ValueError(f"workflow job {job_id} contains a non-mapping step")
            rewritten_steps.append(
                _rewrite_step(
                    job_id=str(job_id),
                    step_payload=step_payload,
                    step_index=index,
                    bindings=bindings,
                    generated_action_references=generated_action_references,
                    real_cli_commands=real_cli_commands,
                    generated_gpg_fixture=generated_gpg_fixture,
                )
            )
        rewritten_steps.append(_job_status_step(str(job_id)))
        job_payload["steps"] = rewritten_steps
    destination = workspace.root / ".github" / "workflows" / workflow_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_copy = destination.with_name(f"{destination.stem}.original{destination.suffix}")
    original_copy.write_text(workflow_path.read_text(encoding="utf-8"), encoding="utf-8")
    destination.write_text(
        _render_rewritten_workflow_yaml(
            payload,
            original_workflow_path=workflow_path,
            original_copy_name=original_copy.name,
        ),
        encoding="utf-8",
    )
    return destination


def _dump_workflow_yaml(payload: dict[str, Any]) -> str:
    """Dump rewritten workflow YAML while keeping the GitHub Actions `on` key literal."""

    rendered = yaml.dump(
        payload,
        Dumper=_GithubActionsYamlDumper,
        sort_keys=False,
        width=1000,
    )
    return re.sub(r"(?m)^([ ]*)['\"]on['\"]:$", r"\1on:", rendered)


def _render_rewritten_workflow_yaml(
    payload: dict[str, Any],
    *,
    original_workflow_path: Path,
    original_copy_name: str,
) -> str:
    """Render one rewritten workflow with a prominent harness-generated header comment."""

    header = "\n".join(
        [
            "# WARNING: This is not the original workflow file.",
            "# This file was generated by buildish-release-harness for local test execution.",
            f"# Original workflow source: {original_workflow_path}",
            f"# Verbatim original copy in this directory: {original_copy_name}",
            "",
        ]
    )
    return header + _dump_workflow_yaml(payload)


def _bootstrap_step() -> dict[str, Any]:
    """Return the injected step that exports harness paths through `GITHUB_ENV`."""

    return {
        "name": "Harness bootstrap environment",
        "shell": "bash",
        "run": (
            "mkdir -p \"$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses\"\n"
            "{\n"
            "  printf 'PATH=%s/.buildish-release-harness/shims:%s\\n' \"$GITHUB_WORKSPACE\" \"$PATH\"\n"
            "  printf 'BUILDISH_HARNESS_STATE_FILE=%s/.buildish-release-harness/shim-state.json\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_REAL_PATH=%s\\n' \"$PATH\"\n"
            "  printf 'BUILDISH_HARNESS_BASH_ENV_FILE=%s/.buildish-release-harness/bash-env.sh\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_SUMMARIES_DIR=%s/.buildish-release-harness/summaries\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_HARNESS_TOOLING_SOURCE_DIR=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling\\n' \"$GITHUB_WORKSPACE\"\n"
            "  printf 'BUILDISH_ALLOW_NON_PRODUCTION_RELEASE_TARGETS=true\\n'\n"
            "  if [[ -n \"${PYTHONPATH:-}\" ]]; then\n"
            "    printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src:%s\\n' \"$GITHUB_WORKSPACE\" \"$PYTHONPATH\"\n"
            "  else\n"
            "    printf 'PYTHONPATH=%s/.buildish-release-harness/repo-sources/apache__buildish-release-tooling/src\\n' \"$GITHUB_WORKSPACE\"\n"
            "  fi\n"
            "} >> \"$GITHUB_ENV\"\n"
            "gpg_key_file=\"$GITHUB_WORKSPACE/.buildish-release-harness/gpg-fixture/private.asc\"\n"
            "if [[ -f \"$gpg_key_file\" ]]; then\n"
            "  {\n"
            "    printf 'BUILDISH_GPG_PRIVATE_KEY<<__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            "    cat \"$gpg_key_file\"\n"
            "    printf '__BUILDISH_HARNESS_GPG_KEY__\\n'\n"
            "  } >> \"$GITHUB_ENV\"\n"
            "fi\n"
        ),
    }


def _rewrite_step(
    *,
    job_id: str,
    step_payload: dict[str, Any],
    step_index: int,
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_references: dict[str, str],
    real_cli_commands: set[str],
    generated_gpg_fixture: bool,
) -> dict[str, Any]:
    """Rewrite one workflow step for local harness execution."""

    uses = step_payload.get("uses")
    if (
        isinstance(uses, str)
        and uses.startswith("astral-sh/setup-uv@")
        and not real_cli_commands
    ):
        rewritten = {key: value for key, value in step_payload.items() if key not in {"uses", "with"}}
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
    if "run" not in step_payload:
        return dict(step_payload)
    step_id = _step_identifier(step_payload, step_index)
    rewritten = dict(step_payload)
    env = dict(rewritten.get("env") or {})
    if generated_gpg_fixture:
        env.pop("BUILDISH_GPG_PRIVATE_KEY", None)
    env["BUILDISH_HARNESS_JOB_ID"] = job_id
    env["BUILDISH_HARNESS_STEP_ID"] = step_id
    rewritten["env"] = env
    return rewritten


def _rewrite_checkout_step(
    step_payload: dict[str, Any],
    bindings: ResolvedReleaseHarnessConfig,
    generated_action_reference: str,
) -> dict[str, Any] | None:
    """Rewrite one `actions/checkout` step to the generated local composite action."""

    with_payload = dict(step_payload.get("with") or {})
    repository_id = str(with_payload.get("repository", bindings.self_repository.repository_id))
    source_binding: ResolvedRepositoryBinding | None = None
    mode: str | None = None
    if "repository" not in with_payload:
        if bindings.self_repository.local_checkout_mode == "when_repository_omitted":
            source_binding = bindings.self_repository
            mode = "local-git-clone"
    else:
        source_binding = bindings.repository_overrides.get(repository_id)
        if source_binding is not None and source_binding.local_checkout_mode == "always":
            mode = "local-source-tree"
    if source_binding is None or mode is None:
        return None
    rewritten = {key: value for key, value in step_payload.items() if key not in {"uses", "with"}}
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
        "setup-uv-noop": "./.buildish-release-harness/actions/setup-uv-noop",
    }


def _step_identifier(step_payload: dict[str, Any], step_index: int) -> str:
    """Return a stable identifier for one workflow step."""

    raw_identifier = step_payload.get("id")
    if isinstance(raw_identifier, str) and raw_identifier:
        return raw_identifier
    raw_name = step_payload.get("name")
    if isinstance(raw_name, str) and raw_name:
        normalized = re.sub(r"[^A-Za-z0-9]+", "-", raw_name).strip("-").lower()
        if normalized:
            return normalized
    return f"step-{step_index}"


def _job_status_step(job_id: str) -> dict[str, Any]:
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
            f"\"$GITHUB_WORKSPACE/.buildish-release-harness/job-statuses/{job_id}.status\"\n"
        ),
    }


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
                '  local-git-clone)',
                '    git clone --local "$source_path" "$destination"',
                '    if [[ -n "$ref" ]]; then',
                '      git -C "$destination" checkout "$ref"',
                "    fi",
                "    ;;",
                '  local-source-tree)',
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


def _write_generic_tool_shims(workspace: HarnessWorkspace, scenario: HarnessScenario) -> None:
    """Write container-safe executable shims for all intercepted non-shell tools."""

    tools = sorted(set(scenario.tool_behaviors) | {"gh", "docker", "java", "javac"})
    for tool in tools:
        script_path = workspace.shims_dir / tool
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "exec python3 -m apache_buildish_release_tooling.harness.shim_entrypoint "
                    f"{json.dumps(tool)} \"$@\"",
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


def _act_step_order_by_job(active_workflow_path: Path) -> dict[str, list[str]]:
    """Return original step identifiers in workflow order for each rewritten job."""

    payload = _load_github_actions_yaml(active_workflow_path)
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    step_order_by_job: dict[str, list[str]] = {}
    for job_id, job_payload in jobs.items():
        if not isinstance(job_payload, dict):
            continue
        step_ids: list[str] = []
        for step_payload in list(job_payload.get("steps") or []):
            if not isinstance(step_payload, dict):
                continue
            env = step_payload.get("env")
            if not isinstance(env, dict):
                continue
            step_id = env.get("BUILDISH_HARNESS_STEP_ID")
            if isinstance(step_id, str) and step_id:
                step_ids.append(step_id)
        step_order_by_job[str(job_id)] = step_ids
    return step_order_by_job
