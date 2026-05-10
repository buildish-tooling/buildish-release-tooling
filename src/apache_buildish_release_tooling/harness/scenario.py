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

"""Scenario loading helpers for the Buildish release harness."""

from __future__ import annotations

from pathlib import Path

from apache_buildish_release_tooling.harness.models import HarnessScenario
from apache_buildish_release_tooling.harness.yaml_types import YamlMapping, require_yaml_mapping
from apache_buildish_release_tooling.shared.parsing import (
    DEFAULT_CONFIG_PARSE_MAX_BYTES,
    read_yaml_mapping_file_bounded,
)


def load_scenario(path: Path) -> HarnessScenario:
    """Load a YAML scenario file into a validated harness model."""

    scenario_dir = path.parent.resolve(strict=False)
    payload = require_yaml_mapping(
        read_yaml_mapping_file_bounded(path, max_bytes=DEFAULT_CONFIG_PARSE_MAX_BYTES),
        source=str(path),
    )
    _resolve_workflow_paths(payload, scenario_dir, _scenario_path_root(scenario_dir))
    return HarnessScenario.model_validate(payload)


def _scenario_path_root(scenario_dir: Path) -> Path:
    """Return the root that scenario-owned workflow paths may reference."""

    if (
        scenario_dir.name == "scenarios"
        and scenario_dir.parent.name == "harness"
        and scenario_dir.parent.parent.name == "buildish-release-tooling"
    ):
        return scenario_dir.parent.parent.parent.resolve(strict=False)
    return scenario_dir


def _resolve_workflow_paths(payload: YamlMapping, scenario_dir: Path, scenario_path_root: Path) -> None:
    """Resolve workflow-related file paths relative to the scenario file."""

    workflow = payload.get("workflow")
    if not isinstance(workflow, dict):
        return
    for key in ("path", "harness_config"):
        raw_value = workflow.get(key)
        if not isinstance(raw_value, str) or not raw_value:
            continue
        raw_path = Path(raw_value)
        if raw_path.is_absolute():
            raise ValueError(f"workflow {key} must be relative to the scenario file: {raw_value}")
        resolved_path = (scenario_dir / raw_path).resolve(strict=False)
        if not resolved_path.is_relative_to(scenario_path_root):
            raise ValueError(
                f"workflow {key} must not escape the scenario path root: {raw_value}"
            )
        workflow[key] = str(resolved_path)
