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

"""GitHub Actions YAML and job-graph helpers for the harness act backend."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from apache_buildish_release_tooling.harness.models import validate_harness_identifier
from apache_buildish_release_tooling.harness.yaml_types import YamlMapping, require_yaml_mapping


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


def _load_github_actions_yaml(path: Path) -> YamlMapping:
    """Load GitHub Actions YAML without converting keys like `on` into booleans."""

    return require_yaml_mapping(
        yaml.load(  # noqa: S506
            path.read_text(encoding="utf-8"),
            Loader=_GithubActionsYamlLoader,  # noqa: S506
        ),
        source=f"workflow {path}",
    )


def _load_job_definitions(workflow_path: Path) -> list[WorkflowJobDefinition]:
    """Load one workflow YAML file and extract the declared job graph."""

    payload = _load_github_actions_yaml(workflow_path)
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"workflow {workflow_path} does not define a jobs mapping")
    definitions: list[WorkflowJobDefinition] = []
    for job_id, job_payload in jobs.items():
        normalized_job_id = validate_harness_identifier(str(job_id), field_name="workflow job id")
        if not isinstance(job_payload, dict):
            raise ValueError(f"workflow job {job_id} must be a mapping")
        definitions.append(
            WorkflowJobDefinition(
                id=normalized_job_id,
                needs=_normalize_needs(job_payload.get("needs")),
            )
        )
    return definitions


def _normalize_needs(raw_needs: object) -> list[str]:
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


def _dump_workflow_yaml(payload: YamlMapping) -> str:
    """Dump rewritten workflow YAML while keeping the GitHub Actions `on` key literal."""

    rendered = yaml.dump(
        payload,
        Dumper=_GithubActionsYamlDumper,
        sort_keys=False,
        width=1000,
    )
    return re.sub(r"(?m)^([ ]*)['\"]on['\"]:$", r"\1on:", rendered)


def _render_rewritten_workflow_yaml(
    payload: YamlMapping,
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
        raw_steps = job_payload.get("steps")
        if not isinstance(raw_steps, list):
            step_order_by_job[str(job_id)] = step_ids
            continue
        for step_payload in raw_steps:
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
