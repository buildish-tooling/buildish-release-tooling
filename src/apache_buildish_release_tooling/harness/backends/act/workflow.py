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

from pathlib import Path

from apache_buildish_release_tooling.harness.config import ResolvedReleaseHarnessConfig
from apache_buildish_release_tooling.harness.models import validate_harness_identifier
from apache_buildish_release_tooling.harness.runtime import HarnessWorkspace
from apache_buildish_release_tooling.harness.yaml_types import YamlMapping, YamlValue, require_yaml_mapping
from apache_buildish_release_tooling.harness.backends.act.workflow_helpers import (
    _bootstrap_step,
    _generated_action_references,
    _job_status_step,
    _repository_slug,
    _render_uv_shim_script,
    _rewrite_step,
    _write_bash_shim,
    _write_generic_tool_shims,
    _write_local_checkout_action,
    _write_setup_uv_noop_action,
    _write_uv_shim,
)
from apache_buildish_release_tooling.harness.backends.act.workflow_yaml import (
    WorkflowJobDefinition,
    _act_step_order_by_job,
    _dump_workflow_yaml,
    _load_github_actions_yaml,
    _load_job_definitions,
    _render_rewritten_workflow_yaml,
    _topological_job_ids,
)
from apache_buildish_release_tooling.shared.io import read_text_file_bounded
from apache_buildish_release_tooling.shared.parsing import DEFAULT_CONFIG_PARSE_MAX_BYTES

__all__ = [
    "WorkflowJobDefinition",
    "_act_step_order_by_job",
    "_dump_workflow_yaml",
    "_load_github_actions_yaml",
    "_load_job_definitions",
    "_render_rewritten_workflow_yaml",
    "_render_uv_shim_script",
    "_repository_slug",
    "_rewrite_workflow",
    "_topological_job_ids",
    "_write_bash_shim",
    "_write_generic_tool_shims",
    "_write_local_checkout_action",
    "_write_setup_uv_noop_action",
    "_write_uv_shim",
]


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
        normalized_job_id = validate_harness_identifier(str(job_id), field_name="workflow job id")
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        raw_steps = job_payload.get("steps")
        if raw_steps is None:
            original_steps: tuple[YamlMapping, ...] = ()
        elif isinstance(raw_steps, list):
            original_steps = tuple(
                require_yaml_mapping(
                    step_payload,
                    source=f"workflow job {job_id} step",
                )
                for step_payload in raw_steps
            )
        else:
            raise ValueError(f"workflow job {job_id} has a non-list steps block")
        rewritten_steps: list[YamlValue] = [_bootstrap_step()]
        generated_action_references = _generated_action_references()
        for index, step_payload in enumerate(original_steps, start=1):
            rewritten_steps.append(
                _rewrite_step(
                    job_id=normalized_job_id,
                    step_payload=step_payload,
                    step_index=index,
                    bindings=bindings,
                    generated_action_references=generated_action_references,
                    real_cli_commands=real_cli_commands,
                    generated_gpg_fixture=generated_gpg_fixture,
                )
            )
        rewritten_steps.append(_job_status_step(normalized_job_id))
        job_payload["steps"] = rewritten_steps
    destination = workspace.root / ".github" / "workflows" / workflow_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_copy = destination.with_name(f"{destination.stem}.original{destination.suffix}")
    original_copy.write_text(
        read_text_file_bounded(workflow_path, max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES),
        encoding="utf-8",
    )
    destination.write_text(
        _render_rewritten_workflow_yaml(
            payload,
            original_workflow_path=workflow_path,
            original_copy_name=original_copy.name,
        ),
        encoding="utf-8",
    )
    return destination
