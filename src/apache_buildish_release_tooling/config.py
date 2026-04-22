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

"""Component configuration loading for the release-tooling CLI."""

from __future__ import annotations

from pathlib import Path

import yaml

from apache_buildish_release_tooling.models import ComponentConfig


def load_component_config(component_config_path: str) -> ComponentConfig:
    """Load component configuration from a required YAML file."""

    path = Path(component_config_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return ComponentConfig.model_validate(payload)
