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

"""Typed YAML mapping helpers for harness-owned config and workflow payloads."""

from __future__ import annotations

from typing import TypeAlias

YamlScalar: TypeAlias = str | int | float | bool | None
YamlValue: TypeAlias = YamlScalar | list["YamlValue"] | dict[str, "YamlValue"]
YamlMapping: TypeAlias = dict[str, YamlValue]


def require_yaml_mapping(payload: object, *, source: str) -> YamlMapping:
    """Validate that one loaded YAML document is a top-level mapping."""

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"expected a YAML mapping in {source}")
    return payload


def deep_merge_yaml_mappings(base: YamlMapping, overlay: YamlMapping) -> YamlMapping:
    """Return a recursive mapping merge where overlay values win."""

    merged: YamlMapping = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = deep_merge_yaml_mappings(base_value, overlay_value)
        else:
            merged[key] = overlay_value
    return merged
