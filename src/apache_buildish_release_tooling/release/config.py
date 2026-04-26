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
from urllib.parse import urlparse

import yaml

from apache_buildish_release_tooling.release.models import ComponentConfig

_DIST_DEV_PREFIX = "https://dist.apache.org/repos/dist/dev/"
_DIST_RELEASE_PREFIX = "https://dist.apache.org/repos/dist/release/"


def load_component_config(component_config_path: str) -> ComponentConfig:
    """Load component configuration from a required YAML file."""

    path = Path(component_config_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return ComponentConfig.model_validate(payload)


def validate_release_target_base_urls(
    component_config: ComponentConfig,
    *,
    allow_non_production_release_targets: bool,
) -> None:
    """Validate ASF dist base URLs for secure and non-production CLI modes."""

    _validate_release_target_base_url(
        field_name="asf_dist_dev_base",
        configured_url=component_config.asf_dist_dev_base,
        production_prefix=_DIST_DEV_PREFIX,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )
    _validate_release_target_base_url(
        field_name="asf_dist_release_base",
        configured_url=component_config.asf_dist_release_base,
        production_prefix=_DIST_RELEASE_PREFIX,
        allow_non_production_release_targets=allow_non_production_release_targets,
    )


def _validate_release_target_base_url(
    *,
    field_name: str,
    configured_url: str,
    production_prefix: str,
    allow_non_production_release_targets: bool,
) -> None:
    """Validate one configured ASF dist base URL against the CLI security mode."""

    if configured_url.startswith(production_prefix):
        return
    parsed = urlparse(configured_url)
    if allow_non_production_release_targets and parsed.scheme in {"file", "http"}:
        return
    if allow_non_production_release_targets:
        raise ValueError(
            f"{field_name} must use {production_prefix} or a file:// or http:// URI in "
            f"non-production mode: {configured_url}"
        )
    raise ValueError(
        f"{field_name} must use {production_prefix}; pass "
        "--allow-non-production-release-targets only for local file:// or http:// test targets: "
        f"{configured_url}"
    )
